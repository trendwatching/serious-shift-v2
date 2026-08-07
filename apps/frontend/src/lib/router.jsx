import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'

const RouterContext = createContext(null)
const ParamsContext = createContext({})

function normalise(path) {
  const value = String(path || '/').split(/[?#]/, 1)[0] || '/'
  return value !== '/' ? value.replace(/\/+$/, '') : value
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
  const [pathname, setPathname] = useState(() => normalise(window.location.pathname))
  useEffect(() => {
    const update = () => setPathname(normalise(window.location.pathname))
    addEventListener('popstate', update)
    return () => removeEventListener('popstate', update)
  }, [])
  const navigate = (to, { replace = false } = {}) => {
    if (typeof to === 'number') {
      history.go(to)
      return
    }
    history[replace ? 'replaceState' : 'pushState']({}, '', to)
    setPathname(normalise(window.location.pathname))
  }
  return <RouterContext.Provider value={{ pathname, navigate }}>{children}</RouterContext.Provider>
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
