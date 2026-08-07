/**
 * Breadcrumb.jsx — the overlapping pill chain, and its collapsed menu variant.
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
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from '../lib/router'

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

/**
 * The menu variant: one pill that opens the domain's whole shift tree.
 *
 * A sub-shift page is navigationally terminal — the design gives it no "next",
 * no related shifts and no sibling rail — so the only way sideways is through
 * here. That is why it lists every shift *and* every sub-shift rather than just
 * the ancestors the trail would show.
 */
export function BreadcrumbMenu({ label, domainLabel, domainTo, crumb, dot, groups = [], activeShift, activeSub }) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => { if (event.key === 'Escape') setOpen(false) }
    const onPointer = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [open])

  const go = (to) => { setOpen(false); navigate(to) }

  return (
    <div ref={rootRef} className="flex flex-col items-start" style={{ fontFamily: 'var(--font-display)' }}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex h-[30px] items-center gap-2 rounded-full px-[13px] text-[12px] tracking-[-0.005em]"
        style={{
          background: open ? '#fff' : crumb,
          color: open ? 'var(--color-ink)' : '#fff',
          fontWeight: 650,
          boxShadow: open ? '0 4px 12px rgba(27,22,32,0.22)' : '0 3px 10px rgba(27,22,32,0.18)',
        }}
      >
        <span className="max-w-[190px] overflow-hidden text-ellipsis whitespace-nowrap uppercase tracking-[0.04em]">{label}</span>
        <span
          aria-hidden="true"
          className="text-[13px] leading-none"
          style={{ opacity: open ? 0.7 : 0.85, transform: `rotate(${open ? -90 : 90}deg)` }}
        >
          →
        </span>
      </button>

      {open && (
        <div
          className="a-rise mt-2 box-border w-[292px] overflow-y-auto rounded-[18px] bg-white p-2"
          style={{ maxHeight: 420, boxShadow: '0 16px 34px rgba(27,22,32,0.24)' }}
        >
          <button
            type="button"
            onClick={() => go(domainTo)}
            className="flex w-full items-center gap-[9px] rounded-xl px-3 py-[11px] text-left text-[13px] font-bold"
            style={{ color: crumb }}
          >
            <span aria-hidden="true" className="flex-none rotate-180 text-[13px] leading-none opacity-70">→</span>
            <span className="flex-1">{domainLabel}</span>
            <span className="t-eyebrow flex-none text-[10.5px]" style={{ color: '#A9A3B8' }}>Domain</span>
          </button>

          {groups.map((group) => {
            const on = group.slug === activeShift
            return (
              <div key={group.slug} className="flex flex-col py-1" style={{ borderTop: '1px solid #F1EFF5' }}>
                <button
                  type="button"
                  onClick={() => go(group.to)}
                  className="flex w-full items-center gap-[9px] rounded-xl px-3 py-[11px] text-left"
                  style={{ background: on && activeSub == null ? '#FBF3F7' : 'transparent' }}
                >
                  <span className="size-[7px] flex-none rounded-full" style={{ background: dot }} />
                  <span className="t-title flex-1 text-[13px] leading-[1.25]" style={{ color: on ? crumb : 'var(--color-ink)' }}>
                    {group.title}
                  </span>
                  {group.subs.length > 0 && (
                    <span className="flex-none text-[10.5px]" style={{ color: '#A9A3B8' }}>{group.subs.length} sub</span>
                  )}
                </button>
                {group.subs.map((sub, i) => {
                  const subOn = on && activeSub === i
                  return (
                    <button
                      key={sub.slug}
                      type="button"
                      onClick={() => go(sub.to)}
                      className="flex w-full items-center gap-[9px] rounded-xl py-[9px] pl-7 pr-3 text-left"
                      style={{ background: subOn ? '#FBF3F7' : 'transparent' }}
                    >
                      <span className="h-px w-3 flex-none" style={{ background: '#D7D2E0' }} />
                      <span
                        className="flex-1 text-[12.5px] leading-[1.3]"
                        style={{ color: subOn ? crumb : '#5C5768', fontWeight: subOn ? 700 : 500 }}
                      >
                        {sub.title}
                      </span>
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
