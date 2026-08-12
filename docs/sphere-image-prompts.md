# Sphere background images — generation prompts

No literal image-generation prompt existed on the Miro board (full sweep, 2026-08-12); what the
board gives is an art direction: Reinier's 2026-08-04 selection of **Abstract & Conceptual
Surrealism + Mid-Century Realism** from the Frame 7 moodboard, with the constraints "NOT AI
design-ish… mixes graphics with real photos… RAW, not polished… real objects, real people, real
situations… people of all ages, ethnicities, genders, body shapes" and "no copy in images".
The shipped Society background (`public/shift/domain-society-bg.jpg`, 884×791) is the visual mold:
a single-hue duotone illustration — silhouetted figures lit by their devices, a soft crowd behind,
fine network lines, three glowing keyword nodes naming the sphere's stakes.

The prompts below compose that brief per sphere. They were used to art-direct the interim
Claude-crafted SVG backgrounds (`apps/frontend/scripts/generate-sphere-bg.mjs`) and are written to
be pasted into an image model when design replaces the interim set with photo-illustration.

## Shared prompt scaffold

> Editorial duotone illustration, entire image graded into a single color ramp of {COLOR}. A group
> of realistic silhouetted people of varied ages, body shapes and hair — some in the foreground
> cropped at the chest, lit softly from below by the glow of the devices they hold — with a
> blurred crowd standing further back. Fine, faint network lines connect small points of light
> across the scene, converging on three softly glowing circular nodes labeled in small uppercase
> letters: {WORDS}. Grainy poster texture, soft gradients, no other text, no logos, flat graphic
> boldness meets photographic softness, in the spirit of mid-century editorial illustration and
> conceptual surrealism. Not glossy, not perfect, not AI-slick. Portrait-leaning 884×791 crop.

## Per sphere

| Sphere | Color ramp | Keyword nodes | Scene inflection |
|---|---|---|---|
| Society (shipped) | Pink `#FF007A` on deep plum | TRUST · BELONGING · TRUTH | People on phones, faces lit, crowd dissolving into the field |
| Economy | Blue `#0FA6FF` on deep navy | VALUE · WORK · MONEY | Figures at screens and standing desks, one shaking hands, a thin rising chart line traced through the network |
| Organizations | Olive `#C2C64F` on deep moss | SPEED · TRUST · JUDGMENT | Figures around the edge of a meeting table, one presenting, org-chart-like branching in the line work |
| Consumers | Orange `#FF6A1F` on deep rust | IDENTITY · TASTE · DESIRE | Shoppers mid-stride with bags and phones, one hand raised comparing something on a screen |

Node words come from each sphere's deck blurb (`apps/frontend/src/lib/site.js` DECK): Economy
"where value, work and money move…", Organizations "how institutions decide, hire and defend
themselves when speed is free" (rendered as the qualities at stake), Consumers "identity, taste
and desire…".

## Output contract

- 884×791 JPEG (quality ~82), no baked-in scrim — `DomainPage.jsx` and `DomainPanel.jsx` apply
  their own gradients.
- File names: `public/shift/domain-{society|economy|organizations|consumers}-bg.jpg` (US spelling).
- Wire-up: `HERO_IMAGE` in `apps/frontend/src/pages/DomainPage.jsx` and `PANEL_IMAGE` in
  `apps/frontend/src/deck/DomainPanel.jsx`.
