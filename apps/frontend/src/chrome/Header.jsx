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

const LOGO = '/shift/serious-shift-logo-white.png'

export function Header() {
  const [open, setOpen] = useState(false)
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
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  return (
    <>
      <header
        className="a-fade absolute inset-x-0 top-0 z-50 box-border flex items-center justify-between"
        style={{
          height: 'var(--topbar)',
          // 56px of the design's 140px is the iOS status bar. On the web that
          // inset is real and variable, so it is honoured rather than faked.
          padding: 'max(0px, env(safe-area-inset-top)) 22px 0',
          background: 'var(--color-black)',
        }}
      >
        <Link to="/" aria-label="Serious Shi(f)t — home" className="flex shrink-0 items-center">
          <img
            src={LOGO} alt="Serious Shi(f)t, powered by TrendWatching"
            width={214} height={74} draggable="false"
            className="block h-[74px] w-[214px] object-contain"
          />
        </Link>

        <button
          ref={triggerRef}
          type="button" onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Close navigation' : 'Open navigation'}
          aria-expanded={open} aria-controls="site-nav"
          className="flex cursor-pointer flex-col items-end"
          style={{ padding: '4px 0 10px 14px', gap: 5 }}
        >
          {/* Three bars of falling width. They do not morph on open — the
              design's hamburger is static and the panel's presence is the
              state indicator. */}
          {[26, 20, 13].map((w) => (
            <span key={w} className="block rounded-sm bg-white" style={{ width: w, height: 2.5 }} />
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
        <nav aria-label="Primary" style={{ padding: '8px 22px 26px', animation: 'ssRise 0.42s var(--ease-out) both' }}>
          {MENU_LINKS.map((link) => {
            const body = (
              <>
                <span className="t-display text-[20px] font-semibold tracking-[-0.01em]">{link.label}</span>
                <span className="ml-auto text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>{link.meta}</span>
              </>
            )
            const props = {
              onClick: close,
              className: 'flex items-center gap-3 !text-white',
              style: { padding: '15px 0', borderBottom: '1px solid rgba(255,255,255,0.12)' },
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
