/**
 * Breadcrumb.jsx — the overlapping pill chain.
 *
 * The design floats this over the hero rather than docking it under the header,
 * which is why it is absolutely positioned by its caller and why the current
 * page's pill is filled with the domain's darkest tint: it has to stay legible
 * on top of a photograph.
 *
 * The pills overlap by 17px and descend in z-index, so the chain reads as one
 * continuous lozenge cut into segments rather than as separate chips. That is
 * also why every pill but the first carries a wider left pad — the overlap eats
 * it.
 */
import { Link } from '../lib/router'

/**
 * Collapse to first / … / last once there are more than three entries.
 *
 * The elided pill keeps the *last* middle entry's target, not the first: from a
 * sub-shift the useful jump is up one level to its parent shift, and that is
 * the entry the ellipsis is standing in for.
 */
function collapse(items) {
  if (items.length <= 3) return items
  const middle = items.slice(1, -1)
  return [items[0], { ...middle[middle.length - 1], label: '…' }, items[items.length - 1]]
}

export function Breadcrumb({ items, crumb = 'var(--a-crumb)', className = '', style }) {
  const trail = collapse(items.filter(Boolean))
  if (!trail.length) return null
  const n = trail.length

  return (
    <nav
      aria-label="Breadcrumb"
      className={`inline-flex h-[26px] max-w-full items-center ${className}`}
      style={{ fontFamily: 'var(--font-display)', ...style }}
    >
      <ol className="flex h-full max-w-full items-center">
        {trail.map((crumbItem, i) => {
          const last = i === n - 1
          const content = (
            <>
              <span className="block min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap uppercase tracking-[0.04em]">
                {crumbItem.label}
              </span>
              {!last && <span className="flex-none text-[11px] opacity-50" aria-hidden="true">›</span>}
            </>
          )
          const shared = {
            className: 'relative box-border flex h-full items-center gap-[6px] rounded-full text-[11px] tracking-[-0.005em]',
            style: {
              zIndex: n - i,
              flex: last ? '1 1 auto' : '0 0 auto',
              minWidth: 0,
              maxWidth: last ? 'none' : n > 2 ? '112px' : '150px',
              padding: last ? '0 13px 0 21px' : i === 0 ? '0 10px 0 13px' : '0 10px 0 22px',
              marginLeft: i === 0 ? 0 : '-17px',
              background: last ? crumb : '#fff',
              color: last ? '#fff' : 'var(--color-ink)',
              fontWeight: last ? 650 : 600,
              boxShadow: last
                ? '0 3px 10px rgba(27,22,32,0.16)'
                : '0 3px 10px rgba(27,22,32,0.14), 6px 0 10px -4px rgba(27,22,32,0.18)',
              transition: 'background 0.25s ease, color 0.25s ease',
            },
          }
          return (
            <li key={`${crumbItem.label}-${i}`} className="flex min-w-0" style={{ flex: shared.style.flex }}>
              {last || !crumbItem.to ? (
                <span {...shared} aria-current={last ? 'page' : undefined}>{content}</span>
              ) : (
                <Link to={crumbItem.to} {...shared}>{content}</Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
