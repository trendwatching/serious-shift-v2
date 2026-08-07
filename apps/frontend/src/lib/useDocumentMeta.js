import { useEffect } from 'react'

/**
 * Keep `<title>`, the description and the canonical link correct as the user
 * navigates.
 *
 * The backend already stamps these into the shell per route, which is what
 * crawlers and link unfurlers read on a cold fetch. But Next's app-router
 * restores its build-time metadata during hydration, so the server's title
 * survived only until the page became interactive — and client-side navigation
 * never touched it at all. The result was a generic tab title on every page,
 * a canonical frozen on whichever route was loaded first, and the same generic
 * title for any crawler that executes JavaScript (Google does).
 *
 * So the server handles first paint and no-JS clients; this handles everything
 * after. Both read the same map document, so they agree.
 */
const SITE = 'Serious Shi(f)t'
const DEFAULT_TITLE = `${SITE} — Everything that is about to change`
const DEFAULT_DESCRIPTION = 'What is about to change, and who is saying so. An evidence-led trend map updated weekly.'

function setMeta(selector, attr, value) {
  let el = document.head.querySelector(selector)
  if (!value) {
    el?.remove()
    return
  }
  if (!el) {
    el = document.createElement(selector.startsWith('link') ? 'link' : 'meta')
    // `selector` is one of the fixed strings below, so this parse is safe.
    const [, key, val] = selector.match(/\[(\w+)="([^"]+)"\]/) || []
    if (key) el.setAttribute(key, val)
    document.head.appendChild(el)
  }
  el.setAttribute(attr, value)
}

/**
 * @param {string} [title]  page title *without* the site suffix
 * @param {string} [description]
 */
export function useDocumentMeta(title, description, { notFound = false } = {}) {
  useEffect(() => {
    document.title = notFound
      ? `Page not found · ${SITE}`
      : title ? `${title} — ${SITE}` : DEFAULT_TITLE

    const copy = notFound ? '' : (description || DEFAULT_DESCRIPTION)
    setMeta('meta[name="description"]', 'content', copy)
    setMeta('meta[property="og:description"]', 'content', copy)
    setMeta('meta[property="og:title"]', 'content', document.title)
    setMeta('meta[name="robots"]', 'content', notFound ? 'noindex, nofollow' : '')

    const url = `${window.location.origin}${window.location.pathname}`
    setMeta('link[rel="canonical"]', 'href', notFound ? '' : url)
    setMeta('meta[property="og:url"]', 'content', notFound ? '' : url)
  }, [title, description, notFound])
}
