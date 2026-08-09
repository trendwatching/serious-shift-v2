/**
 * Breadcrumb.jsx — the overlapping pill chain.
 *
 * The design floats this over the hero rather than docking it under the header,
 * which is why it is absolutely positioned by its caller and why the current
 * page's pill is filled with the domain's darkest tint: it has to stay legible
 * on top of a photograph.
 *
 * The pills overlap and descend in z-index, so the chain reads as one
 * continuous lozenge cut into segments rather than as separate chips. That is
 * also why every pill but the first carries a wider left pad — the overlap eats
 * it.
 *
 * EVERY dimension here is a fraction of `--crumb-h`, the way the header's
 * lock-up is a fraction of `--bar-h`. The chain used to be a flat 26px carrying
 * 11px type at every width: on a 1920 display that is a ribbon of unreadable
 * capitals under a 92px headline, and it was the first thing anyone pointed at.
 * The fractions are exact at the 26px design height, so the phone is unchanged.
 */
const K = {
  text: 0.423,     // 11px
  gap: 0.231,      //  6px
  overlap: 0.654,  // 17px of overlap between pills
  capNarrow: 4.308, // 112px cap when the trail has been collapsed
  capWide: 5.769,  // 150px otherwise
  padEnd: 0.5,     // 13px
  padLast: 0.808,  // 21px lead-in on the current page's pill
  padTight: 0.385, // 10px
  padFirst: 0.5,   // 13px
  padMid: 0.846,   // 22px — swallows the overlap
}
const px = (k) => `calc(var(--crumb-h) * ${k})`
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
      className={`inline-flex max-w-full items-center ${className}`}
      style={{ height: 'var(--crumb-h)', fontFamily: 'var(--font-display)', ...style }}
    >
      <ol className="flex h-full max-w-full items-center">
        {trail.map((crumbItem, i) => {
          const last = i === n - 1
          const content = (
            <>
              {/* Uppercased here, not by CSS — the trail is part of the name surface and
                  a copy-paste of it should read the way the page does. */}
              <span className="block min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap tracking-[0.04em]">
                {String(crumbItem.label ?? '').toUpperCase()}
              </span>
              {!last && <span className="flex-none opacity-50" style={{ fontSize: px(K.text) }} aria-hidden="true">›</span>}
            </>
          )
          const shared = {
            className: 'relative box-border flex h-full items-center rounded-full tracking-[-0.005em]',
            style: {
              zIndex: n - i,
              flex: last ? '1 1 auto' : '0 0 auto',
              minWidth: 0,
              fontSize: px(K.text),
              gap: px(K.gap),
              // A custom property, not a literal, so desktop.css can release it:
              // the cap is a phone constraint and it was truncating "CONSUMERS"
              // to "CONSUMER…" on a 1920 screen with 500px of room to spare.
              // An inline `maxWidth` cannot be beaten by any rule; a custom
              // property can.
              maxWidth: last ? 'none' : `var(--crumb-cap, ${px(n > 2 ? K.capNarrow : K.capWide)})`,
              padding: last
                ? `0 ${px(K.padEnd)} 0 ${px(K.padLast)}`
                : i === 0
                  ? `0 ${px(K.padTight)} 0 ${px(K.padFirst)}`
                  : `0 ${px(K.padTight)} 0 ${px(K.padMid)}`,
              marginLeft: i === 0 ? 0 : `calc(var(--crumb-h) * -${K.overlap})`,
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
