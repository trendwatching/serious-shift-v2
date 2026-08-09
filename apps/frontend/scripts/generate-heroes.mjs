#!/usr/bin/env node
/* ════════════════════════════════════════════════════════════════════════
 * Hero art for every key shift, drawn as SVG.
 *
 * The two hand-made heroes in public/shift are the bar: a graded field in the
 * sphere's own ramp, near-black silhouetted architecture and crowd, a shaft of
 * pale light, a column of matter falling out of something suspended overhead,
 * and heavy poster grain over all of it. That composition is what carries the
 * meaning — a shift arriving from above and landing on people — and it is
 * reproducible in vector form. The photographic rendering is not, so this does
 * not attempt it: these are posters in the same family, not imitations of a
 * photograph.
 *
 * Everything is derived from the slug, so the same shift always gets the same
 * poster and a rerun is a no-op in git. Nothing here is random at runtime.
 *
 *   node scripts/generate-heroes.mjs [--origin https://…]
 *
 * Writes public/shift/heroes/<slug>.svg + src/lib/heroes.json for key shifts,
 * and public/shift/subs/<key>__<sub>.svg + src/lib/sub-art.json for sub-shifts.
 * Both are manifests rather than path templates, so a shift published since the
 * last run falls back to its gradient rather than requesting a file that does
 * not exist.
 * ════════════════════════════════════════════════════════════════════════ */

import { mkdirSync, writeFileSync, readdirSync, rmSync, existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHash } from 'node:crypto'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT_DIR = resolve(ROOT, 'public/shift/heroes')
const MANIFEST = resolve(ROOT, 'src/lib/heroes.json')
const SUB_DIR = resolve(ROOT, 'public/shift/subs')
const SUB_MANIFEST = resolve(ROOT, 'src/lib/sub-art.json')
/* The landscape cut of the same 51 posters, for the desktop hero band. There is
   deliberately no wide set for the sub-shift fragments: those are TILE art, shown
   in a 152px square box, and a sub-shift PAGE inherits its parent's poster
   (see SUB_GEN in src/lib/useDomains.js). One wide set serves both pages. */
const WIDE_DIR = resolve(ROOT, 'public/shift/heroes-wide')
const WIDE_MANIFEST = resolve(ROOT, 'src/lib/heroes-wide.json')

/* ── The frame ────────────────────────────────────────────────────────────
 * A poster is drawn twice: portrait for the phone, landscape for the desktop
 * hero band, which is a letterbox roughly 2.7:1. Painting the portrait art into
 * that band with `cover` scaled it 1.8x and showed about 30% of the picture —
 * the ring and the tops of the towers, with the crowd the whole composition
 * lands on cropped clean off the bottom. No `background-position` can reveal
 * what the box does not contain, so the second frame has to be drawn.
 *
 * `poster()` already expresses every position as a fraction of W and H, so the
 * composition recomposes on its own. What does NOT recompose is absolute size:
 * a 38px shoulder is a person at 800 wide and a speck at 1600. So each absolute
 * length is multiplied by the knob that governs it.
 *
 * EVERY KNOB IS EXACTLY 1 IN THE PORTRAIT FRAME. That is the contract that
 * keeps the 51 committed SVGs byte-identical: `x * 1` is `x` bit-for-bit, so a
 * multiplied expression is unchanged, whereas a rewritten one (`W*0.21` as
 * `H*0.168`) is not. Multiply; never re-derive. scripts/check-frame.mjs proves
 * it by hashing the portrait output against what is on disk.
 * --------------------------------------------------------------------- */
const FRAMES = {
  // The design canvas. Knobs are 1 by definition.
  tall: { W: 800, H: 1000, u: 1, pop: 1, fx: 1 },
  // 2.667:1. The desktop band runs 2.23:1 at 1024 through 2.70 at 1440 to
  // 3.10 at 1920, so this sits on the common laptop with a 1% crop.
  // `u` under 1 because the frame is 2x wider but only 0.6x taller: figures
  // sized for the portrait would tower over a 600px-high scene.
  wide: { W: 1600, H: 600, u: 0.74, pop: 1.7, fx: 0.54 },
  // The link-preview card. 1200x630 is what every unfurler crops to, and it is
  // 1.905:1 — between the portrait and the desktop band, so the knobs sit
  // between theirs too. Every route shared ONE generic logo card before this,
  // so a shift shared into Slack previewed as the site rather than as itself.
  og: { W: 1200, H: 630, u: 0.86, pop: 1.3, fx: 0.72 },
}

let W = FRAMES.tall.W
let H = FRAMES.tall.H
// Horizontal and vertical unit, derived; `u` sizes world objects, `pop` scales
// counts of things repeating across the frame, `fx` the ring and its beam.
// `fx`, not `focal`: poster() declares a local `focal` for the focal SVG, which
// silently shadowed the knob and multiplied every radius by an empty string.
// The ring came out r="0" on all 51 posters.
let ux = 1
let uy = 1
let u = 1
let pop = 1
let fx = 1

function setFrame(frame) {
  ;({ W, H, u, pop, fx } = frame)
  ux = W / FRAMES.tall.W
  uy = H / FRAMES.tall.H
}

/* ── Palettes ───────────────────────────────────────────────────────────
 * The four stops are each sphere's sunset ramp from styles/tokens.css, so a
 * poster and the page it sits on are lit by the same light. `dark` is the
 * silhouette ink — the ramp's own hue driven almost to black, which keeps the
 * shapes from reading as neutral grey holes punched in the field.
 * -------------------------------------------------------------------- */
const PALETTE = {
  society:       { hot: '#FF007A', mid: '#E8006F', warm: '#F2734A', light: '#FDFF85', dark: '#39001F' },
  economy:       { hot: '#0FA6FF', mid: '#0A7FDA', warm: '#23B9A6', light: '#E6FF9C', dark: '#022638' },
  organizations: { hot: '#C2C64F', mid: '#9A9A43', warm: '#4E9A62', light: '#EFFAB4', dark: '#20260A' },
  consumers:     { hot: '#FF6A1F', mid: '#E74707', warm: '#F2A03A', light: '#FDFF85', dark: '#3B1101' },
}

/* Which built forms belong to which sphere. A society shift gets institutions,
   an economy shift gets a trading board, organizations get slabs and networks,
   consumers get the street. This is the only place the four differ in shape
   rather than only in colour. */
const FORMS = {
  society:       ['colonnade', 'towers'],
  economy:       ['board', 'towers'],
  organizations: ['monoliths', 'lattice'],
  consumers:     ['towers', 'board'],
}

/* Weighted, not uniform. `descent` is the composition both hand-made heroes
   use, so it is the house shape; the other two exist so 58 posters in a row
   do not read as one poster recoloured. */
const PILLARS = ['descent', 'descent', 'descent', 'horizon', 'structure']

/* ── Determinism ─────────────────────────────────────────────────────── */

/** mulberry32, seeded off the slug so every choice below is reproducible. */
function rng(slug) {
  let a = parseInt(createHash('sha256').update(slug).digest('hex').slice(0, 8), 16)
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const n = (v) => Math.round(v * 10) / 10
const pick = (r, xs) => xs[Math.floor(r() * xs.length) % xs.length]
const between = (r, lo, hi) => lo + r() * (hi - lo)

/* ── Motifs ──────────────────────────────────────────────────────────── */

/** A pedimented institution: steps, columns, roof. Society's building. */
function colonnade(x, y, w, h, r) {
  const cols = 5 + Math.floor(r() * 3)
  const capH = h * 0.16
  const stepH = h * 0.1
  const shaftTop = y + capH
  const shaftH = h - capH - stepH
  const gap = w / cols
  const colW = gap * 0.42
  let s = `<polygon points="${n(x - w * 0.06)},${n(y + capH)} ${n(x + w / 2)},${n(y)} ${n(x + w * 1.06)},${n(y + capH)}"/>`
  s += `<rect x="${n(x - w * 0.04)}" y="${n(y + capH)}" width="${n(w * 1.08)}" height="${n(capH * 0.36)}"/>`
  for (let i = 0; i < cols; i += 1) {
    s += `<rect x="${n(x + gap * i + (gap - colW) / 2)}" y="${n(shaftTop + capH * 0.36)}" width="${n(colW)}" height="${n(shaftH)}"/>`
  }
  s += `<rect x="${n(x - w * 0.1)}" y="${n(y + h - stepH)}" width="${n(w * 1.2)}" height="${n(stepH)}"/>`
  // The flagpole. Small, but it is what makes the block read as civic.
  const px = x + w * 0.12
  s += `<rect x="${n(px)}" y="${n(y - h * 0.42)}" width="${n(3 * ux)}" height="${n(h * 0.42)}"/>`
  s += `<polygon points="${n(px + 3 * ux)},${n(y - h * 0.42)} ${n(px + w * 0.2)},${n(y - h * 0.36)} ${n(px + 3 * ux)},${n(y - h * 0.3)}"/>`
  return s
}

/** A skyline block: slabs, a few setbacks, the odd mast. */
function towers(x, y, w, h, r, lit) {
  // `pop` on the count, not on the width: a wider frame wants MORE slabs of
  // the same size, not the same five stretched across it.
  const count = Math.max(2, Math.round((5 + Math.floor(r() * 4)) * pop))
  const unit = w / count
  let s = ''
  for (let i = 0; i < count; i += 1) {
    const bw = unit * between(r, 0.62, 0.94)
    const bh = h * between(r, 0.42, 1)
    const bx = x + unit * i + (unit - bw) / 2
    const by = y + h - bh
    s += `<rect x="${n(bx)}" y="${n(by)}" width="${n(bw)}" height="${n(bh)}"/>`
    if (r() > 0.55) {
      const sw = bw * 0.5
      s += `<rect x="${n(bx + (bw - sw) / 2)}" y="${n(by - bh * 0.18)}" width="${n(sw)}" height="${n(bh * 0.18)}"/>`
    }
    if (r() > 0.75) s += `<rect x="${n(bx + bw / 2 - 1.5 * ux)}" y="${n(by - h * 0.14)}" width="${n(3 * ux)}" height="${n(h * 0.14)}"/>`
    // Windows are the only place light gets to sit inside a silhouette. Sparse
    // on purpose: a fully gridded tower stops being a silhouette.
    if (lit) {
      const rows = Math.floor(bh / (26 * uy))
      const colsW = Math.max(2, Math.floor(bw / (18 * ux)))
      for (let ry = 1; ry < rows; ry += 1) {
        for (let cx = 0; cx < colsW; cx += 1) {
          if (r() > 0.89) {
            s += `<rect class="lit" x="${n(bx + 6 * ux + cx * 18 * ux)}" y="${n(by + 12 * uy + ry * 26 * uy)}" width="${n(6 * ux)}" height="${n(9 * uy)}"/>`
          }
        }
      }
    }
  }
  return s
}

/** A trading board: framed panel, a line that only goes one way. */
function board(x, y, w, h, r) {
  let s = `<rect x="${n(x)}" y="${n(y)}" width="${n(w)}" height="${n(h)}"/>`
  const pts = []
  const steps = 9
  let v = between(r, 0.18, 0.3)
  for (let i = 0; i <= steps; i += 1) {
    v += between(r, -0.03, 0.13)
    pts.push(`${n(x + w * 0.08 + (w * 0.62 * i) / steps)},${n(y + h * 0.3 + Math.min(h * 0.52, h * v))}`)
  }
  s += `<polyline class="lit-stroke" points="${pts.join(' ')}" fill="none" stroke-width="${n(4 * ux)}"/>`
  for (let i = 0; i < 5; i += 1) {
    s += `<rect class="lit" x="${n(x + w * 0.78)}" y="${n(y + h * 0.26 + i * h * 0.13)}" width="${n(w * 0.14)}" height="${n(5 * uy)}"/>`
  }
  return s
}

/** Stepped slabs. Organisations: mass without a face. */
function monoliths(x, y, w, h, r) {
  const count = 3 + Math.floor(r() * 3)
  const unit = w / count
  let s = ''
  for (let i = 0; i < count; i += 1) {
    const bh = h * between(r, 0.5, 1)
    const bw = unit * 0.86
    const bx = x + unit * i + (unit - bw) / 2
    let by = y + h - bh
    s += `<rect x="${n(bx)}" y="${n(by)}" width="${n(bw)}" height="${n(bh)}"/>`
    // Each slab steps back once, which is what separates the pile from a
    // skyline: it reads as one accreted structure rather than many buildings.
    const inset = bw * 0.16
    by -= bh * 0.22
    s += `<rect x="${n(bx + inset)}" y="${n(by)}" width="${n(bw - inset * 2)}" height="${n(bh * 0.24)}"/>`
  }
  return s
}

/** A network: nodes on a loose grid, orthogonal links, a few of them lit. */
function lattice(x, y, w, h, r) {
  const cols = Math.max(2, Math.round(5 * pop))
  const rows = 3
  const nodes = []
  for (let cy = 0; cy < rows; cy += 1) {
    for (let cx = 0; cx < cols; cx += 1) {
      nodes.push({
        x: x + (w * (cx + 0.5)) / cols + between(r, -14, 14) * ux,
        y: y + (h * (cy + 0.5)) / rows + between(r, -12, 12) * uy,
      })
    }
  }
  let s = ''
  for (let i = 0; i < nodes.length; i += 1) {
    const a = nodes[i]
    const right = (i + 1) % cols !== 0 ? nodes[i + 1] : null
    const down = nodes[i + cols]
    for (const b of [right, down]) {
      if (!b || r() > 0.72) continue
      s += `<path d="M ${n(a.x)} ${n(a.y)} L ${n(b.x)} ${n(a.y)} L ${n(b.x)} ${n(b.y)}" fill="none" stroke-width="${n(2.5 * ux)}"/>`
    }
  }
  for (const p of nodes) {
    s += r() > 0.78
      ? `<circle class="lit" cx="${n(p.x)}" cy="${n(p.y)}" r="${n(6 * u)}"/>`
      : `<circle cx="${n(p.x)}" cy="${n(p.y)}" r="${n(5 * u)}"/>`
  }
  return s
}

/**
 * The suspended thing: an open hoop on chains, seen slightly from below.
 *
 * It is stroked rather than filled. A filled ellipse with a lighter ellipse cut
 * out of it reads as a lid — a bright disc of paint — and the whole point of the
 * shape is that it is a mouth with nothing holding it closed.
 */
function ring(cx, cy, rx) {
  const ry = rx * 0.3
  const band = rx * 0.15
  let s = ''
  const chain = rx * 0.74
  for (const dx of [-chain, chain]) {
    s += `<path d="M ${n(cx + dx * 0.38)} 0 L ${n(cx + dx)} ${n(cy)}" fill="none" stroke-width="${n(5 * ux)}"/>`
  }
  // The rim, then the front of the band, so the hoop has depth.
  s += `<ellipse cx="${n(cx)}" cy="${n(cy)}" rx="${n(rx)}" ry="${n(ry)}" fill="none" stroke-width="${n(band)}"/>`
  s += `<path d="M ${n(cx - rx)} ${n(cy)} A ${n(rx)} ${n(ry)} 0 0 0 ${n(cx + rx)} ${n(cy)} L ${n(cx + rx)} ${n(cy + band * 0.9)} A ${n(rx)} ${n(ry)} 0 0 1 ${n(cx - rx)} ${n(cy + band * 0.9)} Z" stroke-width="0"/>`
  return s
}

/**
 * The crowd. Two depths, because a single row of evenly-spaced figures reads as
 * a repeating pattern rather than as people: a dense far rank of heads and
 * shoulders that the near rank overlaps, and a near rank of large figures
 * rising off the bottom edge with irregular spacing and no two the same size.
 * Nobody has a face. That is the point of the reference art — the crowd is what
 * the shift lands on, not who it lands on.
 */
function crowd(baseY, r) {
  /**
   * One figure: a narrow head sitting proud of a wider shoulder line.
   *
   * The shoulder curve has to peak well below the head or it swallows it, and
   * the result is a rounded slab — a row of tombstones, which is what the
   * previous geometry produced. The head is the only thing that makes the shape
   * read as a person, so it gets clear air above the shoulders.
   */
  const figure = (x, y, scale) => {
    const hr = 15 * scale * u
    const sw = 38 * scale * u
    const sy = y - 34 * scale * u
    const hy = sy - hr * 1.15
    return (
      `<circle cx="${n(x)}" cy="${n(hy)}" r="${n(hr)}"/>` +
      `<path d="M ${n(x - sw)} ${n(H + 40 * u)} L ${n(x - sw)} ${n(sy)}` +
      ` C ${n(x - sw * 0.62)} ${n(sy - 11 * scale * u)} ${n(x - hr * 0.8)} ${n(sy - 15 * scale * u)} ${n(x)} ${n(sy - 15 * scale * u)}` +
      ` C ${n(x + hr * 0.8)} ${n(sy - 15 * scale * u)} ${n(x + sw * 0.62)} ${n(sy - 11 * scale * u)} ${n(x + sw)} ${n(sy)}` +
      ` L ${n(x + sw)} ${n(H + 40 * u)} Z"/>`
    )
  }

  // Far rank first so the near rank cuts into it. Scale and standing height
  // both vary widely: evenly-sized figures on one baseline produce a serrated
  // band that reads as a hedge, which is exactly what the first pass looked
  // like. The near rank is roughly three times the far one, so the two ranks
  // are unmistakably at different distances rather than merely different sizes.
  let far = ''
  for (let x = -40 * u; x < W + 40 * u; x += between(r, 34, 62) * u) {
    far += figure(x, baseY - between(r, 34, 96) * u, between(r, 0.34, 0.54))
  }
  let near = ''
  for (let x = -60 * u; x < W + 60 * u; x += between(r, 118, 176) * u) {
    near += figure(x + between(r, -18, 18) * u, baseY + between(r, 10, 46) * u, between(r, 1.2, 1.7))
  }
  return { far, near }
}

/** The fall: matter leaving the suspended thing and thinning as it descends. */
function particles(cx, top, bottom, r) {
  let s = ''
  const rows = Math.max(2, Math.round(26 * uy))
  for (let i = 0; i < rows; i += 1) {
    const t = i / (rows - 1)
    const y = top + (bottom - top) * t
    const spread = 26 * u + t * t * 150 * u
    const per = Math.max(1, Math.round(6 - t * 4))
    for (let k = 0; k < per; k += 1) {
      const size = Math.max(1.5 * u, 6 * u - t * 4 * u) * between(r, 0.7, 1.3)
      const x = cx + between(r, -spread, spread)
      s += r() > 0.4
        ? `<rect x="${n(x)}" y="${n(y)}" width="${n(size)}" height="${n(size)}" transform="rotate(${n(between(r, 0, 90))} ${n(x)} ${n(y)})"/>`
        : `<circle cx="${n(x)}" cy="${n(y)}" r="${n(size / 2)}"/>`
    }
  }
  return s
}

/** Ground plane in perspective. Reads as distance without drawing any. */
function groundGrid(y, vanishX) {
  let s = ''
  for (let i = -7; i <= 7; i += 1) {
    s += `<path d="M ${n(vanishX + i * 22 * ux)} ${n(y)} L ${n(vanishX + i * 210 * ux)} ${H}" fill="none" stroke-width="${n(2 * ux)}"/>`
  }
  for (let i = 1; i <= 7; i += 1) {
    const ly = y + ((H - y) * i * i) / 49
    s += `<path d="M 0 ${n(ly)} L ${W} ${n(ly)}" fill="none" stroke-width="${n(2 * ux)}"/>`
  }
  return s
}

/* ── Composition ─────────────────────────────────────────────────────── */

function poster(slug, sphere, frame = FRAMES.tall) {
  // Before anything reads W/H or draws — every position below is a fraction
  // of the frame, so this one call recomposes the whole poster.
  setFrame(frame)
  const r = rng(slug)
  const p = PALETTE[sphere] ?? PALETTE.society
  const pillar = PILLARS[Math.floor(r() * PILLARS.length)]
  // Society's civic form is the point of the sphere, so it is not left to a
  // coin flip that a fifth of the time gives it an anonymous skyline.
  const form = sphere === 'society' && pillar !== 'structure'
    ? 'colonnade'
    : pick(r, FORMS[sphere] ?? FORMS.society)
  const cx = W * between(r, 0.42, 0.58)
  const id = slug.replace(/[^a-z0-9]/g, '')

  const draw = (body, fill, opacity = 1, extra = '') =>
    body ? `<g fill="${fill}" stroke="${fill}" fill-opacity="${opacity}" stroke-opacity="${opacity}" ${extra}>${body}</g>` : ''

  const builtForm = (x, y, w, h, lit) => {
    if (form === 'colonnade') return colonnade(x, y, w, h, r)
    if (form === 'board') return board(x, y, w, h, r)
    if (form === 'monoliths') return monoliths(x, y, w, h, r)
    if (form === 'lattice') return lattice(x, y, w, h, r)
    return towers(x, y, w, h, r, lit)
  }

  // Four depths, each a step darker than the one behind it, with a band of haze
  // between the far and mid ranks. Depth is what stops the poster reading as a
  // sticker sheet: without it every silhouette sits on the same plane and the
  // gradient behind them is just a backdrop.
  const far = draw(towers(-40, H * 0.4, W + 80, H * 0.28, r, false), p.dark, 0.17)
  const haze = `<rect x="0" y="${n(H * 0.36)}" width="${W}" height="${n(H * 0.3)}" fill="url(#haze${id})"/>`

  let mid = ''
  let focal = ''
  let light = ''

  if (pillar === 'descent') {
    const ringY = H * between(r, 0.19, 0.25)
    const rx = W * between(r, 0.21, 0.27) * fx
    light = `<polygon points="${n(cx - rx * 0.55)},${n(ringY)} ${n(cx + rx * 0.55)},${n(ringY)} ${n(cx + rx * 2.1)},${H} ${n(cx - rx * 2.1)},${H}" fill="url(#beam${id})"/>`
    focal = draw(ring(cx, ringY, rx), p.dark, 0.96)
    focal += draw(particles(cx, ringY + rx * 0.34, H * 0.9, r), p.dark, 0.82)
    // The flanking forms run off both edges of the frame. In the reference the
    // architecture is cropped, never politely inset — that crop is most of why
    // it reads as a photograph of somewhere rather than a diagram of nowhere.
    mid = draw(builtForm(-W * 0.06, H * 0.44, W * 0.42, H * 0.32, true), p.dark, 0.93)
    mid += draw(builtForm(W * 0.64, H * 0.47, W * 0.42, H * 0.3, true), p.dark, 0.93)
  } else if (pillar === 'horizon') {
    const discY = H * between(r, 0.19, 0.27)
    const dr = W * between(r, 0.15, 0.21) * fx
    light = `<circle cx="${n(cx)}" cy="${n(discY)}" r="${n(dr)}" fill="url(#disc${id})"/>`
    light += draw(groundGrid(H * 0.72, cx), p.light, 0.14)
    focal = draw(builtForm(W * 0.1, H * 0.42, W * 0.8, H * 0.34, true), p.dark, 0.94)
    mid = draw(towers(-30, H * 0.54, W + 60, H * 0.22, r, false), p.dark, 0.58)
    // Even the horizon gets a shaft. It is the one gesture every poster shares.
    light += `<polygon points="${n(cx - dr * 0.9)},${n(discY)} ${n(cx + dr * 0.9)},${n(discY)} ${n(cx + dr * 2.4)},${H} ${n(cx - dr * 2.4)},${H}" fill="url(#beam${id})" opacity="0.55"/>`
  } else {
    const topY = H * 0.14
    light = `<polygon points="${n(cx - W * 0.11 * fx)},${n(topY)} ${n(cx + W * 0.11 * fx)},${n(topY)} ${n(cx + W * 0.44 * fx)},${H} ${n(cx - W * 0.44 * fx)},${H}" fill="url(#beam${id})"/>`
    focal = draw(builtForm(W * 0.08, topY, W * 0.84, H * 0.54, true), p.dark, 0.95)
    mid = draw(lattice(W * 0.04, H * 0.18, W * 0.92, H * 0.24, r), p.light, 0.28)
    focal += draw(particles(cx, H * 0.5, H * 0.9, r), p.dark, 0.6)
  }

  const { far: crowdFar, near: crowdNear } = crowd(H * 0.95, r)
  const people = draw(crowdFar, p.dark, 0.72) + draw(crowdNear, p.dark, 0.98)

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<title>${slug}</title>
<defs>
<linearGradient id="sky${id}" x1="0" y1="0" x2="0.55" y2="1">
<stop offset="0" stop-color="${p.hot}"/><stop offset="0.42" stop-color="${p.mid}"/>
<stop offset="0.8" stop-color="${p.warm}"/><stop offset="1" stop-color="${p.light}"/>
</linearGradient>
<linearGradient id="beam${id}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="${p.light}" stop-opacity="0.72"/>
<stop offset="0.55" stop-color="${p.light}" stop-opacity="0.3"/>
<stop offset="1" stop-color="${p.light}" stop-opacity="0"/>
</linearGradient>
<radialGradient id="disc${id}">
<stop offset="0.72" stop-color="${p.light}" stop-opacity="0.92"/>
<stop offset="0.86" stop-color="${p.light}" stop-opacity="0.34"/>
<stop offset="1" stop-color="${p.light}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="glow${id}" cx="${n(cx / W * 100)}%" cy="34%" r="62%">
<stop offset="0" stop-color="${p.light}" stop-opacity="0.42"/>
<stop offset="1" stop-color="${p.light}" stop-opacity="0"/>
</radialGradient>
<linearGradient id="haze${id}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="${p.warm}" stop-opacity="0"/>
<stop offset="0.5" stop-color="${p.warm}" stop-opacity="0.42"/>
<stop offset="1" stop-color="${p.warm}" stop-opacity="0"/>
</linearGradient>
<radialGradient id="vig${id}" cx="50%" cy="42%" r="72%">
<stop offset="0.55" stop-color="${p.dark}" stop-opacity="0"/>
<stop offset="1" stop-color="${p.dark}" stop-opacity="0.5"/>
</radialGradient>
<!-- Poster grain. Two frequencies: a fine tooth that sits on the whole field
     and a coarse mottle that keeps the flat gradient from looking printed by a
     browser. Both are filters on a rect, so they cost nothing to download. -->
<filter id="soft${id}" x="-20%" y="-20%" width="140%" height="140%">
<feGaussianBlur stdDeviation="${n(16 * ux)}"/>
</filter>
<filter id="fine${id}" x="0" y="0" width="100%" height="100%">
<feTurbulence type="fractalNoise" baseFrequency="${0.85 / ux}" numOctaves="3" seed="7" result="t"/>
<feColorMatrix in="t" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.4 0 0 0 0"/>
</filter>
<filter id="coarse${id}" x="0" y="0" width="100%" height="100%">
<feTurbulence type="fractalNoise" baseFrequency="${0.05 / ux}" numOctaves="4" seed="19" result="t"/>
<feColorMatrix in="t" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.7 0 0 0 0"/>
</filter>
<style>.lit{fill:${p.light};stroke:none;fill-opacity:0.22}.lit-stroke{stroke:${p.light};stroke-opacity:0.85}</style>
</defs>
<rect width="${W}" height="${H}" fill="url(#sky${id})"/>
<rect width="${W}" height="${H}" fill="url(#glow${id})"/>
${far}
${haze}
<g filter="url(#soft${id})">${light}</g>
${mid}
${focal}
${people}
<rect width="${W}" height="${H}" fill="url(#vig${id})"/>
<rect width="${W}" height="${H}" filter="url(#coarse${id})" opacity="0.22" style="mix-blend-mode:overlay"/>
<rect width="${W}" height="${H}" filter="url(#fine${id})" opacity="0.34" style="mix-blend-mode:multiply"/>
<rect width="${W}" height="${H}" filter="url(#fine${id})" opacity="0.16" style="mix-blend-mode:screen"/>
</svg>
`
}

/* ════════════════════════════════════════════════════════════════════════
 * Sub-shift art — the same world, seen close.
 *
 * A sub-shift tile shows its artwork in a 152×148 box, and the key-shift poster
 * is unreadable at that size: a hoop, a skyline, a shaft and a crowd become
 * mush. Shrinking it further would have been the wrong instinct anyway. The
 * relationship between the two levels is already the answer — a key shift is
 * the wide scene, so a sub-shift is a DETAIL cut out of it. One motif, drawn far
 * too large for its frame and running off at least two edges, on the parent's
 * sunset ramp.
 *
 * That reads at 152px, it is unmistakably the same world as the poster above it,
 * and the crop is what says "you are one level in".
 *
 * The same square serves the sub-shift page's own hero, so the tile a reader
 * taps and the page it opens carry the same image.
 * ════════════════════════════════════════════════════════════════════════ */

const F = 640

/**
 * Which fragments each sphere draws from, in the order it uses them.
 *
 * Five kinds, dealt round-robin down a key shift's sub-shifts rather than picked
 * per slug. Picking independently is what the first pass did, and with a
 * weighted list it put three near-identical colonnades in one five-card stack:
 * every choice was defensible alone and the page was repetitive anyway. Five
 * kinds covers the usual five sub-shifts with no repeat at all, and the sphere
 * keeps its signature because the vocabulary itself differs — Society opens on
 * the institution, Economy on the falling line.
 */
const FRAGMENTS = {
  society:       ['cornice', 'rim', 'figures', 'fall', 'shaft'],
  economy:       ['descent', 'shaft', 'fall', 'slabs', 'rim'],
  organizations: ['slabs', 'shaft', 'rim', 'cornice', 'fall'],
  consumers:     ['figures', 'fall', 'shaft', 'rim', 'descent'],
}

/** A cornice and two column shafts, cropped hard. Society, up close. */
function fragCornice(r) {
  const capY = F * between(r, 0.16, 0.24)
  const capH = F * 0.13
  let s = `<rect x="${n(-F * 0.1)}" y="${n(capY)}" width="${n(F * 1.2)}" height="${n(capH)}"/>`
  s += `<rect x="${n(-F * 0.1)}" y="${n(capY + capH)}" width="${n(F * 1.2)}" height="${n(capH * 0.3)}"/>`
  const cols = 3
  const gap = F / cols
  for (let i = 0; i < cols; i += 1) {
    const w = gap * between(r, 0.4, 0.5)
    s += `<rect x="${n(gap * i + (gap - w) / 2)}" y="${n(capY + capH * 1.3)}" width="${n(w)}" height="${n(F)}"/>`
  }
  return s
}

/** One arc of the hoop, big enough that only part of it fits. */
function fragRim(r) {
  const cy = F * between(r, 0.2, 0.3)
  const rx = F * between(r, 0.7, 0.88)
  const ry = rx * 0.36
  const band = F * 0.075
  let s = `<ellipse cx="${n(F / 2)}" cy="${n(cy)}" rx="${n(rx)}" ry="${n(ry)}" fill="none" stroke-width="${n(band)}"/>`
  for (let i = 0; i < 34; i += 1) {
    const t = i / 33
    const y = cy + ry + t * (F - cy - ry)
    const size = Math.max(4, 20 - t * 15)
    const x = F / 2 + between(r, -1, 1) * (40 + t * 190)
    s += `<rect x="${n(x)}" y="${n(y)}" width="${n(size)}" height="${n(size)}" transform="rotate(${n(between(r, 0, 90))} ${n(x)} ${n(y)})"/>`
  }
  return s
}

/** Two slab edges running off the top and bottom, with the gap between them. */
function fragShaft(r) {
  const leftW = F * between(r, 0.26, 0.36)
  const rightX = F * between(r, 0.66, 0.76)
  let s = `<rect x="${n(-F * 0.1)}" y="${n(-F * 0.1)}" width="${n(leftW + F * 0.1)}" height="${n(F * 1.2)}"/>`
  s += `<rect x="${n(rightX)}" y="${n(F * between(r, -0.1, 0.12))}" width="${n(F * 1.2 - rightX)}" height="${n(F * 1.3)}"/>`
  // A single setback on each side, so the two edges are not a mirror pair.
  s += `<rect x="${n(leftW)}" y="${n(F * between(r, 0.3, 0.5))}" width="${n(F * 0.09)}" height="${n(F)}"/>`
  return s
}

/** Overlapping slabs with a lit top edge each. Organisations, up close. */
function fragSlabs(r) {
  let s = ''
  const count = 3
  for (let i = 0; i < count; i += 1) {
    const w = F * between(r, 0.34, 0.46)
    const x = F * (0.02 + i * 0.3) + between(r, -18, 18)
    const y = F * between(r, 0.18, 0.42)
    s += `<rect x="${n(x)}" y="${n(y)}" width="${n(w)}" height="${n(F)}"/>`
    s += `<rect class="lit" x="${n(x)}" y="${n(y)}" width="${n(w)}" height="6"/>`
  }
  return s
}

/** A line that only goes one way, at the scale of the whole frame. */
function fragDescent(r) {
  const pts = []
  const steps = 7
  let v = between(r, 0.04, 0.3)
  for (let i = 0; i <= steps; i += 1) {
    v += between(r, -0.06, 0.2)
    pts.push(`${n(F * 0.02 + (F * 0.96 * i) / steps)},${n(F * (0.08 + Math.min(0.76, v)) + between(r, -14, 14))}`)
  }
  let s = `<rect x="${n(-F * 0.1)}" y="${n(F * 0.86)}" width="${n(F * 1.2)}" height="${n(F * 0.3)}"/>`
  s += `<polyline points="${pts.join(' ')}" fill="none" stroke-width="${n(F * 0.05)}" stroke-linejoin="round"/>`
  for (let i = 1; i <= 4; i += 1) {
    s += `<rect class="lit" x="0" y="${n((F * 0.86 * i) / 5)}" width="${F}" height="3"/>`
  }
  return s
}

/** Matter falling, close enough that the individual pieces have edges. */
function fragFall(r) {
  let s = ''
  for (let i = 0; i < 64; i += 1) {
    const t = i / 63
    const y = -F * 0.05 + t * F * 1.1
    const size = Math.max(5, 30 - t * 24)
    const x = F * between(r, 0.05, 0.95) * (1 - t * 0.1) + t * 24
    s += r() > 0.4
      ? `<rect x="${n(x)}" y="${n(y)}" width="${n(size)}" height="${n(size)}" transform="rotate(${n(between(r, 0, 90))} ${n(x)} ${n(y)})"/>`
      : `<circle cx="${n(x)}" cy="${n(y)}" r="${n(size / 2)}"/>`
  }
  return s
}

/** Two figures, cropped at the shoulder. The crowd from inside it. */
function fragFigures(r) {
  const one = (x, y, scale) => {
    const hr = 78 * scale
    const sw = 190 * scale
    const sy = y
    return (
      `<circle cx="${n(x)}" cy="${n(sy - hr * 1.35)}" r="${n(hr)}"/>` +
      `<path d="M ${n(x - sw)} ${F + 40} L ${n(x - sw)} ${n(sy)}` +
      ` C ${n(x - sw * 0.6)} ${n(sy - 56 * scale)} ${n(x - hr * 0.8)} ${n(sy - 76 * scale)} ${n(x)} ${n(sy - 76 * scale)}` +
      ` C ${n(x + hr * 0.8)} ${n(sy - 76 * scale)} ${n(x + sw * 0.6)} ${n(sy - 56 * scale)} ${n(x + sw)} ${n(sy)}` +
      ` L ${n(x + sw)} ${F + 40} Z"/>`
    )
  }
  return {
    back: one(F * between(r, 0.16, 0.3), F * between(r, 0.62, 0.72), between(r, 0.62, 0.78)),
    front: one(F * between(r, 0.6, 0.78), F * between(r, 0.78, 0.9), between(r, 1, 1.2)),
  }
}

/** The blurred wedge of light. Every fragment gets one, as the posters do. */
const beam = (id, xTop, wTop, yTop, wBot) =>
  `<polygon points="${xTop - wTop},${yTop} ${xTop + wTop},${yTop} ${xTop + wBot},${F} ${xTop - wBot},${F}" fill="url(#b${id})" filter="url(#s${id})"/>`

function fragment(key, sphere, index) {
  const r = rng(key)
  const p = PALETTE[sphere] ?? PALETTE.society
  const kinds = FRAGMENTS[sphere] ?? FRAGMENTS.society
  // Offset by the parent so two key shifts in a sphere do not open on the same
  // picture; stepped by position so one stack never repeats itself.
  const offset = parseInt(createHash('sha256').update(key.split('/')[0]).digest('hex').slice(0, 4), 16)
  const kind = kinds[(index + offset) % kinds.length]
  const id = key.replace(/[^a-z0-9]/g, '')
  const draw = (body, fill, opacity = 1) =>
    body ? `<g fill="${fill}" stroke="${fill}" fill-opacity="${opacity}" stroke-opacity="${opacity}">${body}</g>` : ''

  let art = ''
  let light = ''
  if (kind === 'cornice') {
    light = beam(id, F * 0.5, F * 0.2, F * 0.3, F * 0.34)
    art = draw(fragCornice(r), p.dark, 0.97)
  } else if (kind === 'rim') {
    light = beam(id, F * 0.5, F * 0.22, F * 0.3, F * 0.42)
    art = draw(fragRim(r), p.dark, 0.96)
  } else if (kind === 'shaft') {
    light = beam(id, F * 0.52, F * 0.16, 0, F * 0.24)
    art = draw(fragShaft(r), p.dark, 0.97)
  } else if (kind === 'slabs') {
    light = beam(id, F * 0.5, F * 0.3, 0, F * 0.36)
    art = draw(fragSlabs(r), p.dark, 0.96)
  } else if (kind === 'descent') {
    art = draw(fragDescent(r), p.dark, 0.97)
  } else if (kind === 'fall') {
    light = beam(id, F * 0.5, F * 0.26, 0, F * 0.44)
    art = draw(fragFall(r), p.dark, 0.92)
  } else {
    light = beam(id, F * 0.44, F * 0.24, 0, F * 0.4)
    const { back, front } = fragFigures(r)
    art = draw(back, p.dark, 0.72) + draw(front, p.dark, 1)
  }

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${F} ${F}" width="${F}" height="${F}" role="img" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
<title>${key}</title>
<defs>
<linearGradient id="f${id}" x1="0" y1="0" x2="0.6" y2="1">
<stop offset="0" stop-color="${p.hot}"/><stop offset="0.42" stop-color="${p.mid}"/>
<stop offset="0.8" stop-color="${p.warm}"/><stop offset="1" stop-color="${p.light}"/>
</linearGradient>
<radialGradient id="g${id}" cx="46%" cy="30%" r="60%">
<stop offset="0" stop-color="${p.light}" stop-opacity="0.3"/>
<stop offset="1" stop-color="${p.light}" stop-opacity="0"/>
</radialGradient>
<linearGradient id="b${id}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="${p.light}" stop-opacity="0.42"/>
<stop offset="0.55" stop-color="${p.light}" stop-opacity="0.15"/>
<stop offset="1" stop-color="${p.light}" stop-opacity="0"/>
</linearGradient>
<filter id="s${id}" x="-25%" y="-25%" width="150%" height="150%">
<feGaussianBlur stdDeviation="22"/>
</filter>
<radialGradient id="v${id}" cx="50%" cy="40%" r="72%">
<stop offset="0.5" stop-color="${p.dark}" stop-opacity="0"/>
<stop offset="1" stop-color="${p.dark}" stop-opacity="0.58"/>
</radialGradient>
<filter id="n${id}" x="0" y="0" width="100%" height="100%">
<feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="3" seed="11" result="t"/>
<feColorMatrix in="t" type="matrix" values="0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.4 0 0 0 0"/>
</filter>
<style>.lit{fill:${p.light};stroke:none;fill-opacity:0.3}</style>
</defs>
<rect width="${F}" height="${F}" fill="url(#f${id})"/>
<rect width="${F}" height="${F}" fill="url(#g${id})"/>
${light}
${art}
<rect width="${F}" height="${F}" fill="url(#v${id})"/>
<rect width="${F}" height="${F}" filter="url(#n${id})" opacity="0.3" style="mix-blend-mode:multiply"/>
<rect width="${F}" height="${F}" filter="url(#n${id})" opacity="0.14" style="mix-blend-mode:screen"/>
</svg>
`
}

/* ── Drive ───────────────────────────────────────────────────────────── */

const originArg = process.argv.indexOf('--origin')
const ORIGIN = originArg > -1
  ? process.argv[originArg + 1]
  : process.env.MAP_ORIGIN || 'https://backend-staging-1c16.up.railway.app'

const SPHERES = ['society', 'economy', 'organizations', 'consumers']

const tail = (slug) => (typeof slug === 'string' ? slug.split('/').filter(Boolean).at(-1) : '')

const sleep = (ms) => new Promise((done) => { setTimeout(done, ms) })

/**
 * One fetch, with the backoff the API's rate limiter asks for.
 *
 * Walking every key shift is 58 requests in a row, which trips staging's
 * limiter partway through — and a half-generated run is worse than a failed one,
 * because the directory has already been emptied by then.
 */
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

async function shifts() {
  const out = []
  for (const sphere of SPHERES) {
    const body = await get(`/api/v1/map/${sphere}`)
    const dom = body.domains?.[0] ?? body
    for (const k of dom.key_shifts ?? dom.key_trends ?? []) {
      const slug = tail(k.slug)
      if (slug) out.push({ slug, sphere })
    }
  }
  return out
}

/**
 * Every sub-shift, keyed `<key shift>/<sub-shift>`.
 *
 * The composite key rather than the sub's own slug: nothing guarantees a
 * sub-shift slug is unique across all 58 key shifts, and two shifts quietly
 * sharing one image is the kind of bug that only shows up in a screenshot
 * months later.
 */
async function subShifts(keyShifts) {
  const out = []
  for (const { slug, sphere } of keyShifts) {
    const from = out.length
    const body = await get(`/api/v1/map/${sphere}/${slug}`)
    for (const s of body.sub_shifts ?? body.sub_trends ?? []) {
      const sub = tail(s.slug)
      if (sub) out.push({ key: `${slug}/${sub}`, file: `${slug}__${sub}`, sphere, index: out.length - from })
    }
  }
  return out
}

async function main() {
    const list = await shifts()
  if (!list.length) throw new Error('no key shifts published — refusing to wipe existing art')
  const subs = await subShifts(list)

  // Rewrite the directories wholesale. Art is derived, so a stale file for a shift
  // that no longer exists is worse than no file: the manifest would not list it
  // but it would still be sitting in the deploy.
  for (const dir of [OUT_DIR, WIDE_DIR, SUB_DIR]) {
    if (existsSync(dir)) for (const f of readdirSync(dir)) rmSync(resolve(dir, f))
    mkdirSync(dir, { recursive: true })
  }

  const manifest = {}
  const wide = {}
  for (const { slug, sphere } of list) {
    writeFileSync(resolve(OUT_DIR, `${slug}.svg`), poster(slug, sphere, FRAMES.tall))
    manifest[slug] = `/shift/heroes/${slug}.svg`
    writeFileSync(resolve(WIDE_DIR, `${slug}.svg`), poster(slug, sphere, FRAMES.wide))
    wide[slug] = `/shift/heroes-wide/${slug}.svg`
  }
  writeFileSync(MANIFEST, `${JSON.stringify(manifest, Object.keys(manifest).sort(), 2)}\n`)
  writeFileSync(WIDE_MANIFEST, `${JSON.stringify(wide, Object.keys(wide).sort(), 2)}\n`)

  const subManifest = {}
  for (const { key, file, sphere, index } of subs) {
    writeFileSync(resolve(SUB_DIR, `${file}.svg`), fragment(key, sphere, index))
    subManifest[key] = `/shift/subs/${file}.svg`
  }
  writeFileSync(SUB_MANIFEST, `${JSON.stringify(subManifest, Object.keys(subManifest).sort(), 2)}\n`)

  console.log(
    `${list.length} posters → public/shift/heroes (+ heroes-wide), `
    + `${subs.length} fragments → public/shift/subs`,
  )
}

/* Importable so scripts/check-frame.mjs can redraw the portrait set in-process
   and hash it against what is committed, without the network this CLI needs. */
export { poster, fragment, FRAMES }

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main()
}
