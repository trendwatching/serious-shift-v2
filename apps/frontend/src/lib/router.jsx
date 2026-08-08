import React, { createContext, useContext, useEffect, useLayoutEffect, useMemo, useState } from 'react'

const RouterContext = createContext(null)
const ParamsContext = createContext({})

function normalise(path) {
  const value = String(path || '/').split(/[?#]/, 1)[0] || '/'
  return value !== '/' ? value.replace(/\/+$/, '') : value
}

const hashOf = (path) => {
  const at = String(path || '').indexOf('#')
  return at === -1 ? '' : String(path).slice(at + 1)
}

/**
 * Put the reader where the link promised.
 *
 * A single-page app keeps the scroll offset across a route change unless
 * something resets it, so tapping a sub-shift from halfway down a key shift
 * landed the reader halfway down the next page — and every `#section` link in
 * the nav landed at the top of /about, which made five of the six nav rows
 * indistinguishable from one another.
 *
 * This runs from a layout effect on the new route, NOT from `navigate`.
 * Scrolling at navigate time happens before React has committed, so the reset
 * lands on the outgoing document and Chrome's scroll anchoring then restores
 * the offset as the incoming one grows — which is exactly what it did.
 */
function ScrollManager({ pathname, hash }) {
  useLayoutEffect(() => {
    const target = hash && document.getElementById(hash)
    if (target) target.scrollIntoView({ block: 'start' })
    else window.scrollTo(0, 0)
  }, [pathname, hash])
  return null
}

function match(pattern, pathname) {
  if (pattern === '*') return {}
  const expected = normalise(pattern).split('/').filter(Boolean)
  const actual = normalise(pathname).split('/').filter(Boolean)
  if (expected.length !== actual.length) return null
  const params = {}
  for (let index = 0; index < expected.length; index += 1) {
    const part = expected[index]
    if (part.startsWith(':')) {
      try {
        params[part.slice(1)] = decodeURIComponent(actual[index])
      } catch {
        return null
      }
    }
    else if (part !== actual[index]) return null
  }
  return params
}

function BrowserHistory({ children }) {
  const [route, setRoute] = useState(() => ({
    pathname: normalise(window.location.pathname),
    hash: window.location.hash.slice(1),
    // Bumped on every navigation so re-opening the same anchor still scrolls.
    nonce: 0,
  }))

  useEffect(() => {
    // Otherwise Back restores the outgoing page's offset onto a route we
    // re-render from scratch, and lands the reader in the middle of it.
    if ('scrollRestoration' in history) history.scrollRestoration = 'manual'
    const update = () => setRoute((current) => ({
      pathname: normalise(window.location.pathname),
      hash: window.location.hash.slice(1),
      nonce: current.nonce + 1,
    }))
    addEventListener('popstate', update)
    return () => removeEventListener('popstate', update)
  }, [])

  const navigate = (to, { replace = false } = {}) => {
    if (typeof to === 'number') {
      history.go(to)
      return
    }
    const pathname = normalise(to)
    const hash = hashOf(to)
    // Re-navigating to where you already are is not a new place. Pushing it
    // anyway stacks duplicate entries, so Back appears to do nothing — which is
    // what tapping "Shifts" in the nav from the homepage used to do.
    const same = pathname === route.pathname && hash === window.location.hash.slice(1)
    if (!same) history[replace ? 'replaceState' : 'pushState']({}, '', to)
    setRoute((current) => ({ pathname, hash, nonce: current.nonce + 1 }))
  }

  const value = useMemo(() => ({ pathname: route.pathname, navigate }), [route])
  return (
    <RouterContext.Provider value={value}>
      <ScrollManager pathname={`${route.pathname}#${route.nonce}`} hash={route.hash} />
      {children}
    </RouterContext.Provider>
  )
}

export function MemoryRouter({ children, initialEntries = ['/'] }) {
  const [entries, setEntries] = useState(() => initialEntries.map(normalise))
  const [index, setIndex] = useState(() => Math.max(0, initialEntries.length - 1))
  const navigate = (to, { replace = false } = {}) => {
    if (typeof to === 'number') {
      setIndex((current) => Math.max(0, Math.min(entries.length - 1, current + to)))
      return
    }
    const path = normalise(to)
    if (replace) setEntries((current) => current.map((item, i) => (i === index ? path : item)))
    else {
      setEntries((current) => [...current.slice(0, index + 1), path])
      setIndex(index + 1)
    }
  }
  return <RouterContext.Provider value={{ pathname: entries[index], navigate }}>{children}</RouterContext.Provider>
}

export const BrowserRouter = BrowserHistory

export function useLocation() {
  const router = useContext(RouterContext)
  if (!router) throw new Error('useLocation must be used inside a router')
  return { pathname: router.pathname }
}

export function useNavigate() {
  const router = useContext(RouterContext)
  if (!router) throw new Error('useNavigate must be used inside a router')
  return router.navigate
}

export function useParams() {
  return useContext(ParamsContext)
}

export function Link({ to, children, onClick, target, ...props }) {
  const navigate = useNavigate()
  const href = String(to)
  const activate = (event) => {
    onClick?.(event)
    if (event.defaultPrevented || event.button !== 0 || target === '_blank'
      || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    navigate(href)
  }
  return <a {...props} href={href} target={target} onClick={activate}>{children}</a>
}

export function Route() {
  return null
}

export function Routes({ children }) {
  const { pathname } = useLocation()
  const routes = useMemo(() => React.Children.toArray(children), [children])
  for (const route of routes) {
    const params = match(route.props.path, pathname)
    if (params !== null) {
      return <ParamsContext.Provider value={params}>{route.props.element}</ParamsContext.Provider>
    }
  }
  return null
}
