# Design audit — what the concept asks for vs. what is built

Reference: `Serious Shift Homepage.dc.html` §4A "Swipe the Domains" (the chosen
direction), the `ShiftDetail.dc.html` component it imports, `SiteFooter.dc.html`,
and the content spec in Miro → **SERIOUS SHIFT 2026 → Content Mockup- July'26**.

## Corrections from the Miro content spec

The mockup HTML and the Miro spec disagreed in four places. The Miro is the content
authority, so it won:

| | Was | Now |
|---|---|---|
| **Pull-quote** | Missing. The only quote was the consumer tension. | Separate `pull_quote` module directly after From/To — the analyst's verdict ("The tool that thinks for you eventually thinks instead of you"), distinct from the consumer's voice later. Added to the prompt. |
| **Sub-shift position** | Mid-page, 5th of 10. | Bottom of the page, per *"Swipe/Carousel at the bottom of the KeyShift"*. |
| **Industry sectors** | 15 | **16** — `Media & Publishing` was missing. Recorded in `industry_sectors` in the contract so the prompt and UI share one list. |
| **Reading order** | Hard-coded in the generator. | Owned by `order` in [shift_modules.json](packages/contracts/shift_modules.json); the export sorts to it, so a composition change re-composes on the next free `--export-only` instead of needing 58 shifts regenerated. |

Deliberate deviations from the Miro, kept because the design mockup is the visual
authority:

- **Industries stay a chip selector**, not a native dropdown. The Miro says
  "drop down showing all 16 industries"; the mockup implements a chip row. All 16
  are reachable — scrolled on mobile, wrapped on desktop.
- **The two undesigned visual slots are treated as covered.** The Miro marks
  "a visual about the shift" near the top and "a simple flowchart/visual of some
  sort" before the industries. The From/To cross-fading cards and the
  Now/next/beyond timeline already occupy those slots; no placeholder artwork was
  invented.
- **Title face stays Suez One.** The Miro notes a "special (TrendWatching naming)
  font — need to look up that exact font"; the mockup specifies Suez One. Swap the
  `--font-title` token if the real brand face turns up.

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

## Remediation status

- **SEO and real 404s are implemented.** `BrowserRouter` uses path URLs. Valid
  deep links return 200 with route-specific title, canonical, Open Graph, robots,
  and sitemap metadata. Unknown content paths render the accessible Not Found
  shell with HTTP 404 and noindex; unknown API/assets are ordinary 404 responses.
- **Navigation now follows the later Miro board.** The exact six items are
  Shifts, Methodology, Subscribe, Services, TrendWatching, and About. Saved and
  The room were removed. Only the verified TrendWatching LinkedIn destination
  ships; unverified social destinations are omitted.
- **The mobile prototype remains visual authority.** The 393×852 domain-swipe
  homepage, 0.55-second easing, typography, gradients, cards, footer, and domain
  composition are preserved. Offscreen panels are inert/hidden from assistive
  technology, pointer cancellation is safe, and reduced motion removes
  nonessential movement.
- **Detail navigation is explicit, not whole-page swipe.** Mobile sub-shifts use
  a scroll-snap carousel with visible controls and position. Shift/sub-shift pages
  expose previous/next siblings, and every sub-shift visibly links its parent.
- **WCAG 2.2 AA is the release bar.** Text tokens, text surfaces, headings,
  44-pixel targets, modal-menu focus, tabs/disclosures, carousel state, and source
  link names are covered by unit, Playwright, and axe gates. Visual baselines are
  tracked at 390×844, 393×852, 768×1024, and 1440×900.
- **The frontend reads route-scoped documents.** It fetches the index globally
  and only the current detail document, retains successful cached data during a
  refresh, retries transient failures twice, and distinguishes offline, timeout,
  server-error, and unavailable states. It does not silently render an empty deck.

## Deliberately deferred or operationally blocked

- **Innovations stay dormant.** The module contract remains, but `INGEST_TOKEN`
  is unset and no ingestion/matching infrastructure is being invented.
- **YouTube requires a managed proxy canary.** Code supports credential-redacted
  proxying and records source success, count, latency, requests, and estimated
  cost. Railway must provide `YOUTUBE_PROXY_URL` before one channel can be
  canaried and the other ten restored.
- **A connected in-app Browser pass is still required for staging acceptance.**
  Automated Chromium/axe/visual coverage is present, but it is not a substitute
  for the signed-in connected Browser network/console/focus review.
