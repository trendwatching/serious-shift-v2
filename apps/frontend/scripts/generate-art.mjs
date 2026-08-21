#!/usr/bin/env node
/* ════════════════════════════════════════════════════════════════════════
 * AI hero art for key shifts and sub-shifts, generated with Gemini image
 * models ("Nano Banana 2", gemini-3.1-flash-image).
 *
 * Where generate-heroes.mjs draws deterministic vector posters from the slug
 * alone, this script feeds each shift's NARRATIVE — its from→to arc and dek,
 * pulled from the published map — into an image model, art-directed by the
 * house brief in docs/sphere-image-prompts.md: editorial duotone graded into
 * the sphere's own ramp, silhouetted people, poster grain, mid-century
 * editorial illustration + conceptual surrealism, no text, "not AI-slick".
 *
 *   node scripts/generate-art.mjs --dry-run --limit 3
 *   node scripts/generate-art.mjs --only cognitive-erosion --subs --style duotone --samples
 *   node scripts/generate-art.mjs --all --subs            # full fleet (cost guard)
 *
 * Flags:
 *   --only slug,slug     key shifts to include (subs of those come with --subs)
 *   --spheres a,b        restrict to spheres
 *   --limit N            cap the number of key shifts
 *   --subs               include sub-shift tiles (opt-in: 179 of them)
 *   --style S            duotone | photo | collage   (default duotone)
 *   --samples            write to public/shift/ai/samples/<style>/ and DO NOT
 *                        touch src/lib/ai-art.json — for style-picking runs
 *   --dry-run            print prompts + cost table, zero API calls
 *   --all                required for an unfiltered run (spends real money)
 *   --force              regenerate even when file + prompt hash match
 *   --prune              delete files/ledger/manifest entries not in the map
 *   --origin URL         backend origin (default: MAP_ORIGIN or staging)
 *
 * Output (canonical runs): public/shift/ai/{heroes,heroes-wide,og,subs}/*.jpg,
 * manifest src/lib/ai-art.json (merged, never wiped — paid art is not derived
 * art), ledger scripts/ai-art-ledger.json (prompt + hash + cost per file, so a
 * rerun is a no-op unless the prompt or model changed).
 *
 * These directories are deliberately NOT the ones generate-heroes.mjs owns:
 * `npm run heroes` wipes its directories wholesale on every run, and a $17
 * fleet should not be deletable by a poster rebuild.
 *
 * Requires GEMINI_API_KEY (paid tier — image models have no free tier).
 * ════════════════════════════════════════════════════════════════════════ */

import { mkdirSync, writeFileSync, readFileSync, rmSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'
import { chromium } from '@playwright/test'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const AI_DIR = resolve(ROOT, 'public/shift/ai')
const MANIFEST = resolve(ROOT, 'src/lib/ai-art.json')
const LEDGER = resolve(ROOT, 'scripts/ai-art-ledger.json')

const MODEL = 'gemini-3.1-flash-image'
const COST_PER_IMAGE = 0.067 // USD, 1K tier, standard (not batch)
const API_BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

/* The four sunset ramps — same values as PALETTE in generate-heroes.mjs and
   --grad-sunset in styles/tokens.css. Duplicated rather than imported: that
   file's exports are hashed by check-frame.mjs and this script must not grow
   a reason to touch it. `tone` names the near-black ground for the prompt. */
const RAMP = {
  society:       { hot: '#FF007A', dark: '#39001F', tone: 'deep plum, near-black' },
  economy:       { hot: '#0FA6FF', dark: '#022638', tone: 'deep navy, near-black' },
  organizations: { hot: '#C2C64F', dark: '#20260A', tone: 'deep moss green, near-black' },
  consumers:     { hot: '#FF6A1F', dark: '#3B1101', tone: 'deep rust, near-black' },
}

/* ── Style presets ────────────────────────────────────────────────────────
 * Three candidate looks; samples decide which one the fleet gets. Each is a
 * function of the ramp so the sphere's light carries through every style.
 * All three end in the same discipline: real varied people, no faces carrying
 * the image, raw not glossy — the Miro review's "non-AI, non generic".
 * ---------------------------------------------------------------------- */
const STYLES = {
  duotone: (ramp) =>
    `Editorial duotone illustration, the entire image graded into a single color ramp of ${ramp.hot} on ${ramp.tone}. `
    + 'Realistic silhouetted people of varied ages, body shapes and hair — some in the foreground cropped at the chest, '
    + 'a softer out-of-focus crowd further back; nobody has a visible face, the crowd is what the shift lands on. '
    + 'Grainy printed poster texture, soft gradients, flat graphic boldness meets photographic softness, '
    + 'in the spirit of mid-century editorial illustration and conceptual surrealism. '
    + 'Raw and imperfect, not glossy, not perfect, not AI-slick.',
  photo: (ramp) =>
    `Conceptual editorial photograph, heavily color-graded so the whole frame sits in a duotone of ${ramp.hot} over ${ramp.tone}. `
    + 'A real, physically staged scene — real objects, real people of varied ages, ethnicities and body shapes, '
    + 'shot from behind or in silhouette so no face carries the image. '
    + 'One surreal staging decision makes the concept visible, the rest stays documentary. '
    + 'Heavy 35mm film grain, slight motion blur, imperfect available light. '
    + 'Raw and unpolished, like a magazine cover photograph from a serious weekly, not a stock photo, not AI-slick.',
  collage: (ramp) =>
    `Mixed-media cut-paper and photo collage, every element re-tinted into a duotone of ${ramp.hot} on ${ramp.tone}. `
    + 'Torn paper edges, halftone dots, misregistered print artifacts, photographic fragments of real people of varied '
    + 'ages and body shapes (silhouetted or seen from behind, no readable faces) layered against bold flat graphic shapes. '
    + 'Brutalist poster energy in the spirit of mid-century protest graphics and conceptual surrealism. '
    + 'Handmade and imperfect, not glossy, not AI-slick.',
}

/* ── Template styles ──────────────────────────────────────────────────────
 * Unlike the presets above, a template style is a COMPLETE prompt supplied
 * by the design team, used verbatim — the shift's description is spliced
 * into its CONCEPT slot and nothing else is added (no ramp, no frame clause,
 * no extra no-text guard; the template carries its own rules). Aspect ratio
 * still comes from imageConfig per frame.
 * ---------------------------------------------------------------------- */
const CONCEPT_SLOT = '[PASTE YOUR DESCRIPTION HERE]'
const TEMPLATES = {
  // Reinier's editorial-illustration prompt, received 17 Aug 2026. Verbatim.
  editorial: `Create a contemporary conceptual editorial illustration in a highly stylized, tactile, print-inspired visual language.
VISUAL STYLE
The artwork should look like a premium illustrated magazine cover / feature illustration, created by a contemporary editorial illustrator using a combination of flat gouache painting, screen printing, vintage poster art and digital collage.
The visual style is:
bold + graphic + painterly + textured + surreal + editorial + sophisticated
It should feel hand-illustrated and physically printed, not digitally generated.
ILLUSTRATION TREATMENT
Use large simplified shapes and painterly colour blocks rather than realistic rendering.
Forms should be:

* simplified but expressive
* slightly irregular
* organically shaped
* graphic and bold
* constructed from overlapping blocks of colour
* subtly rough around the edges

Characters should look like stylized editorial people, with simplified faces, minimal facial features and strong silhouettes.
Do not make them cute, cartoonish or exaggerated.
The people should feel like real adults interpreted through an illustrator's visual language.
VERY IMPORTANT: TEXTURE
The surface of the entire illustration should have a rich analogue print texture.
Use:

* visible paper grain
* fine speckling
* dry-brush texture
* subtle ink bleed
* screen-print imperfections
* halftone grain
* distressed pigment
* uneven colour density
* subtle noise within colour fields
* slightly rough printed edges

Large areas of colour should NOT be perfectly smooth.
The viewer should feel that the image was painted/printed on textured paper and then scanned.
Texture should exist throughout the image — in the background, characters, shadows and objects.
COLOUR
Use a small, deliberate colour palette.
Colours should be rich but slightly muted, with a vintage printed quality.
Use combinations such as:

* deep navy / midnight blue
* dusty blue
* muted sky blue
* warm cream
* burnt orange
* terracotta
* ochre
* mustard yellow
* muted red
* dark forest green

Allow strong contrasting colour relationships.
Use large areas of saturated colour, but make them feel like pigment or ink rather than digital RGB.
Avoid overly clean neon colours.
LIGHTING & SHADOW
Use graphic blocks of light and shadow.
Do not use realistic cinematic rendering.
Shadows should often appear as large, simplified shapes with textured edges.
Use dramatic directional lighting and strong tonal contrast.
Allow certain objects or people to emerge dramatically from darker environments.
COMPOSITION
The composition should be conceptual and metaphorical.
Do not simply depict the subject literally.
Instead, identify the underlying idea and create an unexpected visual metaphor.
Use:

* extreme scale
* unusual perspective
* oversized objects
* tiny human figures
* objects interacting with people
* visual contradictions
* large foreground elements
* strong diagonal movement
* unusual cropping
* layered compositions
* generous negative space

The composition should feel like an editorial thought translated into an image.
It should have an immediate visual hook.
PERSPECTIVE
Perspective can be deliberately exaggerated.
Use:

* bird's-eye views
* extreme close-ups
* low angles
* enormous foreground objects
* tiny figures in large environments
* objects extending beyond the frame

Perspective should contribute to the metaphor rather than simply establish realistic space.
SURREALISM
Introduce one unexpected surreal transformation or relationship.
For example:
a gigantic hand manipulating a landscape,
a person walking through an enormous object,
a normal everyday object becoming architectural,
a human figure dwarfed by an abstract system,
or an ordinary environment behaving in an impossible way.
The surreal element should feel intelligent and purposeful, not random.
PEOPLE
People should be:

* adult
* natural
* understated
* diverse
* slightly stylized
* simplified
* expressive through posture
* minimally detailed

Faces should be graphic rather than realistic.
Use clothing as simple blocks of colour.
Avoid glossy skin, perfect faces and fashion-editorial posing.
GRAPHIC CHARACTER
The illustration should sit somewhere between:
editorial illustration + contemporary poster art + screen print + gouache painting + graphic novel composition
but it must remain refined and sophisticated.
Think art-directed magazine illustration, not comic-book art.
DO NOT CREATE
Avoid:

* photorealism
* 3D CGI
* glossy digital art
* hyperrealistic lighting
* smooth vector gradients
* generic corporate illustrations
* generic flat-design illustrations
* stock-art aesthetics
* childish cartoon characters
* anime
* Pixar / Disney aesthetics
* overly cute characters
* excessive detail
* photorealistic faces
* shiny plastic surfaces
* generic futuristic AI imagery
* excessive neon
* random decorative objects

MOST IMPORTANT STYLE RULE
The final image should have the feeling of a beautifully printed contemporary editorial illustration.
It should look slightly imperfect.
The colour should feel like ink or gouache on paper.
The edges should feel illustrated rather than mathematically vector-perfect.
The texture should be embedded into the artwork, not added as an obvious filter.
The image should feel intelligent, metaphorical, tactile and visually unexpected.
CONCEPT
${CONCEPT_SLOT}
Interpret the concept first.
Identify its core human tension, behavioural shift, opportunity or contradiction.
Then create one strong visual metaphor that expresses that idea.
Do not write any text inside the image.
Do not illustrate the sentence literally.
Create an original editorial composition using the exact visual language described above.
OUTPUT
Premium contemporary editorial illustration.
Portrait 4:5 composition.
Highly textured printed surface.
Bold graphic composition.
Limited sophisticated colour palette.
Painterly flat shapes.
Strong visual metaphor.
Subtle surrealism.
Human, sophisticated and intellectually engaging.`,
  // The screen-print / linocut prompt, received 17 Aug 2026. Verbatim.
  linocut: `Create a sophisticated contemporary editorial illustration in a hand-pulled screen-print / linocut-inspired style, using the exact visual language described below.
OVERALL AESTHETIC
The image should look like a high-end editorial illustration that has been created from a photographic or observational reference and then manually translated into a limited-colour print.
The result should feel:
graphic + painterly + tactile + human + dramatic + editorial + slightly raw
It should look like ink printed onto textured paper, rather than a digitally rendered illustration.
The artwork should have the visual sophistication of a premium magazine or newspaper editorial illustration, while retaining the imperfections and personality of traditional printmaking.

COLOUR SYSTEM
Use an extremely restricted colour palette.
Ideally use only:

* one very dark navy / almost-black ink
* one medium desaturated blue
* one lighter dusty blue
* one warm coral / salmon accent
* one warm off-white / cream

Do NOT introduce many additional colours.
The image should essentially feel like a 2–4 colour screen print with one strong accent colour.
Use colour as a structural element rather than realistic colour reproduction.
For example:

* skin can be represented using cream, blue and coral
* clothing can become large navy or blue shapes
* shadows can become navy graphic masses
* highlights can become cream
* selected areas can use coral as a dramatic accent

Colours should feel like physical ink pigments, slightly imperfect and subtly desaturated.
Avoid:

* neon
* glossy colours
* photorealistic colour
* rainbow palettes
* smooth digital gradients



DRAWING LANGUAGE
Translate realistic subjects into bold illustrated graphic planes.
Preserve enough anatomy that people remain recognizable as real human beings.
Faces should retain:

* cheekbones
* noses
* eye sockets
* jawlines
* hair shapes
* facial expressions

But simplify them into large areas of light, mid-tone and shadow.
Do not draw realistic skin.
Instead, construct faces using:

* solid colour planes
* angular shadow shapes
* small areas of highlight
* hand-drawn contour marks
* directional hatching

The result should resemble a skilled illustrator interpreting a photograph through printmaking.

LINEWORK
Use expressive hand-drawn ink lines.
Lines should vary in:

* thickness
* density
* direction
* pressure

Do not use perfectly uniform vector outlines.
Use lines selectively to define:

* facial structure
* hair
* clothing folds
* hands
* objects
* architectural elements
* important contours

Some edges should be completely defined by colour contrast rather than an outline.
The linework should feel drawn by hand with ink, not generated from clean vector geometry.

CROSS-HATCHING
This is one of the most important characteristics.
Introduce visible directional hatching and cross-hatching throughout the illustration.
Use fine parallel lines to describe:

* hair
* cheeks
* forehead
* clothing
* hands
* shadows
* folds
* objects

Use different hatch directions to distinguish different surfaces and planes.
Some areas should have:

* dense dark hatching
* sparse hatching
* overlapping cross-hatching
* broken hatch marks
* short gestural strokes

Hatching should follow the form of the object or body, rather than being random texture.
It should feel manually drawn.
Do not overuse it everywhere. Leave large flat areas of colour between textured areas.

LIGHT AND SHADOW
Use extreme graphic chiaroscuro.
Convert realistic lighting into large simplified areas of:
dark ink → mid-tone colour → light paper
Shadows should be bold and sometimes exaggerated.
Do not create smooth photographic shading.
Instead, create:

* hard-edged shadows
* large dark silhouettes
* angular tonal planes
* dramatic highlights
* graphic transitions between light and dark

The image should have a strong sense of light emerging from darkness.

PEOPLE
People are central and should feel observational and human, not cartoon characters.
Use realistic adult proportions.
Faces should be recognizable and expressive through:

* posture
* gaze
* head angle
* body position
* simplified facial planes

Avoid exaggerated cartoon expressions.
Avoid:

* oversized heads
* tiny bodies
* cute characters
* anime features
* generic corporate avatars

The people should feel like real people captured in a moment and translated into printmaking.

COMPOSITION
Use a dense, editorial composition with overlapping figures and objects.
Allow elements to:

* enter and leave the frame
* overlap one another
* be partially cropped
* occupy the foreground
* create layers of depth

Use an interesting viewpoint rather than a straightforward centered portrait.
Create a sense of:

* movement
* tension
* interaction
* narrative
* human relationships

The composition should feel like a single frozen moment from a larger story.

DEPTH
Create depth through:
scale + overlap + colour separation + ink density + hatching
rather than realistic rendering.
Foreground subjects can be much larger.
Background subjects can become:

* simplified shapes
* darker silhouettes
* partially obscured figures
* fragmented forms

Use overlapping bodies and objects to create a rich visual field.

BACKGROUND
Keep the background relatively simple.
Use large flat areas of muted colour with occasional:

* architectural shapes
* geometric forms
* furniture
* environmental details
* graphic lines

Background details should support the narrative without competing with the people.
Do not create a photorealistic environment.

PRINT TEXTURE
The entire artwork should have a subtle physical printmaking texture.
Include:

* fine paper grain
* slightly rough ink edges
* subtle ink bleeding
* tiny speckles
* distressed pigment
* uneven ink density
* small imperfections
* faint registration irregularities
* subtle screen-print texture

Some areas should appear slightly darker or lighter because of imperfect ink coverage.
The texture should feel naturally embedded in the illustration.
Do not add an obvious digital noise filter over a clean image.
It should look as though the artwork was actually printed on paper.

EDGE QUALITY
Edges are important.
Avoid perfectly smooth digital vector edges.
Use a mixture of:

* hard graphic edges
* rough ink edges
* broken edges
* hand-drawn contours
* slightly feathered print edges

Some colour shapes should appear to have been cut or painted by hand.

VISUAL HIERARCHY
The illustration should have three levels of detail:
PRIMARY
Faces, hands, major body forms and the main conceptual object.
These should have the strongest definition and contrast.
SECONDARY
Clothing, surrounding people and environmental elements.
These can use simpler shapes and less detail.
TERTIARY
Background shapes, textures and atmospheric elements.
These should be quieter and less defined.

CONCEPTUAL EDITORIAL QUALITY
This is NOT a literal scene illustration.
If I provide a concept, trend or sentence, first determine:
What is the underlying human behaviour?
What is changing?
What is the tension or contradiction?
What is the strongest visual metaphor for it?
Then construct an editorial scene around that metaphor.
The metaphor should be clever but visually understandable.
Do not simply place keywords from the text into the image.

IMPORTANT STYLE REFERENCES
The final artwork should sit visually between:
editorial illustration
+
screen printing
+
linocut / relief printmaking
+
graphic novel ink work
+
limited-palette poster art
+
observational figure drawing
But keep the final result sophisticated and contemporary, not vintage cosplay or comic-book pulp.

ABSOLUTELY AVOID
Do not use:

* photorealism
* 3D CGI
* glossy digital rendering
* smooth gradients
* airbrushed skin
* generic vector illustration
* corporate SaaS illustration
* cartoon aesthetics
* anime
* Pixar / Disney aesthetics
* exaggerated caricatures
* excessive colours
* neon palettes
* photorealistic textures
* perfect geometric outlines
* plastic-looking surfaces
* generic AI imagery
* excessive decorative details



FINAL STYLE TARGET
The finished illustration should look like:
a sophisticated editorial scene manually translated from reality into a limited-colour screen print, with bold navy graphic shadows, muted blue tonal planes, warm coral accents, cream paper highlights, expressive ink linework, directional cross-hatching, rough print edges and tactile paper grain.
It should feel human, intelligent, dramatic, slightly imperfect and unmistakably illustrated.
The image should look printed rather than rendered.
CONCEPT TO VISUALIZE
${CONCEPT_SLOT}
Translate the concept into one powerful editorial visual metaphor while maintaining the exact illustration language above.
No text or typography inside the image unless specifically requested.
Default composition: 4:5 portrait.`,
}

/* Every prompt ends with this. Image models volunteer signage, headlines and
   UI the moment a prompt mentions institutions or screens — and a baked-in
   word fights the real headline the page sets over the art. */
const NO_TEXT =
  ' Absolutely no text anywhere in the image: no words, no letters, no numbers, '
  + 'no signage, no logos, no watermarks, no captions.'

/* The second ban, added after the 19 Aug 2026 review of the first fleet: nearly
   every image had come back with an arrow or a lightning bolt in it, or someone
   at a screen. The brief prompt bans these too, but the brief and the image are
   written by different models and this one reaches for them unprompted. */
const NO_SYMBOLS =
  ' No explanatory symbols of any kind: no arrows, no lightning bolts, no '
  + 'circuitry, no glowing brains or orbs, no rising graphs, no networks of dots '
  + 'or connecting lines, no robots, no holograms, and nobody looking at a screen, '
  + 'laptop, phone or monitor. Nothing in the scene may be an object whose job is '
  + 'to carry writing: no books, no documents, no filled-in cards, no menus, no '
  + 'signs. Torn paper as a collage texture is fine; paper as the subject is not.'

/* One generation per frame; the wide master is cropped twice (band + OG). */
const FRAMES = {
  hero: {
    aspect: '4:5', w: 800, h: 1000, quality: 80,
    clause: 'Vertical poster composition: one clear focal point in the upper half, the rest of the frame giving it room, nothing essential in the outer margins.',
  },
  wide: {
    aspect: '21:9', w: 1600, h: 600, quality: 80,
    clause: 'Panoramic frieze composition: low horizon, the focal subject centered, nothing essential in the top or bottom sixth so the image survives a letterbox crop.',
  },
  sub: {
    aspect: '1:1', w: 640, h: 640, quality: 78,
    clause: 'A single close-cropped detail of that world: one motif drawn far too large for the frame, bleeding off at least two edges, bold enough to read as a small thumbnail.',
  },
}
/* OG is a second crop of the wide master, not a third generation. */
const OG = { w: 1200, h: 630, quality: 80 }

/* ── CLI ─────────────────────────────────────────────────────────────── */

const argv = process.argv.slice(2)
const flag = (name) => argv.includes(name)
const value = (name) => {
  const i = argv.indexOf(name)
  return i > -1 ? argv[i + 1] : null
}

const OPTS = {
  only: value('--only')?.split(',').map((s) => s.trim()).filter(Boolean) ?? null,
  spheres: value('--spheres')?.split(',').map((s) => s.trim()).filter(Boolean) ?? null,
  limit: value('--limit') ? Number(value('--limit')) : null,
  subs: flag('--subs'),
  style: value('--style') ?? 'duotone',
  samples: flag('--samples'),
  dryRun: flag('--dry-run'),
  all: flag('--all'),
  force: flag('--force'),
  prune: flag('--prune'),
}

if (!STYLES[OPTS.style] && !TEMPLATES[OPTS.style]) {
  console.error(`✗ unknown --style ${OPTS.style}; expected ${[...Object.keys(STYLES), ...Object.keys(TEMPLATES)].join(' | ')}`)
  process.exit(1)
}
const filtered = OPTS.only || OPTS.spheres || OPTS.limit !== null
if (!filtered && !OPTS.all && !OPTS.dryRun && !OPTS.prune) {
  console.error('✗ an unfiltered run generates ~250 paid images — pass --all if you mean it,\n  or scope with --only/--spheres/--limit')
  process.exit(1)
}
const API_KEY = process.env.GEMINI_API_KEY
if (!API_KEY && !OPTS.dryRun && !OPTS.prune) {
  console.error('✗ GEMINI_API_KEY is not set. export GEMINI_API_KEY=… and rerun\n  (image models are paid-tier only). --dry-run works without a key.')
  process.exit(1)
}

const originArg = argv.indexOf('--origin')
const ORIGIN = originArg > -1
  ? argv[originArg + 1]
  : process.env.MAP_ORIGIN || 'https://backend-staging-1c16.up.railway.app'

const SPHERES = ['society', 'economy', 'organizations', 'consumers']

/* ── Map walking (same shapes as generate-heroes.mjs, but keeping text) ── */

const tail = (slug) => (typeof slug === 'string' ? slug.split('/').filter(Boolean).at(-1) : '')
const sleep = (ms) => new Promise((done) => { setTimeout(done, ms) })

async function get(path, attempt = 0) {
  const res = await fetch(`${ORIGIN}${path}`)
  if (res.status === 429 && attempt < 6) {
    const wait = Number(res.headers.get('retry-after')) * 1000 || 1000 * 2 ** attempt
    await sleep(wait)
    return get(path, attempt + 1)
  }
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`)
  return res.json()
}

/** Pull the narrative a prompt needs out of a shift's module list. */
function narrativeOf(modules) {
  const out = {}
  for (const m of Array.isArray(modules) ? modules : []) {
    const d = m?.data ?? m ?? {}
    if ((m?.type === 'from_to' || m?.type === 'from_to_solid') && !out.from) {
      out.from = d.from
      out.to = d.to
    }
    if (m?.type === 'dek' && !out.dek) out.dek = d.text
    if (m?.type === 'lede' && !out.lede) out.lede = d.text
  }
  return out
}

async function keyShifts() {
  const out = []
  for (const sphere of SPHERES) {
    if (OPTS.spheres && !OPTS.spheres.includes(sphere)) continue
    const body = await get(`/api/v1/map/${sphere}`)
    const dom = body.domains?.[0] ?? body
    for (const k of dom.key_shifts ?? dom.key_trends ?? []) {
      const slug = tail(k.slug)
      if (!slug) continue
      if (OPTS.only && !OPTS.only.includes(slug)) continue
      out.push({ slug, sphere })
    }
  }
  const capped = OPTS.limit !== null ? out.slice(0, OPTS.limit) : out
  // The detail payload carries the modules; the sphere index does not.
  for (const s of capped) {
    const body = await get(`/api/v1/map/${s.sphere}/${s.slug}`)
    const kt = body.shift ?? body.key_shift ?? body.key_trend ?? body
    s.title = kt.name ?? s.slug
    s.narrative = narrativeOf(kt.modules)
    s.subs = (body.sub_shifts ?? body.sub_trends ?? []).map((sub) => ({
      slug: tail(sub.slug),
      title: sub.name ?? '',
      dek: sub.subtitle || sub.description || narrativeOf(sub.modules).dek || '',
    })).filter((sub) => sub.slug)
  }
  return capped
}

/* ── Prompt building ─────────────────────────────────────────────────── */

function heroPrompt(shift, frame) {
  const { title, narrative, sphere } = shift
  const arc = narrative.from && narrative.to
    ? ` The world is moving from ${lower(narrative.from)} to ${lower(narrative.to)}.`
    : ''
  const dek = narrative.dek || narrative.lede
  const scene = dek ? ` ${dek}` : ''
  // Template styles take ONLY the shift's description in their concept slot.
  if (TEMPLATES[OPTS.style]) {
    return TEMPLATES[OPTS.style].replace(CONCEPT_SLOT, `${title}.${scene}${arc}`)
  }
  return (
    `${STYLES[OPTS.style](RAMP[sphere])} `
    + `The scene expresses the shift "${title}".${arc}${scene} `
    + `${frame.clause}${NO_TEXT}${NO_SYMBOLS}`
  )
}

function subPrompt(shift, sub) {
  const parentArc = shift.narrative.from && shift.narrative.to
    ? ` in a world moving from ${lower(shift.narrative.from)} to ${lower(shift.narrative.to)}`
    : ''
  const dek = sub.dek ? ` ${sub.dek}` : ''
  if (TEMPLATES[OPTS.style]) {
    return TEMPLATES[OPTS.style].replace(
      CONCEPT_SLOT,
      `${sub.title}, part of the shift "${shift.title}"${parentArc}.${dek}`,
    )
  }
  return (
    `${STYLES[OPTS.style](RAMP[shift.sphere])} `
    + `The image is a detail of the shift "${shift.title}"${parentArc} — this detail is "${sub.title}".${dek} `
    + `${FRAMES.sub.clause}${NO_TEXT}${NO_SYMBOLS}`
  )
}

/* Narrative copy arrives sentence-cased; mid-sentence it reads like a splice.
   Only a sentence-case initial is lowered — "AI treated as…" must not become
   "aI treated as…". */
const lower = (s) => (typeof s === 'string' && /^[A-Z][a-z]/.test(s) ? s.charAt(0).toLowerCase() + s.slice(1) : s)

const promptHash = (prompt, aspect) =>
  createHash('sha256').update(`${MODEL}|${aspect}|${prompt}`).digest('hex').slice(0, 16)

/* ── Gemini call ─────────────────────────────────────────────────────────
 * The one function that knows the wire format, so a shape change is a
 * one-place fix. generateContent with responseModalities/imageConfig is the
 * documented form for the gemini-*-image family.
 * ---------------------------------------------------------------------- */
async function generateImage(prompt, aspect, attempt = 0) {
  const res = await fetch(`${API_BASE}/${MODEL}:generateContent`, {
    method: 'POST',
    headers: { 'x-goog-api-key': API_KEY, 'content-type': 'application/json' },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: {
        responseModalities: ['IMAGE'],
        imageConfig: { aspectRatio: aspect, imageSize: '1K' },
      },
    }),
  })
  if ((res.status === 429 || res.status >= 500) && attempt < 6) {
    const wait = Number(res.headers.get('retry-after')) * 1000 || 1000 * 2 ** attempt
    await sleep(wait)
    return generateImage(prompt, aspect, attempt + 1)
  }
  if (!res.ok) throw new Error(`${MODEL} HTTP ${res.status}: ${(await res.text()).slice(0, 300)}`)
  const body = await res.json()
  const part = body.candidates?.[0]?.content?.parts?.find((p) => p.inlineData?.data)
  if (!part) {
    const why = body.candidates?.[0]?.finishReason || JSON.stringify(body).slice(0, 300)
    throw new Error(`${MODEL} returned no image (${why})`)
  }
  return Buffer.from(part.inlineData.data, 'base64')
}

/* ── Raster post-processing ──────────────────────────────────────────────
 * Playwright, not sharp: the same house rule as render-og.mjs — Chromium is
 * already a devDependency and already in CI. object-fit:cover centers the
 * crop, the screenshot clip sets the exact output pixels, and JPEG keeps a
 * grainy gradient at a repo-friendly size.
 * ---------------------------------------------------------------------- */
let browser = null
async function recompress(buffer, { w, h, quality }) {
  if (!browser) browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 })
  try {
    const uri = `data:image/jpeg;base64,${buffer.toString('base64')}` // the model returns JPEG; Chromium sniffs anyway
    await page.setContent(
      `<style>html,body{margin:0;padding:0;overflow:hidden}img{display:block;width:${w}px;height:${h}px;object-fit:cover}</style>`
      + `<img src="${uri}">`,
      { waitUntil: 'load' },
    )
    return await page.screenshot({ type: 'jpeg', quality, clip: { x: 0, y: 0, width: w, height: h } })
  } finally {
    await page.close()
  }
}

/* ── Ledger + manifest (merge, never wipe: paid art is not derived art) ── */

const readJson = (path, fallback) => (existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : fallback)
/* NOT the replacer-array trick generate-heroes.mjs uses: a replacer array
   filters keys at EVERY level, and the ledger's values are objects — it would
   write `{}` for each entry. Sort the top level by hand instead. */
const writeJson = (path, obj) => {
  const sorted = Object.fromEntries(Object.entries(obj).sort(([a], [b]) => a.localeCompare(b)))
  writeFileSync(path, `${JSON.stringify(sorted, null, 2)}\n`)
}

const ledger = readJson(LEDGER, {})
const manifest = readJson(MANIFEST, { heroes: {}, heroesWide: {}, og: {}, subs: {} })

/* ── Jobs ────────────────────────────────────────────────────────────── */

/** relative output dir under public/ — samples go to a style-named sandbox. */
const relDir = (kind) => (OPTS.samples ? `/shift/ai/samples/${OPTS.style}/${kind}` : `/shift/ai/${kind}`)

function jobsFor(shifts) {
  const jobs = []
  for (const shift of shifts) {
    jobs.push({
      kind: 'hero', shift, prompt: heroPrompt(shift, FRAMES.hero), frame: FRAMES.hero,
      outs: [{ rel: `${relDir('heroes')}/${shift.slug}.jpg`, ...FRAMES.hero, manifestKey: ['heroes', shift.slug] }],
    })
    jobs.push({
      kind: 'wide', shift, prompt: heroPrompt(shift, FRAMES.wide), frame: FRAMES.wide,
      outs: [
        { rel: `${relDir('heroes-wide')}/${shift.slug}.jpg`, ...FRAMES.wide, manifestKey: ['heroesWide', shift.slug] },
        { rel: `${relDir('og')}/${shift.slug}.jpg`, ...OG, manifestKey: ['og', shift.slug] },
      ],
    })
    if (OPTS.subs) {
      for (const sub of shift.subs) {
        jobs.push({
          kind: 'sub', shift, sub, prompt: subPrompt(shift, sub), frame: FRAMES.sub,
          outs: [{
            rel: `${relDir('subs')}/${shift.slug}__${sub.slug}.jpg`,
            ...FRAMES.sub,
            manifestKey: ['subs', `${shift.slug}/${sub.slug}`],
          }],
        })
      }
    }
  }
  return jobs
}

function isFresh(job) {
  const hash = promptHash(job.prompt, job.frame.aspect)
  return job.outs.every((out) => {
    const entry = ledger[out.rel]
    return entry && entry.promptHash === hash && existsSync(resolve(ROOT, `public${out.rel}`))
  })
}

async function runJob(job, spent) {
  const hash = promptHash(job.prompt, job.frame.aspect)
  const master = await generateImage(job.prompt, job.frame.aspect)
  for (const out of job.outs) {
    const jpeg = await recompress(master, out)
    const abs = resolve(ROOT, `public${out.rel}`)
    mkdirSync(dirname(abs), { recursive: true })
    writeFileSync(abs, jpeg)
    ledger[out.rel] = {
      prompt: job.prompt,
      promptHash: hash,
      model: MODEL,
      style: OPTS.style,
      aspect: job.frame.aspect,
      generatedAt: new Date().toISOString(),
      costUsd: out === job.outs[0] ? COST_PER_IMAGE : 0, // crops of one master are free
    }
    if (!OPTS.samples) {
      const [section, key] = out.manifestKey
      manifest[section][key] = out.rel
    }
  }
  const label = job.kind === 'sub' ? `${job.shift.slug}/${job.sub.slug}` : `${job.shift.slug} (${job.kind})`
  console.log(`  ✓ ${label}  $${spent.total.toFixed(2)} spent`)
}

/** N workers over one shared queue — generation dominates, so modest N. */
async function runPool(jobs, size, spent) {
  const queue = [...jobs]
  const failures = []
  const worker = async () => {
    for (let job = queue.shift(); job; job = queue.shift()) {
      try {
        spent.total += COST_PER_IMAGE
        await runJob(job, spent)
      } catch (err) {
        spent.total -= COST_PER_IMAGE
        failures.push({ job, err })
        console.error(`  ✗ ${job.shift.slug}${job.sub ? `/${job.sub.slug}` : ''}: ${err.message}`)
      }
    }
  }
  await Promise.all(Array.from({ length: size }, worker))
  return failures
}

/* ── Prune (manual only — a transient API hiccup must never delete art) ── */

function prune(shifts) {
  const live = new Set()
  for (const s of shifts) {
    live.add(`/shift/ai/heroes/${s.slug}.jpg`)
    live.add(`/shift/ai/heroes-wide/${s.slug}.jpg`)
    live.add(`/shift/ai/og/${s.slug}.jpg`)
    for (const sub of s.subs) live.add(`/shift/ai/subs/${s.slug}__${sub.slug}.jpg`)
  }
  let removed = 0
  for (const rel of Object.keys(ledger)) {
    if (rel.startsWith('/shift/ai/samples/') || live.has(rel)) continue
    const abs = resolve(ROOT, `public${rel}`)
    if (existsSync(abs)) rmSync(abs)
    delete ledger[rel]
    removed += 1
  }
  for (const section of Object.keys(manifest)) {
    for (const [key, rel] of Object.entries(manifest[section])) {
      if (!live.has(rel)) delete manifest[section][key]
    }
  }
  console.log(`pruned ${removed} files no longer in the published map`)
}

/* ── Drive ───────────────────────────────────────────────────────────── */

async function main() {
  console.log(`map: ${ORIGIN}  style: ${OPTS.style}  model: ${MODEL}${OPTS.samples ? '  (samples sandbox)' : ''}`)
  const shifts = await keyShifts()
  if (!shifts.length) throw new Error('no key shifts matched — check --only/--spheres against the published map')

  if (OPTS.prune) {
    prune(shifts)
    writeJson(LEDGER, ledger)
    writeManifest()
    return
  }

  const jobs = jobsFor(shifts)
  const pending = OPTS.force ? jobs : jobs.filter((j) => !isFresh(j))
  const skipped = jobs.length - pending.length
  const estimate = pending.length * COST_PER_IMAGE

  console.log(`${jobs.length} generations (${shifts.length} key shifts${OPTS.subs ? `, ${jobs.filter((j) => j.kind === 'sub').length} subs` : ''}), ${skipped} already fresh, ${pending.length} to run ≈ $${estimate.toFixed(2)}`)

  if (OPTS.dryRun) {
    for (const job of pending) {
      const label = job.kind === 'sub' ? `${job.shift.slug}/${job.sub.slug}` : `${job.shift.slug} (${job.kind})`
      console.log(`\n── ${label} [${job.frame.aspect}] ${'─'.repeat(Math.max(1, 40 - label.length))}\n${job.prompt}`)
    }
    return
  }
  if (!pending.length) {
    console.log('nothing to do')
    return
  }

  const spent = { total: 0 }
  const failures = await runPool(pending, 4, spent)

  writeJson(LEDGER, ledger)
  if (!OPTS.samples) writeManifest()

  console.log(`\n${pending.length - failures.length}/${pending.length} generated, $${spent.total.toFixed(2)} spent`
    + (OPTS.samples ? `\nsamples → public${relDir('')} (manifest untouched — pick a style, then rerun without --samples)` : ''))
  if (failures.length) {
    console.error(`${failures.length} failed — rerun the same command; fresh files are skipped automatically`)
    process.exitCode = 1
  }
}

function writeManifest() {
  const sorted = {}
  for (const section of ['heroes', 'heroesWide', 'og', 'subs']) {
    sorted[section] = Object.fromEntries(Object.entries(manifest[section] ?? {}).sort(([a], [b]) => a.localeCompare(b)))
  }
  writeFileSync(MANIFEST, `${JSON.stringify(sorted, null, 2)}\n`)
}

try {
  await main()
} finally {
  if (browser) await browser.close()
}
