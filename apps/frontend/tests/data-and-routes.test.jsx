import { useEffect } from 'react'
import { MemoryRouter, Route, Routes } from '../src/lib/router'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, load } from '../src/lib/useData'
import { failureState } from '../src/lib/failure'
import { useResolved } from '../src/lib/useDomains'
import SubShiftPage from '../src/pages/SubShiftPage'
import App from '../src/App'
import { indexFixture, response, shiftFixture, subFixture } from './fixtures'

describe('route-scoped data', () => {
  it('retries transient failures twice and caches only the success', async () => {
    vi.useFakeTimers()
    global.fetch = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503, json: () => Promise.resolve({ error: { code: 'unavailable' } }) })
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve(indexFixture) })

    const pending = load('/api/v1/map')
    await vi.runAllTimersAsync()
    await expect(pending).resolves.toEqual(indexFixture)
    await expect(load('/api/v1/map')).resolves.toEqual(indexFixture)
    expect(fetch).toHaveBeenCalledTimes(3)
  })

  it('does not retry or cache a 404', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404, json: () => Promise.resolve({ error: { code: 'not_found' } }) })
    await expect(load('/api/v1/map/missing')).rejects.toMatchObject({ status: 404 })
    await expect(load('/api/v1/map/missing')).rejects.toMatchObject({ status: 404 })
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('revalidates cached responses with ETags and reuses a 304 body', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true, status: 200, headers: new Headers({ ETag: 'W/"index-a"' }),
        json: () => Promise.resolve(indexFixture),
      })
      .mockResolvedValueOnce({ ok: false, status: 304, headers: new Headers() })
    await expect(load('/api/v1/map')).resolves.toEqual(indexFixture)
    await expect(load('/api/v1/map', { force: true })).resolves.toEqual(indexFixture)
    expect(fetch.mock.calls[1][1].headers['If-None-Match']).toBe('W/"index-a"')
  })

  it('rejects malformed route documents before rendering them', async () => {
    vi.useFakeTimers()
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200, headers: new Headers(),
      json: () => Promise.resolve({ domain: { id: 'society' }, shift: {} }),
    })
    const pending = load('/api/v1/map/society/trust-machines')
    const assertion = expect(pending).rejects.toMatchObject({ status: 502, code: 'invalid_response' })
    await vi.runAllTimersAsync()
    await assertion
  })

  it('stops timed-out requests and presents distinct recovery states', async () => {
    vi.useFakeTimers()
    global.fetch = vi.fn((_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('Timed out', 'AbortError')))
    }))

    const pending = load('/api/v1/map/slow')
    const assertion = expect(pending).rejects.toMatchObject({ kind: 'timeout', code: 'timeout' })
    await vi.runAllTimersAsync()
    await assertion
    expect(fetch).toHaveBeenCalledTimes(3)

    expect(['offline', 'timeout', 'server', 'unavailable'].map((kind) => (
      failureState(new ApiError('/api/v1/map', 0, '', kind)).title
    ))).toEqual([
      'You’re offline.',
      'The map took too long to respond.',
      'The map service hit an error.',
      'The current map isn’t available.',
    ])
  })

  it('fetches only the index and current route and resolves shift siblings', async () => {
    global.fetch = vi.fn((url) => response(url === '/api/v1/map' ? indexFixture : shiftFixture))

    function Probe() {
      const state = useResolved({ domainSlug: 'society', ktSlug: 'trust-machines' })
      useEffect(() => {}, [state])
      return <output>{state.shift?.title}|{state.shiftSiblings.next?.title}</output>
    }

    render(<MemoryRouter initialEntries={['/map/society/trust-machines']}><Probe /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Trust Machines|Synthetic Belonging')).toBeInTheDocument())
    expect(fetch.mock.calls.map(([url]) => url)).toEqual(['/api/v1/map', '/api/v1/map/society/trust-machines'])
    expect(fetch).not.toHaveBeenCalledWith('/api/map', expect.anything())
  })

  it('gives a terminal sub-shift page its only way out: the breadcrumb menu', async () => {
    // The design deliberately strips every other route off this page — no
    // eyebrow link to the parent, no sibling rail, no next pager. The
    // breadcrumb menu carries all of it, which is why it lists the whole
    // domain rather than just the ancestors.
    global.fetch = vi.fn((url) => response(url === '/api/v1/map' ? indexFixture : subFixture))
    render(
      <MemoryRouter initialEntries={['/map/society/trust-machines/sub-1']}>
        <Routes><Route path="/map/:domainSlug/:ktSlug/:subSlug" element={<SubShiftPage />} /></Routes>
      </MemoryRouter>,
    )
    const trigger = await screen.findByRole('button', { expanded: false })
    await userEvent.click(trigger)
    expect(screen.getByRole('button', { name: /Society/ })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Adjacent sub-shifts' })).not.toBeInTheDocument()
  })

  it('clears stale canonical metadata and marks client-side unknown routes noindex', async () => {
    document.head.innerHTML = '<link rel="canonical" href="https://example.test/old"><meta property="og:url" content="https://example.test/old">'
    render(<MemoryRouter initialEntries={['/not-real']}><App /></MemoryRouter>)
    await waitFor(() => expect(document.title).toBe('Page not found · Serious Shi(f)t'))
    expect(document.querySelector('meta[name="robots"]')).toHaveAttribute('content', 'noindex, nofollow')
    expect(document.querySelector('link[rel="canonical"]')).toBeNull()
    expect(document.querySelector('meta[property="og:url"]')).toBeNull()
  })

  it('treats malformed percent-encoded paths as not found instead of crashing', async () => {
    render(<MemoryRouter initialEntries={['/map/%E0%A4%A']}><App /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: 'This shift has moved.' })).toBeInTheDocument()
  })
})

describe('sub-shift response validation', () => {
  // Every sub-shift page rendered "temporarily unavailable" because the backend
  // served `sub_shift.slug` as the compound `parent/child` while this check
  // compared it to the bare URL segment. A rejected response is retried and then
  // surfaced as unavailable, so all 281 pages answered 200 and showed an error.
  const body = (slug) => ({
    updated: '2026-08-02',
    domain: { id: 'society', name: 'Society', short_description: 'x', key_shift_count: 1 },
    parent_shift: { id: 'kt-1', slug: 'sovereign-machines', name: 'Sovereign Machines' },
    sub_shift: { id: 'st-1', slug, name: 'Sovereign Labs', modules: [{ type: 'lede', data: { text: 'x' } }] },
    siblings: [{ id: 'st-1', slug: 'sovereign-labs', name: 'Sovereign Labs' }],
  })

  it('accepts the bare route segment the backend now sends', async () => {
    const { load, __resetDataCacheForTests } = await import('../src/lib/useData')
    __resetDataCacheForTests()
    global.fetch = vi.fn(async () => new Response(JSON.stringify(body('sovereign-labs')),
      { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await expect(load('/api/v1/map/society/sovereign-machines/sovereign-labs')).resolves.toBeTruthy()
  })

  it('also accepts the compound parent/child form, so a version skew cannot break the page', async () => {
    const { load, __resetDataCacheForTests } = await import('../src/lib/useData')
    __resetDataCacheForTests()
    global.fetch = vi.fn(async () => new Response(
      JSON.stringify(body('sovereign-machines/sovereign-labs')),
      { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await expect(load('/api/v1/map/society/sovereign-machines/sovereign-labs')).resolves.toBeTruthy()
  })

  it('still rejects a response for a different sub-shift', async () => {
    const { load, __resetDataCacheForTests } = await import('../src/lib/useData')
    __resetDataCacheForTests()
    global.fetch = vi.fn(async () => new Response(JSON.stringify(body('some-other-sub')),
      { status: 200, headers: { 'Content-Type': 'application/json' } }))
    await expect(load('/api/v1/map/society/sovereign-machines/sovereign-labs')).rejects.toThrow()
  })
})
