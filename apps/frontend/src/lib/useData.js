import { useCallback, useEffect, useMemo, useState } from 'react'

const cache = new Map()     // url → { data, etag, storedAt }
const inflight = new Map()  // url → Promise<data>
const CACHE_TTL = 60_000

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

export class ApiError extends Error {
  constructor(url, status = 0, code = '', kind = '', retryAfterMs = 0) {
    super(status ? `${url} → ${status}` : `${url} → network error`)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.kind = kind || (status === 503 || code === 'unavailable'
      ? 'unavailable'
      : status === 408 || status === 504
        ? 'timeout'
        : status >= 500
        ? 'server'
          : status === 0
            ? (typeof navigator !== 'undefined' && navigator.onLine === false ? 'offline' : 'unavailable')
            : 'request')
    this.retryAfterMs = retryAfterMs
  }
}

function normaliseUrl(resource) {
  const value = String(resource || '')
  if (value.startsWith('/api/')) return value
  return `/api/${value.replace(/^\/+/, '').replace(/\.json$/, '')}`
}

function transient(error) {
  return !error?.status || error.status === 408 || error.status === 429 || error.status >= 500
}

function validObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** The addressable path segment of a slug — `a/b` and `b` both give `b`. */
function lastSegment(value) {
  return typeof value === 'string' ? value.split('/').filter(Boolean).at(-1) : undefined
}

function validModules(value) {
  return Array.isArray(value) && value.every((module) => (
    validObject(module) && typeof module.type === 'string' && validObject(module.data)
  ))
}

/** Reject truncated or wrong-route JSON before it reaches the renderer. */
function validateMapResponse(url, data) {
  if (!url.startsWith('/api/v1/map') || !validObject(data)) return validObject(data)
  const parts = url.slice('/api/v1/map'.length).split('/').filter(Boolean)
  if (parts.length === 0) {
    return validObject(data.totals) && Array.isArray(data.domains)
      && data.domains.every((domain) => validObject(domain) && typeof domain.id === 'string')
  }
  if (!validObject(data.domain) || data.domain.id !== parts[0]) return false
  if (parts.length === 1) return Array.isArray(data.key_shifts) && Array.isArray(data.insights)
  if (parts.length === 2) {
    return validObject(data.shift) && data.shift.slug === parts[1] && validModules(data.shift.modules)
      && Array.isArray(data.siblings) && Array.isArray(data.sub_shifts)
  }
  // Compare the last path segment, not the whole slug. A published sub-shift's
  // slug is `parent/child`, and the backend used to serve that compound form
  // here while serving the bare segment on `siblings` in the same response — so
  // this check could never pass, every sub-shift response was rejected as
  // invalid, retried, and rendered as "temporarily unavailable". The backend now
  // sends the segment; matching on the segment either way means a version skew
  // between the two deploys cannot take the pages down again.
  return validObject(data.parent_shift) && validObject(data.sub_shift)
    && lastSegment(data.sub_shift.slug) === parts[2] && validModules(data.sub_shift.modules)
    && Array.isArray(data.siblings)
}

async function fetchJson(url, previous) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)
  let response
  try {
    const headers = { Accept: 'application/json' }
    if (previous?.etag) headers['If-None-Match'] = previous.etag
    response = await fetch(url, { headers, signal: controller.signal })
  } catch (cause) {
    const timedOut = cause?.name === 'AbortError'
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false
    throw new ApiError(url, 0, timedOut ? 'timeout' : 'network_error', timedOut ? 'timeout' : offline ? 'offline' : 'unavailable')
  } finally {
    clearTimeout(timeout)
  }
  if (response.status === 304 && previous?.data) {
    return { data: previous.data, etag: previous.etag, storedAt: Date.now() }
  }
  if (!response.ok) {
    let code = ''
    try { code = (await response.json())?.error?.code || '' } catch { /* non-JSON error */ }
    const retryAfter = response.headers?.get?.('Retry-After') || ''
    const retryAfterMs = retryAfter
      ? (/^\d+$/.test(retryAfter) ? Number(retryAfter) * 1000 : Math.max(0, Date.parse(retryAfter) - Date.now()))
      : 0
    throw new ApiError(url, response.status, code, '', retryAfterMs)
  }
  const data = await response.json()
  if (!validateMapResponse(url, data)) {
    throw new ApiError(url, 502, 'invalid_response', 'unavailable')
  }
  return {
    data,
    etag: response.headers?.get?.('ETag') || '',
    storedAt: Date.now(),
  }
}

/** Load once, retrying only transient failures. Rejections are never cached. */
export function load(resource, { force = false } = {}) {
  const url = normaliseUrl(resource)
  const previous = cache.get(url)
  if (!force && previous && Date.now() - previous.storedAt < CACHE_TTL) {
    return Promise.resolve(previous.data)
  }

  let pending = inflight.get(url)
  if (!pending) {
    pending = (async () => {
      let lastError
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const result = await fetchJson(url, previous)
          cache.set(url, result)
          return result.data
        } catch (error) {
          lastError = error
          if (!transient(error) || attempt === 2) throw error
          await wait(Math.max(error.retryAfterMs || 0, 250 * (2 ** attempt)))
        }
      }
      throw lastError
    })().finally(() => inflight.delete(url))
    inflight.set(url, pending)
  }
  return pending
}

export function useData(resource, { enabled = true } = {}) {
  const url = useMemo(() => normaliseUrl(resource), [resource])
  const [result, setResult] = useState(() => (
    enabled && cache.has(url) ? { data: cache.get(url).data, error: null } : null
  ))
  const [revision, setRevision] = useState(0)

  useEffect(() => {
    if (!enabled) {
      setResult(null)
      return undefined
    }
    let alive = true
    const cached = cache.get(url)?.data
    setResult(cached ? { data: cached, error: null } : null)
    load(url, { force: revision > 0 })
      .then((data) => { if (alive) setResult({ data, error: null }) })
      .catch((error) => { if (alive) setResult((current) => ({ data: current?.data || cached || null, error })) })
    return () => { alive = false }
  }, [enabled, revision, url])

  const retry = useCallback(() => setRevision((value) => value + 1), [])

  return {
    data: result?.data ?? null,
    error: result?.error ?? null,
    loading: enabled && !result,
    retry,
  }
}

export function __resetDataCacheForTests() {
  cache.clear()
  inflight.clear()
}
