#!/usr/bin/env bash
# Promote one environment's published content onto another.
#
#   ./scripts/promote-content.sh --from "$STAGING_URL" --to "$TARGET_URL" [--apply]
#
# Step 6a of docs/PRODUCTION-CUTOVER.md. Dry run by default; --apply writes.
#
# WHY THIS EXISTS
# ---------------
# Production's map is the pre-rebuild schema — 58 key shifts and 290 sub-shifts
# with no slug and no modules on any of them — so moving the domain onto it
# serves 348 pages of 404. Staging already holds the map that every committed
# artwork file was drawn for and that every editorial correction landed on: the
# renames that cleared 22 duplicate names, the machine-suffixed URL, real
# capitals in the data, US spellings, the `organizations` sphere id. Copying it
# costs nothing and leaves `preflight-origin.mjs` passing without regenerating a
# single image.
#
# WHAT MOVES, AND WHAT DELIBERATELY DOES NOT
# ------------------------------------------
# The site reads exactly one thing: `documents['map']`. Everything else here
# moves so the database does not contradict the page it is serving.
#
# `domain_sub_trend_claims` is NOT copied, and that is the important decision.
# It links a sub-shift to the claims its editorial cites, by claim id — and the
# two databases have independent id sequences over different corpora. Measured
# 2026-08-09: claim 415 is Herbert Simon on organisational AI in staging and
# youth anxiety in production; 539 and 819 are likewise unrelated. Copying those
# links would satisfy the foreign key and attach entirely unrelated evidence to
# every sub-shift on the site — silently, in a product whose whole claim is that
# its evidence is traceable. Wrong provenance is worse than absent provenance.
#
# The consequence, stated plainly: after this runs, `mapgen.cli --export-only`
# on the target will FAIL, because every sub-shift's editorial cites claims that
# are no longer in its (now empty) routed set. That is the safe direction. The
# gate runs before promotion, so a failed export leaves the served document
# untouched — and it is far better than the alternative, which is what happens
# if the v2 tables are left alone: a re-export would quietly rebuild and publish
# the OLD 58-shift map over the good one, and nothing would say so.
#
# The first full `synthesize` on the target clears this: `reset_v2_tables`
# truncates the taxonomy and regenerates it from the target's own claims, which
# are richer than staging's. Until then, the target is a publish-once database.
set -euo pipefail

FROM=''; TO=''; APPLY=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="$2"; shift 2 ;;
    --to)   TO="$2";   shift 2 ;;
    --apply) APPLY=true; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$FROM" && -n "$TO" ]] || { echo "usage: $0 --from <url> --to <url> [--apply]" >&2; exit 2; }

# Never echo a connection string: these carry the password, and this script's
# output is the kind of thing that gets pasted into a ticket.
mask() { sed -E 's#(://[^:]+:)[^@]+(@)#\1****\2#g'; }
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Parent-first. The reverse of this is the truncate order, and it is the same
# order mapgen's own reset uses, minus the two tables that stay behind.
TABLES=(
  domains_v2
  domain_key_trends
  domain_sub_trends
  domain_synthesis_insights
  domain_flows
  shift_module_visibility
  shift_module_overrides
  shift_refs
)

say "promote content"
echo "  from: $(echo "$FROM" | mask)"
echo "  to:   $(echo "$TO"   | mask)"
$APPLY || echo "  (dry run — pass --apply to write)"

# ── Preconditions ───────────────────────────────────────────────────────────
say "0. Is the source worth promoting, and is the target ready to receive it?"

src=$(psql "$FROM" -At -F'|' -c "
  SELECT count(*) FILTER (WHERE slug <> ''),
         count(*) FILTER (WHERE modules IS NOT NULL AND modules::text <> 'null'),
         count(*)
    FROM domain_key_trends;")
IFS='|' read -r src_slugged src_modules src_total <<<"$src"
echo "  source: $src_total key shifts, $src_slugged with a slug, $src_modules with modules"
[[ "$src_total" -gt 0 && "$src_slugged" == "$src_total" && "$src_modules" == "$src_total" ]] || {
  echo "  ✗ the source map is not fully published — refusing to copy it" >&2; exit 1; }

src_doc=$(psql "$FROM" -At -c "SELECT length(body::text) FROM documents WHERE key='map';")
[[ "${src_doc:-0}" -gt 100000 ]] || { echo "  ✗ source documents['map'] is missing or tiny" >&2; exit 1; }
echo "  source documents['map']: $src_doc bytes"

# The target must already be reconciled: these tables are created by migrations
# well after the pre-squash baseline, so their absence means step 2 has not run.
for t in shift_refs shift_module_visibility; do
  psql "$TO" -At -c "SELECT to_regclass('public.$t');" | grep -q "$t" || {
    echo "  ✗ target has no '$t' — run step 2 (schema reconciliation) first" >&2; exit 1; }
done
echo "  target schema is reconciled"

# A data-only dump carries `SET` lines for GUCs the *source* server knows. Feed
# an 18.x dump to a 16.x server and it aborts on `transaction_timeout` — inside
# the transaction, so nothing is applied, but it fails after the truncate has
# been composed and reads like the copy broke. Refuse up front instead: a
# cross-major copy is not something to discover halfway through.
from_v=$(psql "$FROM" -At -c "SHOW server_version;" | cut -d. -f1)
to_v=$(psql "$TO"   -At -c "SHOW server_version;" | cut -d. -f1)
echo "  postgres: source $from_v, target $to_v"
[[ "$from_v" == "$to_v" ]] || {
  echo "  ✗ major version mismatch ($from_v vs $to_v) — dump/restore across majors is not safe here" >&2
  exit 1; }

# Copying onto a target that has curated innovation links would strand them:
# their shift_ref rows are about to be replaced wholesale.
links=$(psql "$TO" -At -c "SELECT count(*) FROM innovation_shift_links;")
echo "  target innovation links: $links"
[[ "$links" == "0" ]] || {
  echo "  ✗ target has curated innovation links that this would strand — stop and reconcile by hand" >&2
  exit 1; }

# ── The copy ────────────────────────────────────────────────────────────────
say "1. Dump the content tables from the source"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
args=(); for t in "${TABLES[@]}"; do args+=(--table="public.$t"); done
if $APPLY; then
  pg_dump "$FROM" --data-only --no-owner --no-acl "${args[@]}" -f "$tmp/content.sql"
  pg_dump "$FROM" --data-only --no-owner --no-acl --table=public.documents -f "$tmp/documents.sql"
  echo "  $(wc -l < "$tmp/content.sql") lines of content, $(wc -l < "$tmp/documents.sql") of documents"
else
  echo "  would dump: ${TABLES[*]} and documents"
fi

say "2. Replace the target's content, in one transaction"
echo "  truncate (reverse order, CASCADE) → restore → replace documents['map']"
echo "  NOT copied: domain_sub_trend_claims — see the header of this script"
if $APPLY; then
  # One transaction: a half-applied taxonomy is a database that disagrees with
  # the page it serves, which is the exact failure this whole exercise exists to
  # remove.
  psql "$FROM" -At -c "SELECT body::text FROM documents WHERE key='map';" > "$tmp/map.json"
  {
    echo "BEGIN;"
    # `pg_dump --data-only` opens by blanking the search path
    # (`set_config('search_path','',false)`), so every unqualified name after it
    # resolves to nothing. Schema-qualify our own statements and put the path
    # back before them rather than relying on where they sit in the file.
    printf 'SET search_path = public;\n'
    # CASCADE reaches `domain_sub_trend_claims` — intended: those rows belong to
    # the sub-shifts being replaced and mean nothing without them. It also
    # reaches `innovation_shift_links`, which is why step 0 refuses to run at
    # all when the target has any.
    printf 'TRUNCATE %s RESTART IDENTITY CASCADE;\n' \
      "$(printf 'public.%s, ' "${TABLES[@]}" | sed 's/, $//')"
    cat "$tmp/content.sql"
    printf 'SET search_path = public;\n'
    # Only the 'map' key. `map:previous` is the source's own rollback copy and
    # means nothing on the target; other keys may be the target's.
    python3 - "$tmp/map.json" <<'PY'
import sys
body = open(sys.argv[1], encoding='utf-8').read().rstrip('\n')
# A dollar-quoted literal avoids escaping 3.4 MB of JSON. The tag must not
# occur in the body — asserted rather than assumed, because a collision would
# terminate the literal early and produce a syntactically valid, wrong INSERT.
tag = '$ssmap$'
assert tag not in body, 'dollar-quote tag collides with the document body'
print("INSERT INTO public.documents (key, body) VALUES ('map', "
      f"{tag}{body}{tag}::jsonb) "
      "ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now();")
PY
    echo "COMMIT;"
  } > "$tmp/apply.sql"
  # One transaction, document included: a target whose tables and whose served
  # document disagree is the exact failure this exercise exists to remove.
  psql "$TO" -v ON_ERROR_STOP=1 -q -f "$tmp/apply.sql"
  echo "  ✓ applied"
else
  echo "  would truncate and restore ${#TABLES[@]} tables, then replace documents['map']"
fi

# ── Verify ──────────────────────────────────────────────────────────────────
say "3. Verify the target"
if $APPLY; then
  psql "$TO" -At -F'|' -c "
    SELECT 'key shifts', count(*) FROM domain_key_trends
    UNION ALL SELECT 'with slug', count(*) FROM domain_key_trends WHERE slug <> ''
    UNION ALL SELECT 'with modules', count(*) FROM domain_key_trends
       WHERE modules IS NOT NULL AND modules::text <> 'null'
    UNION ALL SELECT 'sub shifts', count(*) FROM domain_sub_trends
    UNION ALL SELECT 'shift refs', count(*) FROM shift_refs
    UNION ALL SELECT 'spheres', count(*) FROM domains_v2
    UNION ALL SELECT 'routed claims (expected 0)', count(*) FROM domain_sub_trend_claims;" \
    | sed 's/^/  /'
  echo "  documents['map'] published: $(psql "$TO" -At -c \
    "SELECT (body->>'updated') || ' · ' || jsonb_array_length(body->'key_trends') || ' key shifts' FROM documents WHERE key='map';")"
  echo
  echo "  Next: point a backend at this database and run"
  echo "    node apps/frontend/scripts/preflight-origin.mjs <origin>"
else
  echo "  (dry run — nothing to verify)"
fi
