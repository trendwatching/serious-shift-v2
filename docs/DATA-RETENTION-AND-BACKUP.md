# Data retention and backup

Answers audit items **D1** (a retention window on `claims`/`sources`/
`predictions`, or an explicit decision that the archive is the point) and **E3**
(confirm and document the Postgres backup policy). Measured 2026-08-09 against
staging.

## What is in the database

| table | rows | on disk |
|---|---|---|
| `claims` | 45,355 | 57 MB |
| `sources` | 2,512 | 21 MB |
| `predictions` | 9,450 | 4 MB |
| `documents` | — | 7 MB |
| everything else | — | ~14 MB |
| **whole database** | | **103 MB** |

The volume is 1.28 GB of a 50 GB allocation, so the storage question is not
close. Growth is roughly 20,000 claims in a heavy ingest week — call it 25 MB —
which is on the order of 1 GB a year in the worst case.

## D1 — Retention: the archive is the point. Deliberately.

**No retention window on `claims`, `sources` or `predictions`.**

This is a decision, not an omission, and it follows from what the product does.
A prediction is *made* in one week and can only be *resolved* months or years
later; `steps/evaluate.py` walks due predictions, scores whether each came true,
and that history is what `thinker credibility` is computed from. A rolling
window would silently delete the evidence the credibility system exists to
weigh, and it would do it just as the oldest predictions became the most
valuable ones — the only ones old enough to have an answer.

`sources.full_text` is the other candidate and is kept for the same reason: it
is what a re-extraction reads when the extraction prompt changes, and re-fetching
is not equivalent — pages move, paywalls close, and a source that 404s today was
still real evidence when it was ingested.

**Review trigger, so this stays a decision rather than drift:** revisit when the
volume passes **20 GB** (40% of the current allocation), or if a single table
passes 5 GB. At the growth rate above that is years away, and it is a size at
which the cheap answers — dropping `sources.full_text` for items older than N
years, or moving the archive to cold storage — are still available.

### What *is* pruned

Observability only, and it already works: `RunLog.prune()` runs at the end of
every pipeline run and deletes `pipeline_errors` and `pipeline_runs` older than
`SS_RUN_RETENTION_DAYS` (default **180**). Those are diagnostics with a short
useful life, not evidence.

## E3 — Backups

### What is verified

- The production and staging databases each sit on a Railway volume
  (`postgres-volume`, mounted at `/var/lib/postgresql/data`).
- Staging's volume reports 1,281 MB used of 50,000 MB, status Ready.
- **A dump is taken before the migration** in the cutover: step 2 of
  `scripts/cutover-steps-2-to-5.sh` runs
  `pg_dump "$PROD_DATABASE_URL" --no-owner --no-acl -Fc` before any DDL, and
  refuses to continue if it fails. That covers the riskiest single moment.

### What is NOT verified, and needs a human

**Railway's own volume backup schedule and retention are not exposed by the
CLI** — `railway volume` lists volumes and their usage and nothing about
backups. Confirm in the Railway dashboard, on the Postgres service in the
**production** environment:

1. Are scheduled backups enabled?
2. At what frequency, and with what retention?
3. Has a restore ever been tested? An untested backup is a hypothesis.

Record the answers here once confirmed. Until then, treat production as having
**no verified automated backup**, and note that the pre-migration dump above is
a one-off, not a policy.

### The fallback that does not depend on the answer

A weekly logical dump costs nothing and is worth having even if Railway's volume
snapshots turn out to be in place — they protect the volume, not against a bad
migration or a mistaken `DELETE`, and they cannot be restored into a different
environment as easily as a dump can:

```bash
pg_dump "$DATABASE_URL" --no-owner --no-acl -Fc -f "serious-shift-$(date +%F).dump"
```

At 103 MB this is a few seconds and a small file. Restore is:

```bash
pg_restore -d "$TARGET_DATABASE_URL" --no-owner --no-acl serious-shift-2026-08-09.dump
```

A restored copy still needs the schema reconciliation described in step 2 of
[`PRODUCTION-CUTOVER.md`](PRODUCTION-CUTOVER.md) — it carries whatever migration
bookkeeping the source had.
