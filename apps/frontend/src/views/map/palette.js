/**
 * palette.js — domain color palette + horizon/velocity labels.
 *
 * Centralised so every map layer (landing, domain, scenario, KT, sub-trend)
 * uses the same tint and the colour persists down the warp hierarchy.
 */

// Per-domain hues carried down the whole hierarchy (blob → streak → stat →
// breadcrumb tint). Values mirror the --color-c-* @theme tokens in index.css.
// `soft` is a low-alpha tint for backgrounds; `image` is the hero photo used
// inside the domain's smoke-blob (assets live in /public/domains/).
export const DOMAIN_COLORS = {
  society:       { color: '#F6469F', soft: 'color-mix(in oklab, #F6469F 12%, transparent)', image: '/domains/society.jpg' },
  economy:       { color: '#2E9BE6', soft: 'color-mix(in oklab, #2E9BE6 12%, transparent)', image: '/domains/economy.jpg' },
  consumers:     { color: '#FF6A3D', soft: 'color-mix(in oklab, #FF6A3D 12%, transparent)', image: '/domains/consumers.jpg' },
  organisations: { color: '#7FCB3B', soft: 'color-mix(in oklab, #7FCB3B 12%, transparent)', image: '/domains/organisations.jpg' },
}

export const DEFAULT_PALETTE = DOMAIN_COLORS.society

export const HORIZON_LABELS = {
  '1-3 years':  'Near-term',
  '3-5 years':  'Mid-term',
  '5-10 years': 'Long-term',
}

export const VELOCITY_LABEL = {
  accelerating:  'Accelerating',
  steady:        'Steady',
  decelerating:  'Decelerating',
  emergent:      'Emergent',
  early:         'Early',
  mature:        'Mature',
}

export function paletteFor(domainId) {
  return DOMAIN_COLORS[domainId] || DEFAULT_PALETTE
}

export function pad(n, width) {
  return String(n).padStart(width, '0')
}
