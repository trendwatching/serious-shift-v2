import { useEffect } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, load } from '../src/hooks/useData'
import { failureState } from '../src/shift/failure'
import { useResolved } from '../src/shift/useDomains'
import { SubShiftDetail } from '../src/shift/pages'
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
      'This week’s map isn’t available.',
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

  it('renders parent identity and adjacent sub-shift navigation from the route API', async () => {
    global.fetch = vi.fn((url) => response(url === '/api/v1/map' ? indexFixture : subFixture))
    render(
      <MemoryRouter initialEntries={['/map/society/trust-machines/sub-1']}>
        <Routes><Route path="/map/:domainSlug/:ktSlug/:subSlug" element={<SubShiftDetail />} /></Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('link', { name: /Sub-shift of “Trust Machines”/i })).toHaveAttribute('href', '/map/society/trust-machines')
    expect(screen.getByRole('navigation', { name: 'Adjacent sub-shifts' })).toHaveTextContent('Sub Shift 2')
  })
})
