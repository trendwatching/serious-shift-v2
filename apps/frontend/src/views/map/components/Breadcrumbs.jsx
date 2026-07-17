/**
 * Breadcrumbs — wayfinding trail for inner pages (Sphere / Key Shift / Sub-shift).
 *
 * Props:
 *   crumbs — array of { label, to? }. Last crumb renders as the current page.
 *   tint   — optional domain hue applied to links + the active crumb.
 *
 * Rendered inline at the top of a page's content (not sticky) to match the
 * bright editorial layout.
 */
import { Fragment } from 'react'
import { Link } from 'react-router-dom'

export default function Breadcrumbs({ crumbs, tint }) {
  if (!crumbs || crumbs.length === 0) return null
  const accent = tint || 'var(--color-ink)'

  return (
    <nav
      className="max-w-7xl mx-auto px-4 sm:px-6 pt-6 flex items-center gap-2 overflow-x-auto"
      aria-label="Breadcrumb"
    >
      {crumbs.map((c, i) => {
        const isLast = i === crumbs.length - 1
        return (
          <Fragment key={i}>
            {i > 0 && (
              <span className="text-ink-faint shrink-0 select-none text-sm">›</span>
            )}
            {c.to && !isLast ? (
              <Link
                to={c.to}
                className="font-mono text-[11px] uppercase tracking-widest text-ink-faint hover:opacity-70 transition-opacity whitespace-nowrap shrink-0"
              >
                {c.label}
              </Link>
            ) : (
              <span
                className={`font-mono text-[11px] uppercase tracking-widest whitespace-nowrap shrink-0 ${
                  isLast ? 'font-bold' : 'text-ink-faint'
                }`}
                style={isLast ? { color: accent } : undefined}
                aria-current={isLast ? 'page' : undefined}
              >
                {c.label}
              </span>
            )}
          </Fragment>
        )
      })}
    </nav>
  )
}
