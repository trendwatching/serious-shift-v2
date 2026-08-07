/**
 * chrome.jsx — the black top bar with its nav panel, and the three-band footer.
 *
 * Both are ports of the delivered design build, with two deliberate departures:
 *
 *  * the bar absorbs the notch via `env(safe-area-inset-top)` rather than the
 *    build's hard-coded 56px status-bar offset, which only looks right inside
 *    the mockup's iPhone frame;
 *  * the nav is a `<dialog>` on mobile rather than an absolutely-positioned div,
 *    so it traps focus and closes on Escape for free.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from '../router'
import { LOGOS, MENU_LINKS, WHATSAPP_URL } from './site'

const LOGO = '/shift/serious-shift-logo-white.png'
const WHATSAPP = '/shift/whatsapp-logo.png'

/* ── Top bar + nav ───────────────────────────────────────────────────── */

export function TopBar() {
  const [open, setOpen] = useState(false)
  const dialogRef = useRef(null)
  const triggerRef = useRef(null)
  const closeRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return undefined
    if (open && !dialog.open) {
      dialog.showModal()
      requestAnimationFrame(() => closeRef.current?.focus())
    }
    if (!open && dialog.open) dialog.close()
    if (!open) return undefined

    const previous = document.documentElement.style.overflow
    const desktop = window.matchMedia('(min-width: 64rem)')
    const closeAtDesktop = (event) => { if (event.matches) setOpen(false) }
    desktop.addEventListener('change', closeAtDesktop)
    document.documentElement.style.overflow = 'hidden'
    return () => {
      desktop.removeEventListener('change', closeAtDesktop)
      document.documentElement.style.overflow = previous
    }
  }, [open])

  const close = () => {
    setOpen(false)
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  return (
    <>
      <header
        className="a-fade sticky top-0 z-40 bg-black"
        style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}
      >
        <div className="mx-auto flex items-center justify-between px-[22px] pb-4 lg:max-w-[1180px] lg:px-8">
          <Link to="/" aria-label="Serious Shi(f)t — home" className="flex min-h-11 shrink-0 items-center">
            {/* The lockup carries "powered by TrendWatching" inside the artwork,
                so it is sized to keep that sub-line readable — a Miro sticky
                called it out as too small to read at the original scale. */}
            <img
              src={LOGO} alt="Serious Shi(f)t" width={214} height={74} draggable="false"
              className="block h-[52px] w-auto object-contain lg:h-[60px]"
            />
          </Link>

          <button
            ref={triggerRef}
            type="button" onClick={() => setOpen((v) => !v)}
            aria-label="Open navigation" aria-expanded={open} aria-controls="site-navigation"
            className="grid h-11 w-11 cursor-pointer place-content-center justify-items-end gap-[5px] lg:hidden"
          >
            {/* Three bars of falling width — the build's mark, not a plain ≡. */}
            {[26, 20, 13].map((w) => (
              <span key={w} className="block h-[2.5px] rounded-sm bg-white transition-all" style={{ width: open ? 22 : w }} />
            ))}
          </button>

          <nav aria-label="Primary" className="hidden items-center gap-6 lg:flex">
            {MENU_LINKS.map((link) => (
              <NavLink key={link.label} link={link} className="t-eyebrow inline-flex min-h-11 items-center !text-white hover:!text-[var(--color-yellow)]" />
            ))}
          </nav>
        </div>
      </header>

      <dialog
        ref={dialogRef}
        id="site-navigation"
        aria-label="Site navigation"
        onCancel={(event) => { event.preventDefault(); close() }}
        onClose={() => setOpen(false)}
        className="m-0 h-dvh max-h-none w-full max-w-none border-0 bg-black p-0 text-white lg:hidden"
      >
        <div className="flex min-h-full flex-col px-[22px] pb-8" style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}>
          <div className="flex h-[52px] items-center justify-between">
            <img src={LOGO} alt="Serious Shi(f)t" width={214} height={74} className="block h-[52px] w-auto object-contain" />
            <button ref={closeRef} type="button" onClick={close} aria-label="Close navigation" className="grid h-11 w-11 place-items-center rounded-full text-3xl text-white hover:bg-white/15">×</button>
          </div>
          <nav aria-label="Primary" className="mt-6 flex flex-col">
            {MENU_LINKS.map((link) => (
              <NavLink
                key={link.label} link={link} onNavigate={close}
                className="flex min-h-14 items-center gap-3 py-[15px] !text-white hover:!text-[var(--color-yellow)]"
                style={{ borderBottom: '1px solid rgba(255,255,255,0.12)' }}
              >
                <span className="t-display text-[20px] font-semibold tracking-[-0.01em]">{link.label}</span>
                <span className="ml-auto text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>{link.meta}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </dialog>
    </>
  )
}

/** One nav row, internal or external, with the label as the default body. */
function NavLink({ link, onNavigate, children, ...props }) {
  const body = children ?? link.label
  return link.internal ? (
    <Link to={link.href} onClick={onNavigate} {...props}>{body}</Link>
  ) : (
    <a href={link.href} target="_blank" rel="noopener noreferrer" onClick={onNavigate} {...props}>{body}</a>
  )
}

/* ── Footer ──────────────────────────────────────────────────────────── */

/**
 * The logo rail. The list is rendered twice and translated by exactly -50%, so
 * the second copy is under the cursor at the moment the first ends and the seam
 * is invisible. Duplicating is what makes that possible — a single pass would
 * snap back.
 */
function Marquee() {
  const row = [...LOGOS, ...LOGOS]
  return (
    <div className="overflow-hidden bg-white pb-[26px] pt-1" aria-hidden="true">
      <div className="flex w-max gap-3.5" style={{ animation: 'ssMarquee 40s linear infinite' }}>
        {row.map((src, i) => (
          <span
            key={i}
            className="box-border flex h-14 w-[118px] shrink-0 items-center justify-center rounded-xl bg-white p-2"
            style={{ boxShadow: '0 3px 12px rgba(27,22,32,0.08)' }}
          >
            <img src={src} alt="" loading="lazy" decoding="async" className="block max-h-full max-w-full object-contain" style={{ mixBlendMode: 'multiply' }} />
          </span>
        ))}
      </div>
    </div>
  )
}

export function ShiftFooter() {
  return (
    <footer className="w-full">
      <div
        className="t-display px-6 pb-[34px] pt-10 text-center text-[23px] leading-[1.2] text-pretty"
        style={{ backgroundImage: 'var(--grad-yellow)', letterSpacing: '-0.02em', color: 'var(--color-ink)' }}
      >
        <span className="mx-auto block max-w-[620px]">
          TrendWatching and Serious Shift are trusted by 50,000+ members worldwide
        </span>
      </div>

      <Marquee />

      <div
        className="flex flex-col items-center gap-[30px] px-6 pb-14 pt-[52px] text-white"
        style={{ background: 'var(--color-darker)' }}
      >
        <img src={LOGO} alt="Serious Shi(f)t, powered by TrendWatching" width={220} height={76} className="block h-[76px] w-auto object-contain" />

        {/* WhatsApp green rather than the build's rust, per the resolved sticky:
            the pill carries the WhatsApp mark, so it has to be WhatsApp's own
            colour or the mark reads as decoration. */}
        <a
          href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer"
          className="inline-flex h-[50px] items-center gap-[11px] rounded-full px-[26px] text-[15px] font-bold uppercase tracking-[0.08em] !text-white transition-transform duration-300 hover:-translate-y-0.5"
          style={{ background: '#25D366', fontFamily: 'var(--font-display)' }}
        >
          <img src={WHATSAPP} alt="" width={24} height={24} className="block size-6 object-contain" />
          Join us on WhatsApp
        </a>

        {/* Not in the design build. A site with no ownership line is an
            oversight in a mockup, not a decision. */}
        <div className="text-[11px]" style={{ letterSpacing: '0.06em', color: 'rgba(255,255,255,0.6)' }}>
          © {new Date().getFullYear()} TrendWatching
        </div>
      </div>
    </footer>
  )
}
