#!/usr/bin/env bash
#
# Production cutover, steps 2–5 of docs/PRODUCTION-CUTOVER.md.
#
# Everything here is INVISIBLE to users. The domain stays on the `frontend`
# service throughout; step 6 (moving it) is deliberately not in this script.
#
#   ./scripts/cutover-steps-2-to-5.sh            # dry run — prints, changes nothing
#   ./scripts/cutover-steps-2-to-5.sh --apply
#
# Needs: PROD_DATABASE_URL (the Postgres service's DATABASE_PUBLIC_URL),
# psql, pg_dump, python3, and the Railway CLI logged in.
#
# The sequence was rehearsed on 2026-08-08 against a pg_restore of production
# into a scratch Postgres: 48,104 claims intact, schema afterwards identical to
# staging — 27 tables, zero column differences.
set -euo pipefail

APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT=7606baa7-420c-4c76-9332-7ff36703e404
PROD_ENV=8ac917c0-230c-4749-92eb-36839d926186
BACKEND_SVC=35cb98f9-b205-4a7b-ab79-95963400c461
RAILWAY="${RAILWAY:-$HOME/.railway/bin/railway}"

: "${PROD_DATABASE_URL:?set PROD_DATABASE_URL to the production Postgres DATABASE_PUBLIC_URL}"

say()  { printf '\n\033[1m%s\033[0m\n' "$*"; }
run()  { if $APPLY; then "$@"; else printf '  would run: %s\n' "$*"; fi; }

# ── Preflight ───────────────────────────────────────────────────────────────
say "0. Preflight"
migrations=$(psql "$PROD_DATABASE_URL" -Atc \
  "SELECT string_agg(version, ',' ORDER BY version) FROM schema_migrations;")
echo "  schema_migrations: $migrations"

case "$migrations" in
  *20250101000000*) echo "  already reconciled — skipping to step 3"; SKIP_DB=true ;;
  0001,0002,0003,0004,0005,0006) SKIP_DB=false ;;
  *) echo "  UNEXPECTED state. Stop and re-read docs/PRODUCTION-CUTOVER.md §2." >&2; exit 1 ;;
esac

# The reconciliation drops five concept-graph tables. It refuses if any has
# rows, but check here too so a refusal is never a surprise mid-run.
if [[ "$SKIP_DB" == false ]]; then
  rows=$(psql "$PROD_DATABASE_URL" -Atc "
    SELECT coalesce(sum(n), 0) FROM (
      SELECT count(*) n FROM claim_concepts UNION ALL
      SELECT count(*) FROM concept_thinkers UNION ALL
      SELECT count(*) FROM thinker_disagreements UNION ALL
      SELECT count(*) FROM tensions UNION ALL
      SELECT count(*) FROM concepts) x;")
  echo "  rows in the five tables 0008 drops: $rows"
  [[ "$rows" == "0" ]] || { echo "  NOT EMPTY — stop." >&2; exit 1; }
fi

# ── 2. Schema ───────────────────────────────────────────────────────────────
if [[ "$SKIP_DB" == false ]]; then
  say "2. Schema — back up first"
  dump="$ROOT/prod-$(date +%Y%m%d-%H%M).dump"
  run pg_dump "$PROD_DATABASE_URL" --no-owner --no-acl -Fc -f "$dump"
  $APPLY && ls -lh "$dump"

  say "2a. Apply 0007 (UP half only — the original carries its own down section)"
  run psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 \
    -f "$ROOT/packages/db/etl/0007_map_rich_fields_up.sql"
  run psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 -Atc \
    "INSERT INTO schema_migrations(version) VALUES ('0007') ON CONFLICT DO NOTHING;"

  say "2b. Reconcile to the squashed baseline"
  run psql "$PROD_DATABASE_URL" -v ON_ERROR_STOP=1 \
    -f "$ROOT/packages/db/etl/reconcile_baseline.sql"

  say "2c. Forward migrations"
  if $APPLY; then
    ( cd "$ROOT/apps/pipeline" && DATABASE_URL="$PROD_DATABASE_URL" \
        python3 -m serious_shift_pipeline.core.migrate )
  else
    echo "  would run: python -m serious_shift_pipeline.core.migrate"
  fi
fi

# ── 3 & 4. Build from the Dockerfile, off mobile-ui ─────────────────────────
say "3. Point the backend at railway.backend.json with an empty root"
echo "  the images COPY packages/, which sits outside apps/ — the root must be /"
run "$RAILWAY" api "mutation{serviceInstanceUpdate(serviceId:\"$BACKEND_SVC\",environmentId:\"$PROD_ENV\",input:{railwayConfigFile:\"railway.backend.json\",rootDirectory:\"/\"})}"

say "4. Deploy from mobile-ui — NOT a merge to main"
echo "  a merge would rebuild the frontend service and flip the live site with"
echo "  no verification. Pointing the backend at the branch cannot."
run "$RAILWAY" api "mutation{serviceInstanceUpdate(serviceId:\"$BACKEND_SVC\",environmentId:\"$PROD_ENV\",input:{branch:\"mobile-ui\"})}"
run "$RAILWAY" redeploy --project "$PROJECT" --environment "$PROD_ENV" --service backend --from-source --yes

# ── 5. Verify on the Railway URL, before the domain moves ───────────────────
say "5. Verify — on the Railway URL only; www.seriousshift.ai is untouched"
URL=https://backend-production-d723.up.railway.app
if $APPLY; then
  echo "  waiting for the deploy…"
  for _ in $(seq 1 40); do
    [[ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health")" == "200" ]] && break
    sleep 20
  done
  for path in /health / /map/society /robots.txt /sitemap.xml /api/v1/map /api/nonsense; do
    printf '  %-22s %s\n' "$path" "$(curl -s -o /dev/null -w '%{http_code}' "$URL$path")"
  done
  echo "  title: $(curl -s "$URL/" | grep -o '<title>[^<]*</title>' | head -1)"
  echo "  map:   $(curl -s "$URL/api/v1/map" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("updated"), d.get("totals"))' 2>/dev/null)"
  echo
  echo "  shift_refs must NOT be zero before enabling ingest:"
  psql "$PROD_DATABASE_URL" -Atc "SELECT count(*) FROM shift_refs;" | sed 's/^/    /'
else
  echo "  would curl $URL for /health, /, /map/society, robots, sitemap, /api/v1/map"
fi

say "Done — steps 2 to 5."
echo "  www.seriousshift.ai is still served by the frontend service."
echo "  Step 6 (moving the domain) and step 7 (removing that service) are"
echo "  deliberately not in this script. See docs/PRODUCTION-CUTOVER.md."
