# Shift map webhook

The outbound half of the innovation↔shift loop. Serious Shift POSTs its current
key shifts and sub-shifts, grouped by sphere, to an endpoint you provide — so an
upstream system knows which shifts exist without polling, and can name them back
in [`POST /api/innovations/ingest`](INNOVATIONS-API.md).

- **Direction:** Serious Shift → you. Nothing is read back; the response body is
  ignored and only the HTTP status being non-error matters.
- **Configured by:** `SS_SHIFTS_WEBHOOK_URL` on the pipeline's **synthesize**
  service. Unset disables the hook entirely.
- **Content type:** `application/json`. No authentication header is sent — see
  [Securing the receiver](#securing-the-receiver).

---

## 1. When it fires

Once per **successful publication**, immediately after the new map is committed and
the site starts serving it. That is the only moment the taxonomy changes.

| Trigger | Cadence |
|---|---|
| Weekly `synthesize` run | Mondays 02:00 UTC |
| `mapgen.cli --export-only` | manual — the free recovery path after a gate failure |
| `mapgen.cli --editorial-only` | manual — modules regenerated, taxonomy unchanged |

All three deliver, deliberately: `--export-only` is how a failed publication is
repaired, and a receiver that missed it would sit stale against a live site.

A publication that **fails the validation gate does not fire** — the map is not
promoted, so there is nothing new to announce. Delivery is fire-and-forget: a
failure is logged on the pipeline side and never retried, and it never fails the
run. If your endpoint was down, you missed that publication; re-run
`mapgen.cli --export-only` to resend, or read the current state from
`GET /api/v1/map`.

---

## 2. Payload

```json
{
  "event": "shift_map.published",
  "published_at": "2026-08-17T02:41:09Z",
  "updated": "2026-08-17",
  "run_id": "20260817T024003-synthesize-a1b2c3",
  "totals": { "spheres": 4, "key_shifts": 33, "sub_shifts": 165 },
  "spheres": [
    {
      "id": "society",
      "name": "Society",
      "label": "AI × Society",
      "key_shifts": [
        {
          "slug": "psyche-capture",
          "name": "Psyche Capture",
          "subtitle": "Attention was the product; interior state is the next one.",
          "velocity": "rising",
          "href": "/society/psyche-capture",
          "sub_shifts": [
            {
              "slug": "psyche-capture/mood-markets",
              "name": "Mood Markets",
              "description": "Emotional read-outs priced and traded like any other signal.",
              "href": "/society/psyche-capture/mood-markets"
            }
          ]
        }
      ]
    }
  ]
}
```

Roughly **135 KB** for a full map (4 spheres, 36 key shifts, 179 sub-shifts as of
2026-08-12). Most of that is prose: `subtitle` and `description` are editorial
paragraphs of 30–60 words, not short deks. Size scales with the taxonomy, so budget
for growth rather than pinning a limit.

### Envelope

| Field | Notes |
|---|---|
| `event` | Always `shift_map.published`. Branch on it if you later share the endpoint. |
| `published_at` | UTC, second resolution. **Order and dedupe on this.** |
| `updated` | The map's own date stamp. Two publications on one day share it, so it is not a delivery key. |
| `run_id` | The pipeline run, e.g. `…-synthesize-…` or `…-export-…`. `null` on a standalone `--editorial-only` run. Quote it in any support request. |
| `totals` | Counts of what this payload actually contains — cheap truncation check. |

### Sphere

`id`, `name`, `label`, `key_shifts`. There are always **four**, in this fixed,
meaningful order: **Society, Economy, Consumers, Organizations**. The `id` is the
URL segment, which is why `organizations` is US-spelled.

### Key shift

`slug`, `name`, `subtitle`, `velocity`, `href`, `sub_shifts`. `subtitle` is the
shift's editorial standfirst — a paragraph, not a tagline. `velocity` is a free-text
pace label (`rising`, `accelerating`, `breakout`, …); treat unknown values as
informational rather than rejecting the payload. Ordering within a sphere is
editorial — preserve it rather than re-sorting.

### Sub-shift

`slug`, `name`, `description`, `href`. Ordering within a key shift is editorial.

---

## 3. Identity — the part that matters

**A shift is identified by its slug, not by any numeric id, and no numeric id is
sent.** Internally the taxonomy tables are truncated and rebuilt on every run, so
database keys are recycled weekly and would be worthless to you. The slug is the
durable identity, and it is the same key the ingest API accepts.

- `key_shifts[].slug` is **globally unique** across all four spheres.
- `sub_shifts[].slug` is the **two-segment `parent/child` path**
  (`psyche-capture/mood-markets`), not the bare last segment. That full path is the
  identity — send it whole.
- `href` is site-relative; prefix it with the site origin for a link.

### Round trip into the ingest API

`name` and `slug` are both accepted by the `shifts` field of
`POST /api/innovations/ingest` ([contract](INNOVATIONS-API.md)). Prefer `slug`:
names are resolved case-insensitively against the current publication, and a name
that matches nothing — or matches two shifts — is a `422` with nothing written.

```json
{ "shifts": { "key shifts": ["psyche-capture"],
              "sub shifts": ["psyche-capture/mood-markets"] } }
```

### Change detection

Slugs are derived from names, so **renaming a shift changes its slug**, and a
renamed shift looks like a removal plus an addition. Diff each delivery against the
last one you stored; do not assume slugs are permanent.

---

## 4. Structural invariants

Every payload has passed the publication gate, so these hold. Treat a payload that
violates one as suspect rather than as new truth:

- exactly 4 spheres, in the order above;
- 7–9 key shifts per sphere;
- 4–5 sub-shifts per key shift;
- every key-shift slug unique map-wide; every sub-shift slug unique map-wide;
- every sub-shift slug begins with its parent's slug and a `/`.

---

## 5. Securing the receiver

**No authentication header is sent.** The taxonomy itself is public — it is on the
live site and on `GET /api/v1/map` — so there is nothing confidential in transit.
The exposure is on your side: your endpoint cannot distinguish a real publication
from anyone who learns the URL and forges one. Mitigate with an unguessable path
segment, an IP allowlist, or by treating the payload as a *cache-invalidation
signal* and re-reading `GET /api/v1/map` rather than trusting the body.

Adding an `Authorization` header later is a small, contained change on the pipeline
side (`mapgen/publish_hook.py`) if you decide you want one.

---

## 6. Verifying a receiver

Build the payload from the live map without sending anything:

```bash
cd apps/pipeline && python -c "
import json
from serious_shift_pipeline.core import db
from serious_shift_pipeline.mapgen.publish_hook import build_shift_map_payload
with db.connect() as c:
    doc = json.loads(db.query_one(c, \"SELECT body::text b FROM documents WHERE key='map'\")['b'])
print(json.dumps(build_shift_map_payload(doc, run_id='local-check'), indent=1))"
```

Then deliver it for real, at no API cost — `--export-only` re-publishes the
existing taxonomy:

```bash
cd apps/pipeline && SS_SHIFTS_WEBHOOK_URL="https://your-endpoint" python -m serious_shift_pipeline.mapgen.cli --export-only
```

Success prints `✓  shift map → <host> · N key shifts · N sub shifts` after the
publication line.
