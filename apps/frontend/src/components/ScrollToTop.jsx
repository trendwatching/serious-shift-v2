import { useLayoutEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Reset scroll to the top of the page on every route change.
 *
 * React Router keeps the window scroll position across client-side navigations,
 * so a new page would otherwise open wherever the previous one was scrolled to.
 * We watch the pathname (not the full location, so a hash/query change alone
 * doesn't yank the page) and jump to the top before paint — no visible flash.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation()
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }, [pathname])
  return null
}
