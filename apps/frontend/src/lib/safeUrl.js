/**
 * Two guards for URLs the site did not author.
 *
 * Hero images, innovation thumbnails and innovation/source links arrive from the
 * map document and from the upstream innovations database. Both were being used
 * raw: pasted into a CSS `url('…')` string, and set as an `href`.
 *
 * `cssUrl` — a `'` or `)` in an image URL ends the CSS string early, so whatever
 * follows is parsed as CSS. That is a stylesheet injection with an
 * attacker-supplied payload; the benign version of the same thing (a URL with a
 * bracket in its query string) silently breaks the card's artwork instead.
 *
 * `safeHref` — an `href` accepts `javascript:`, which runs on click. Nothing
 * between the upstream database and the anchor checked the scheme.
 *
 * Neither has bitten, because today's data happens to be clean. That is the only
 * thing standing between the site and both.
 */

/** Quotes, parens and backslash end the url() token; whitespace and control
 *  characters can end the declaration. All are legal percent-encoded. */
const CSS_UNSAFE = /[\u0000-\u0020"'()\\]/g

/** `url("…")` for CSS, or null when there is nothing usable to point at. */
export function cssUrl(value) {
  const raw = String(value ?? '').trim()
  if (!raw) return null
  // Percent-encode by code point, not with encodeURIComponent: that leaves `'`
  // and `(` untouched, which are two of the four characters this is here for.
  return `url("${raw.replace(CSS_UNSAFE, (c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0').toUpperCase()}`)}")`
}

/** `value` if it is a scheme we will follow, otherwise undefined. */
export function safeHref(value) {
  const raw = String(value ?? '').trim()
  if (!raw) return undefined
  // Same-origin paths are fine and common; `//host` is not — it changes origin.
  if (raw.startsWith('/') && !raw.startsWith('//')) return raw
  try {
    const { protocol } = new URL(raw, 'https://serious.invalid')
    return ['http:', 'https:', 'mailto:'].includes(protocol) ? raw : undefined
  } catch {
    return undefined
  }
}
