# Design audit — what the concept asks for vs. what is built

Reference: `Serious Shift Homepage.dc.html` §4A "Swipe the Domains" (the chosen
direction), the `ShiftDetail.dc.html` component it imports, and `SiteFooter.dc.html`.

## Fixed in this pass

| Gap | Detail |
|---|---|
| Bottom scrim missing | The deck has a 40px `rgba(27,22,32,0→0.42)` wash at its foot so the dots and swipe hint hold against a light panel. Was absent; added to [Home.jsx](apps/frontend/src/shift/Home.jsx). |
| Wrong mono face | The design specifies `ui-monospace, 'SF Mono', Menlo` for the mono labels (panel `01 / 04`, horizon, shift indices). We loaded JetBrains Mono. Now the platform stack — matches the design and drops a font request. |
| Stat band showed prose | The band renders its value at 58px (99px desktop). `hero_stat.value` is prose lifted from a claim, and **0 of 53** staging values were short enough — every shift would have rendered a broken band. The editorial prompt now returns a `stat_value` figure, with a leading-figure fallback and the module dropped if neither yields one. |
| Unreferenced assets | `tile-*-crop.png` ×4 and `serious-shift-logo-mark.png` were copied but never used (the tiles belong to a different concept variant and have a pink band baked in). Removed; `public/shift` 896K → 420K. |
| Generated content unrendered | See below — `voices`, `evidence`, `related_shifts` modules and the domain-sheet synthesis block. |

## Generated content now surfaced

The pipeline produces these every run; nothing rendered them. All are composed at
**export time** from existing rows, so surfacing them costs no extra model spend.

| Data | Rows (staging) | Where it now appears |
|---|---|---|
| `proponents_detail` / `skeptics_detail` — thinker name + verbatim quote per shift | on most of 58 shifts | `voices` module ("Who is saying this"), after the tension/horizon |
| claims joined to sub-shifts — text, thinker, source, date, signal strength, consumer implication | 1,968 links | `evidence` module on sub-shift pages, beside the written signals |
| `domain_links` — typed KT↔KT edges with relationship + reasoning | 179 | `related_shifts` module at the foot of a shift page |
| `domain_synthesis_insights` — cross-cutting insight per domain | 16 | "What it adds up to" block closing the domain sheet |
| `velocity` per shift | all 58 | Domain-sheet row meta: `Key shift · Accelerating · 5 min read` |

## Content the chosen template has no home for

The concept's `SHIFTS` data defines these for all 8 shifts, but
`ShiftDetail.dc.html` — the component §4A actually imports — renders none of them.
They appear in some of the concept's *other* variants and in the reference
screenshots, not in the chosen one. Left out deliberately rather than invented:

- `body` — 2–3 paragraphs of long-form prose per shift.
- `sowhat` — 3 "so what" bullets per shift.
- `thread` — a "Take it to the room · 84 replies in #post-labour" community CTA.
- `imgNote` — art direction for a photo (e.g. "photo — vacant open-plan office, 4:3"). **The design has no imagery on any shift page**; these notes describe photography that was never produced.

Each maps cleanly onto a new module type (`prose`, `so_what`, `room_cta`, `image`)
if you want them. That is now a data + registry change, not a redesign.

## Known limitations, not yet addressed

- **No SEO or link previews.** The app is a `HashRouter` SPA with SSR disabled, so
  shift URLs (`/#/map/society/…`) cannot be crawled or unfurled. Every shift page
  is invisible to search and to social cards. This predates the redesign but now
  applies to the whole public site.
- **Deleted routes 404 → home.** `/about`, `/daily`, `/thinker/:name`,
  `/map/thinkers`, `/map/synthesis`, `/map/macros/*` now redirect to the deck. Any
  inbound links to those break.
- **"Saved" is inert.** The menu item needs per-user state; there is no auth or
  per-user storage in the backend. "The room" points at Subscribe.
- **No frontend tests.** The pipeline has 42; the front end has none. The module
  registry, the adapter's live/fallback branching and the drag maths are all
  untested.
- **`innovations` kept.** Empty, but `POST /api/innovations/ingest` is a live
  integration point for the upstream Innovation database. Dropping it would break
  that producer, so it survives 0008 pending confirmation the feed is retired.
- **Unused-but-served endpoints remain**: `/api/thinkers`, `/sources`, `/claims`,
  `/predictions`, `/stats`, `/keynote`, `/synthesis`, `/daily`, `/personalize`.
  The UI calls only `/api/map`. `keynote` in particular is regenerated weekly at
  real cost and has no screen in the design.
