/**
 * The black bar and its nav.
 *
 * Two things here are load-bearing and were wrong before:
 *
 *  * The bar is `position: absolute`, not sticky, and it OVERLAPS the content
 *    below it. The deck starts at 126px while the bar is 140px, so the bar
 *    sits over the top 14px of the panel. Making it sticky put it in flow and
 *    pushed everything down.
 *  * Its height is `--topbar`, and every hero and floating breadcrumb measures
 *    against that same token. The last build hard-coded 62px against an 82px
 *    bar and the 20px error propagated to every page.
 *
 * The nav is a dropdown pinned under the bar, not a full-screen sheet. It is
 * still a <dialog> so focus is trapped and Escape closes it — semantics the
 * design build has no notion of, and which move no pixel it specifies.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from '../lib/router'
import { MENU_LINKS } from '../lib/site'
import { useDomains } from '../lib/useDomains'

const LOGO = '/shift/serious-shift-logo-white.png'

export function Header() {
  const [open, setOpen] = useState(false)
  const { meta } = useDomains()
  const dialogRef = useRef(null)
  const triggerRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const dialog = dialogRef.current
    const onKey = (e) => { if (e.key === 'Escape') close() }
    const onPointer = (e) => {
      if (!dialog.contains(e.target) && !triggerRef.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [open])

  const close = () => {
    setOpen(false)
    // `preventScroll` is load-bearing, not a nicety. Returning focus to the
    // trigger scrolls it back into view by default, and the trigger lives at the
    // top of the document — so choosing "Services" scrolled to that section and
    // then snapped straight back to the top of /about, one frame later. The
    // focus return itself has to stay: closing a dropdown must not drop the
    // keyboard user at the top of the document with nothing selected.
    requestAnimationFrame(() => triggerRef.current?.focus({ preventScroll: true }))
  }

  return (
    <>
      <header
        className="a-fade absolute inset-x-0 top-0 z-50 box-border flex items-center justify-between"
        style={{
          height: 'var(--topbar)',
          // 56px of the design's 140px is the iOS status bar. On the web that
          // inset is real and variable, so it is honoured rather than faked.
          padding: 'max(0px, env(safe-area-inset-top)) var(--gutter) 0',
          background: 'var(--color-black)',
        }}
      >
        <Link to="/" aria-label="Serious Shift — home" className="flex shrink-0 items-center">
          {/* Sized as a FRACTION of the band, not in pixels. The lock-up is
              74×214 in an 84px bar, so it keeps 88% of the band's height and
              its own 2.892 aspect at every width — which is what stops a
              214px logo from becoming a stamp in the corner of a 27" display.
              The width/height attributes stay: they give the browser the ratio
              to hold before the PNG arrives. */}
          <img
            src={LOGO} alt="Serious Shi(f)t, powered by TrendWatching"
            width={214} height={74} draggable="false"
            className="block object-contain"
            style={{ height: 'calc(var(--bar-h) * 0.881)', width: 'calc(var(--bar-h) * 2.548)' }}
          />
        </Link>

        {/* The spelled-out desktop nav — real horizontal entries, per the
            12 Aug 2026 Miro review. `.nav-desktop` is display:none until the
            desktop layer (styles/desktop.css) shows it and hides the burger,
            so phones keep the dropdown exactly as it was. */}
        <nav aria-label="Primary" className="nav-desktop items-center" style={{ gap: 30 }}>
          {MENU_LINKS.map((link) => {
            const props = {
              className: 't-display font-semibold !text-white',
              style: { fontSize: 16, letterSpacing: '-0.01em' },
            }
            return link.internal
              ? <Link key={link.label} to={link.href} {...props}>{link.label}</Link>
              : <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer" {...props}>{link.label}</a>
          })}
        </nav>

        <button
          ref={triggerRef}
          type="button" onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          aria-expanded={open} aria-controls="site-nav"
          className="nav-burger flex cursor-pointer flex-col items-end"
          style={{
            padding: `calc(var(--bar-h) * 0.048) 0 calc(var(--bar-h) * 0.119) calc(var(--bar-h) * 0.167)`,
            gap: 'calc(var(--bar-h) * 0.0595)',
          }}
        >
          {/* Three bars of falling width. They do not morph on open — the
              design's hamburger is static and the panel's presence is the
              state indicator. Like the logo, each is a fraction of the band
              (26, 20 and 13 of an 84px bar), so the target grows with the
              chrome instead of staying a 26px smudge on a large screen. */}
          {[0.3095, 0.2381, 0.1548].map((k) => (
            <span
              key={k} className="block rounded-sm bg-white"
              style={{ width: `calc(var(--bar-h) * ${k})`, height: 'calc(var(--bar-h) * 0.0298)' }}
            />
          ))}
        </button>
      </header>

      {/* `open` as an attribute, not `showModal()`: this is a dropdown, so it
          must not take the top layer or dim the page behind it. */}
      <dialog
        ref={dialogRef}
        id="site-nav"
        open={open}
        aria-label="Site navigation"
        onClose={() => setOpen(false)}
        className="fixed inset-x-0 z-[49] m-0 w-full max-w-none border-0 bg-black p-0 text-white"
        style={{ top: 'var(--topbar)' }}
      >
        <nav aria-label="Primary" style={{ padding: '8px var(--gutter) 26px', animation: 'ssRise 0.42s var(--ease-out)' }}>
          {MENU_LINKS.map((link) => {
            // Only a row that declares `meta` gets the right-hand slot; a null
            // declaration means "fill in the live shift count". The 5 Aug Miro
            // review removed the descriptive metas from every other row.
            const body = (
              <>
                <span className="t-display font-semibold tracking-[-0.01em]" style={{ fontSize: 'var(--t-nav)' }}>{link.label}</span>
                {'meta' in link && (
                  <span className="ml-auto" style={{ fontSize: 'calc(var(--t-nav) * 0.6)', color: 'rgba(255,255,255,0.5)' }}>
                    {link.meta ?? (meta.shiftCount ? `${meta.shiftCount} key shifts` : 'Every domain')}
                  </span>
                )}
              </>
            )
            const props = {
              onClick: close,
              className: 'flex items-center gap-3 !text-white',
              // Derived from the label, so the rows open up as the type does
              // — 15px against 20px type, 19.5 against 26.
              style: { padding: 'calc(var(--t-nav) * 0.75) 0', borderBottom: '1px solid rgba(255,255,255,0.12)' },
            }
            return link.internal
              ? <Link key={link.label} to={link.href} {...props}>{body}</Link>
              : <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer" {...props}>{body}</a>
          })}
        </nav>
      </dialog>
    </>
  )
}
