# Innovations API

The contract between the upstream **Innovation database** and Serious Shift, plus
the curation and read surfaces built on it.

An *innovation* is a real branded example of a shift. Upstream pushes them here;
an innovation appears on a shift page once it is **mapped** to that shift, and the
mapping is many-to-many — one innovation can be an example of several shifts, and
a shift carries several innovations.

- **Base URL:** the site's own origin (the API and the app are one service).
- **Content type:** `application/json` for every request and response body,
  except `GET /api/innovations/{id}/cover-image`, which returns image bytes.
- **Every route is versionless except the public reads.** The write and curation
  paths are operational surfaces with named clients; `/api/v1/*` is the public,
  cacheable one.

---

## 1. Authentication

Three independent secrets. **A route whose secret is unset answers `404`, not
`401`** — an unauthenticated write endpoint should not exist by default, and 404
leaks less about what is deployed than 401 does.

| Secret | Sent as | Grants |
|---|---|---|
| `INGEST_TOKEN` | `X-Ingest-Token: <token>` | `POST /api/innovations/ingest` |
| `CURATION_TOKEN` | `Authorization: Bearer <token>` | `PUT`/`DELETE` on an innovation's shift links |
| — | — | the `/api/v1/innovations*` reads and `cover-image` are public |

Two tokens rather than one, deliberately: the upstream database's credential can
write innovations but cannot change what appears on a page. Both comparisons are
constant-time.

---

## 2. Errors

One envelope, everywhere, unchanged from the rest of the API:

```json
{
  "error": {
    "code": "unauthorized",
    "message": "Unauthorized.",
    "request_id": "ss-41-7"
  }
}
```

`code` is stable and safe to branch on; `message` is for humans. `request_id` is
also returned as the `X-Request-Id` header and is what to quote when asking about
a specific failure — the underlying database error stays in the server log and is
never sent to a client.

`422` responses add a `details` array naming each problem:

```json
{
  "error": {
    "code": "validation_failed",
    "message": "The payload could not be accepted.",
    "request_id": "ss-41-9",
    "details": [
      { "field": "source_innovation_id", "code": "required" },
      { "field": "article_url", "code": "not_http_url" },
      { "field": "tags.industry[0].slug", "code": "empty" }
    ]
  }
}
```

| `code` | Status | Meaning |
|---|---|---|
| `not_found` | 404 | No such route (the gating secret is unset), or no such record |
| `unauthorized` | 401 | Token missing or wrong |
| `unsupported_media_type` | 415 | `Content-Type` was not `application/json` |
| `invalid_request` | 400 | The body is not valid JSON |
| `validation_failed` | 422 | The body parsed but is not acceptable — see `details` |
| `rate_limited` | 429 | Over the limit; `Retry-After` says when to come back |
| `internal_error` | 500 | Our fault. Retry is safe — every write is idempotent |

A body over 1 MB is rejected with `413` before the handler runs.

**Field codes** used in `details`: `required`, `empty`, `not_an_array`,
`not_an_object`, `not_http_url`, `not_a_positive_integer`,
`not_an_object_or_array`, `unsupported_image_type`, `unknown_scope`,
`unknown_state`, `unknown_shift`, `ambiguous_shift`, `malformed`,
`expected_scope_colon_slug`, `expected_facet_colon_slug`.

A detail entry for a shift **name** carries a third key, `name`, echoing the value
that failed — a payload can name four shifts and a field path alone does not say
which of them the caller should fix.

---

## 3. `POST /api/innovations/ingest`

Accept one innovation. **Rate limit: 60/minute, burst 20.**

### Request

```
POST /api/innovations/ingest
X-Ingest-Token: <INGEST_TOKEN>
Content-Type: application/json
X-Request-Id: <your correlation id>        # optional, echoed back
```

```json
{
  "article_url": "https://example.com/original-article",
  "source_urls": [
    "https://example.com/original-article",
    "https://other-site.com/linked-article"
  ],
  "source_innovation_id": 1234,
  "title": "Generated innovation title",
  "body": "Generated innovation body…",
  "trendbite": null,
  "brands": ["Primary Brand", "Another Brand"],
  "tags": {
    "industry":         [{ "slug": "food-beverage", "external_uuid": "…" }],
    "subindustry":      [{ "slug": "…", "external_uuid": "…" }],
    "region":           [{ "slug": "europe", "external_uuid": "…" }],
    "country":          [{ "slug": "…", "external_uuid": "…" }],
    "audience":         [{ "slug": "…" }],
    "season":           [],
    "innovation-type":  [{ "slug": "…" }],
    "basic-human-need": []
  },
  "cover_image": {
    "url": "https://tw-the-engine.up.railway.app/api/innovations/1234/cover-image?v=…&exp=…&sig=…",
    "mime": "image/jpeg"
  },
  "shifts": {
    "key shifts": ["PSYCHE CAPTURE", "LEGITIMACY COLLAPSE"],
    "sub shifts": ["COGNITION LIEN", "ALIGNMENT LAG"]
  },
  "state": "active"
}
```

| Field | Required | Rules |
|---|---|---|
| `source_innovation_id` | **yes** | Positive integer. A numeric string is accepted. This is the idempotency key |
| `title` | **yes** | Non-empty after trimming |
| `article_url` | **yes** | `http://` or `https://` |
| `source_urls` | no | Array of `http(s)` URLs. A non-URL entry is a `422` |
| `body` | no | Free text. Used as the card's description when `trendbite` is absent, clamped to 240 characters |
| `trendbite` | no | Free text. Preferred as the card's description |
| `brands` | no | Array of non-empty strings. **Element 1 is the primary brand** and is what the card shows |
| `tags` | no | Object of facet → `[{slug, external_uuid?}]`. Facets: `industry`, `subindustry`, `region`, `country`, `audience`, `season`, `innovation-type`, `basic-human-need`. A facet outside that list is **ignored, not rejected** — it stays in the stored payload and is listed in `tags.ignored_facets`. A malformed `external_uuid` is dropped; the tag is still recorded. **Shifts do not belong here** — they have their own field |
| `cover_image` | no | `{url, mime}`. `mime` must be one of `image/jpeg`, `image/png`, `image/webp`, `image/avif` |
| `shifts` | no | The shifts this is an example of, **by name or by slug** — see [The `shifts` field](#the-shifts-field). Stored with `source: "ingest"`, and **never touches editor-made links**. A name matching no currently published shift, or more than one, is a **`422` with nothing written** |
| `state` | no | `active` (default) or `withdrawn`. `withdrawn` hides the innovation everywhere without deleting it — this is how to retract one |

### Idempotency

The natural key is `source_innovation_id`; there is no `Idempotency-Key` header
because the payload already carries a stable upstream identity. Re-POSTing is
always safe:

- **New id** → `result: "created"`.
- **Known id, changed content** → `result: "updated"`, in place.
- **Known id, same content** → `result: "unchanged"`, and nothing is written.

"Same content" ignores the cover URL's query string. That query carries `v`, `exp`
and `sig`, which change every time you sign the same image — counting them would
make every retry look like new content. If a previous cover fetch failed, an
otherwise-unchanged re-POST still retries the mirror.

### Success — `200 OK`

`201` is never used: the same URL both creates and updates, and `result` says
which.

```json
{
  "id": 42,
  "source_innovation_id": 1234,
  "result": "created",
  "state": "active",
  "updated_at": "2026-08-05T09:12:44+0000",
  "cover_image": {
    "state": "stored",
    "url": "/api/innovations/42/cover-image?v=9f2b1c4d55ae",
    "mime": "image/jpeg",
    "byte_size": 148213
  },
  "tags": { "linked": 4, "ignored_facets": [] },
  "brands": ["Primary Brand", "Another Brand"],
  "shift_links": {
    "linked": [{ "scope": "key_trend", "slug": "ai-matches-professional-expertise-institutions-cant" }],
    "unknown": [],
    "named": [{ "name": "PSYCHE CAPTURE", "scope": "key_trend", "slug": "psyche-capture" }]
  },
  "visible_at": ["/map/frontier/ai-matches-professional-expertise-institutions-cant"],
  "request_id": "ss-41-7"
}
```

| Field | Meaning |
|---|---|
| `id` | Our id. Use it for curation and for the cover-image URL |
| `result` | `created` · `updated` · `unchanged` |
| `cover_image.state` | `stored` · `failed` · `none`. When `failed`, `cover_image.error` says why |
| `tags.ignored_facets` | Facets we do not model. Non-fatal, but worth alerting on: it means our taxonomy is behind yours |
| `shift_links.unknown` | **Slugs** in `shifts` that matched no published shift. **Not an error** — the innovation is still stored. Usually a rename |
| `shift_links.named` | What each **name** in `shifts` resolved to. Read it back to learn the slug, and to confirm a name landed on the shift you meant. A slug is absent here — there was nothing to resolve |
| `visible_at` | The page paths where this innovation now renders. Check these rather than deriving our URL scheme |

Response headers: `RateLimit-Limit`, `RateLimit-Remaining`, and
`X-Upstream-Request-Id` echoing your `X-Request-Id`.

### A failed cover image is not a failed ingest

If the image cannot be fetched, the innovation is still saved and the response
carries `cover_image.state: "failed"` with a reason. That is the signal to re-POST
with a freshly signed URL. The card renders without an image in the meantime.

Cover images are **mirrored**, not hotlinked: the page's CSP is
`img-src 'self' data:` and your signed URL expires, so a third-party URL would be
blocked by the browser today and dead tomorrow. We copy the bytes once and serve
them from our own origin.

The fetcher only talks to hosts on the `INNOVATION_ASSET_HOSTS` allowlist, over
HTTPS, with redirects disabled, a 10-second timeout and a 5 MiB ceiling. **If you
move where cover images are served from, that allowlist has to change first** or
every mirror will report `host not allowed`.

### Failure examples

```http
POST /api/innovations/ingest          → 404  not_found        (INGEST_TOKEN unset here)
POST … (no X-Ingest-Token)            → 401  unauthorized
POST … Content-Type: text/plain       → 415  unsupported_media_type
POST … body: "{"                      → 400  invalid_request
POST … no source_innovation_id        → 422  validation_failed
POST … 61st request this minute       → 429  rate_limited     (Retry-After: 2)
```

---

## 4. Curating the shift mapping

A payload can map itself through its `shifts` field, and anything it does not map is
an editorial act. Both writers coexist: **ingest owns `source: "ingest"` links and
curation owns `source: "editor"` links**, and neither deletes the other's. That is
why re-ingesting an innovation cannot undo curation.

### The `shifts` field

`shifts` takes two shapes, and they are the same thing spelled differently. Use
whichever fits what you hold.

**Grouped by scope** — the shape to reach for when you know shifts by name:

```json
"shifts": {
  "key shifts": ["PSYCHE CAPTURE", "LEGITIMACY COLLAPSE"],
  "sub shifts": ["COGNITION LIEN", "ALIGNMENT LAG"]
}
```

**A list of entries** — the original form, unchanged:

```json
"shifts": [
  { "scope": "key_trend", "slug": "psyche-capture" },
  { "scope": "sub_trend", "name": "COGNITION LIEN" }
]
```

Either way the innovation appears on those pages within the cache TTL, with no
publication run.

- **Scope keys are read loosely.** `key shifts`, `Key Shifts`, `key_shifts`,
  `key-shifts`, `keyShifts`, `key shift` and `key trends` are all the same key;
  likewise for `sub`. Case and punctuation are ignored. A key that names neither
  tier is a `422 unknown_scope` — there are exactly two, so a third is a typo, not
  drift.
- **Entries may be** a bare name, or an object carrying `name`, `title`, or `slug`.
  A `slug` is taken as a slug and skips the name lookup entirely; a `name`
  alongside one wins, because a rename strands a slug and not a name. A lone value
  need not be wrapped in a list.
- **In the list form, `scope` defaults to `key_trend`**, so a bare `"PSYCHE
  CAPTURE"` in the array is a key shift.
- **Name matching is case- and whitespace-insensitive.** Names are stored Title
  Case (`Psyche Capture`); the caps you see on the site are a display transform, so
  `PSYCHE CAPTURE` matches.
- **A sub shift is named by its own name alone.** You do not need its parent — the
  two-segment slug (`psyche-capture/cognition-lien`) is resolved for you and comes
  back in `shift_links.named`.
- **Only the current publication is matchable by name.** A shift from an earlier one
  has a slug that no longer routes anywhere, so resolving onto it would file the
  innovation on a page that 404s.
- **Naming a sub shift links that sub shift only** — it does not also appear on the
  parent key shift's page. Name both if you want both.
- **Order becomes `sort_order`**, which is the order the `shifts` array comes back
  in from `GET /api/v1/innovations`. The **list form keeps your exact order**. The
  **object form always puts key shifts first**, then sub shifts, however you write
  the keys — a JSON object's key order does not survive parsing, so the tier decides
  it rather than the alphabet. Send the list form if you need a specific order.
- **Duplicates collapse**, including a shift sent once by name and once by slug.

#### An unresolvable name is a `422`, and nothing is written

A **name** is stricter than a **slug**, deliberately. An unknown slug is
applied-around and reported in `shift_links.unknown`, because a slug is a machine
identity that a rename legitimately breaks. A name is what you believe the shift is
called, and quietly filing an innovation under nothing because that belief went
stale is worse than refusing the write.

```json
{ "error": { "code": "validation_failed", "details": [
  { "field": "shifts.key shifts[1]", "code": "unknown_shift",   "name": "NO SUCH SHIFT" },
  { "field": "shifts.sub shifts[0]", "code": "ambiguous_shift", "name": "TWINNED" }
] } }
```

- `unknown_shift` — no currently published shift has that name. Usually a rename:
  re-send with the new name.
- `ambiguous_shift` — two published shifts share that name. Sub-shift names are
  only unique within a parent, so this is reachable. Nothing is guessed; send that
  one as `{"slug": …}` instead to disambiguate.

The whole payload is refused and no row is touched, so a retry is safe and loses
nothing. The consequence to plan for: **once a shift is renamed, every ingest still
naming it fails** — including a re-POST of otherwise unchanged content, which would
previously have answered `result: "unchanged"`. That is the intended alarm.

One more thing worth knowing: switching an innovation from slugs to names, or
adding `shifts` where there was none, is a content change — so it answers `updated`
rather than `unchanged`. Expect one pass of `updated` results across your back
catalogue when you make the switch.

### `PUT /api/innovations/{id}/shifts`

Replace the editor-curated link set. Idempotent — the body is the desired state.

```
PUT /api/innovations/42/shifts
Authorization: Bearer <CURATION_TOKEN>
Content-Type: application/json
```

```json
{
  "shifts": [
    { "scope": "key_trend", "slug": "ai-matches-professional-expertise-institutions-cant" },
    { "scope": "sub_trend", "slug": "trust-machines/proof-of-human" }
  ]
}
```

`scope` is `key_trend` or `sub_trend`. A **key shift's slug is one segment**; a
**sub-shift's slug is `parent/child`**, which is what makes it unique.

`200 OK`:

```json
{
  "id": 42,
  "linked": [{ "scope": "key_trend", "slug": "…" }],
  "unknown": [{ "scope": "key_trend", "slug": "renamed-last-week" }],
  "request_id": "ss-41-8"
}
```

Unknown slugs are applied-around and reported rather than rejected, so a rename
never blocks the rest of the edit. Add `?strict=1` to get `422 validation_failed`
with the unknown entries in `details` and **nothing applied**.

Empty `shifts` removes every editor link (ingest links stay).

### `DELETE /api/innovations/{id}/shifts/{scope}/{slug}`

Remove one link whatever created it. `204 No Content`, or `404 not_found` if there
is no such link.

```
DELETE /api/innovations/42/shifts/sub_trend/trust-machines/proof-of-human
Authorization: Bearer <CURATION_TOKEN>
```

### When does the page change?

Within the response cache TTL — **60 seconds**, no publication run required. The
backend joins innovations into each shift's module list when it builds a route
fragment, and folds an innovations revision into every fragment's `ETag`, so a
client holding `If-None-Match` is correctly told the page has changed.

---

## 5. Public reads

Rate limit 600/minute, burst 150. `Cache-Control: public, max-age=60,
stale-while-revalidate=300`.

(This said 120/30 for a while, and so did the `ratelimit-limit` header, while the
bucket actually allowed 600 — a client pacing itself against the documented
number was throttling itself to a fifth of its allowance. The figure now comes
from the limiter itself, so the two cannot disagree again.)

### `GET /api/v1/innovations`

| Query | Default | Meaning |
|---|---|---|
| `limit` | 24 | 1–100 |
| `cursor` | — | Opaque; take it from the previous response's `next_cursor` |
| `shift` | — | `scope:slug`, e.g. `key_trend:trust-machines` |
| `tag` | — | Comma-separated `facet:slug` pairs, **ANDed** — a result carries every tag asked for. e.g. `tag=industry:food-beverage,region:europe` |
| `brand` | — | Exact brand match |

```json
{
  "items": [ { "…": "see the record shape below" } ],
  "limit": 24,
  "next_cursor": "1754300000000000_41"
}
```

`next_cursor` is `null` on the last page, and is only issued when the page came
back full — so you never need an extra request that returns nothing. Paging is
keyset, not `OFFSET`, so an innovation arriving mid-scroll cannot shift the page
under a reader. Withdrawn innovations are excluded.

### `GET /api/v1/innovations/{id}`

One record, or `404 not_found`.

```json
{
  "id": 42,
  "source_innovation_id": 1234,
  "title": "Generated innovation title",
  "body": "Generated innovation body…",
  "trendbite": null,
  "article_url": "https://example.com/original-article",
  "source_urls": ["https://example.com/original-article"],
  "brands": ["Primary Brand", "Another Brand"],
  "state": "active",
  "tags": {
    "industry": ["food-beverage"],
    "innovation-type": ["product-launch"],
    "region": ["europe"]
  },
  "cover_image": {
    "state": "stored",
    "url": "/api/innovations/42/cover-image?v=9f2b1c4d55ae",
    "mime": "image/jpeg",
    "byte_size": 148213
  },
  "shifts": [
    {
      "scope": "key_trend",
      "slug": "trust-machines",
      "domain_id": "society",
      "source": "editor",
      "href": "/map/society/trust-machines"
    }
  ],
  "created_at": "2026-08-05T09:12:44+0000",
  "updated_at": "2026-08-05T09:12:44+0000"
}
```

### `GET /api/innovations/{id}/cover-image?v={hash}`

The mirrored bytes, with the stored `Content-Type` and an `ETag` of the content
hash. `304` on a matching `If-None-Match`. `404` if no image is stored or the
innovation is withdrawn.

`?v=` is the first 12 characters of that hash. When it matches, the response is
`Cache-Control: public, max-age=31536000, immutable` — the URL addresses those
exact bytes, so it can be cached forever. When it does not match (a guessed or
stale link), it falls back to one hour rather than pinning a stale image for a
year.

---

## 6. How an innovation reaches a page

```
upstream POST ─► innovations ─┬─► innovation_tag_links ─► innovation_tags
                              ├─► innovation_assets            (mirrored cover)
                              └─► innovation_shift_links ─► shift_refs
                                        ▲                        ▲
                              curation PUT/DELETE      published by the weekly
                                                       synthesize run
```

`innovation_shift_links` is the many-to-many join, with a composite primary key —
so a duplicate pair is structurally impossible and every writer is idempotent for
free.

It points at **`shift_refs`, not at `domain_key_trends`.** The v2 taxonomy is
`TRUNCATE`d with `RESTART IDENTITY` on every synthesize run, so a foreign key into
it would be cascade-deleted every Monday. `shift_refs` is keyed on `(scope, slug)`
— the URL slug, the same durable identity `shift_module_overrides` uses — and is
upserted by publication, never deleted.

The consequence worth knowing: **renaming a shift changes its slug, which strands
every link to the old one.** The link is still in the database and the page simply
stops showing the innovation. Publication reports this:

```
⚠  3 innovation link(s) point at 1 shift(s) not in this publication (renamed?): key_trend:trust-machines
```

Re-point them with `PUT /api/innovations/{id}/shifts` using the new slug.

A link made from a **name** behaves differently, and better: the name is
re-resolved on every POST, so a re-POST after the rename moves the link to the new
slug with no editorial action. The trade is that the ingest *fails* (`422
unknown_shift`) between the rename and the moment upstream sends the new name,
rather than silently stranding the link — see
[The `shifts` field](#the-shifts-field).

**A stranded link is omitted from `GET /api/v1/innovations`.** The `shifts[]`
array lists only shifts in the current publication, because a link the site will
not render is not a destination worth advertising — the endpoint used to hand out
an `href` that 404s, and on staging every href it returned was dead. The row
itself survives, so a re-point (or the slug returning) brings it straight back.

The classifier repairs this on its own for links it owns: a rename changes the
corpus hash, the innovation is re-swept, and `source='auto'` links move to the
new slug. `ingest` and `editor` links are never touched by it — that is the
provenance guarantee — so those are the ones that need the PUT above.

---

## 7. Operating it

| Env var | Where | Notes |
|---|---|---|
| `INGEST_TOKEN` | backend | Unset ⇒ the ingest route is a 404 |
| `CURATION_TOKEN` | backend | Unset ⇒ the curation routes are 404s |
| `INNOVATION_ASSET_HOSTS` | backend | Comma-separated host allowlist for mirroring covers. Defaults to `tw-the-engine.up.railway.app` |

Both tokens should be long random strings, set per environment, and never shared
between staging and production. Rotating one takes effect on the next deploy.

### First-time setup: back-fill `shift_refs`

**On a database migrated *after* its last publication, `shift_refs` is empty and
no innovation can be linked to anything.** Every `shifts[]` entry comes back in
`unknown`, the ingest still returns 200, and nothing looks broken — it just never
reaches a page. Observed on staging the first time this was enabled.

The registry is written by publication, so the next synthesize run fixes it by
itself. To avoid waiting a week, back-fill it from the document already published:

```bash
python3 - <<'PY'
import json, os, psycopg
from psycopg.rows import dict_row
from serious_shift_pipeline.mapgen.export import _publish_shift_refs
conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
doc = json.loads(conn.execute("SELECT body::text AS b FROM documents WHERE key='map'").fetchone()["b"])
_publish_shift_refs(conn, doc); conn.commit()
PY
```

That calls the same function publication does, against the live document. It does
not regenerate anything and does not touch `documents`. Confirm with
`SELECT count(*) FROM shift_refs` — it should equal the map's key shifts plus
sub-shifts.

**Enable staging first.** `POST` the real payload, confirm `result` and
`cover_image.state`, curate a link, and load the shift page with the browser
console open — a CSP violation there means an image is being served from the wrong
origin.
