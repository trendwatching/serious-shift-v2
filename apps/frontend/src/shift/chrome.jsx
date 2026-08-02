/**
 * chrome.jsx — the black top bar, the menu overlay, and the site footer.
 *
 * The bar is the design's fixed black header; on a real device it absorbs the
 * notch via env(safe-area-inset-top) rather than the concept's hard-coded 58px
 * status-bar offset.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { LOGOS, SOCIALS, SUBSCRIBE_URL, FOOTER_LINKS, MENU_LINKS } from './site'

const LOGO = '/shift/serious-shift-logo-white.png'

/* ── Top bar + menu ──────────────────────────────────────────────────── */

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
        className="sticky top-0 z-40 bg-black a-fade"
        style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}
      >
        <div className="mx-auto flex items-center justify-between px-[22px] pb-3.5 lg:max-w-[1180px] lg:px-8">
          <Link to="/" aria-label="Serious Shi(f)t — home" className="flex min-h-11 shrink-0 items-center">
            <img src={LOGO} alt="Serious Shi(f)t" width={110} height={38} className="block h-[34px] w-auto object-contain lg:h-[38px]" draggable="false" />
          </Link>
          <button
            ref={triggerRef}
            type="button" onClick={() => setOpen((v) => !v)}
            aria-label="Open navigation" aria-expanded={open} aria-controls="mobile-navigation"
            className="grid h-11 w-11 cursor-pointer place-content-center justify-items-end gap-[5px] lg:hidden"
          >
            {[26, 20, 13].map((w) => (
              <span key={w} className="block h-[2.5px] rounded-sm bg-white transition-all" style={{ width: open ? 22 : w }} />
            ))}
          </button>

          <nav aria-label="Primary" className="hidden items-center gap-6 lg:flex">
            {MENU_LINKS.map((link) => link.internal ? (
              <Link key={link.label} to={link.href} className="t-eyebrow inline-flex min-h-11 items-center !text-white hover:!text-[var(--color-yellow)]">
                {link.label}
              </Link>
            ) : (
              <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer" className="t-eyebrow inline-flex min-h-11 items-center !text-white hover:!text-[var(--color-yellow)]">
                {link.label}
              </a>
            ))}
          </nav>
        </div>
      </header>

      <dialog
        ref={dialogRef}
        id="mobile-navigation"
        aria-label="Site navigation"
        onCancel={(event) => { event.preventDefault(); close() }}
        onClose={() => setOpen(false)}
        className="m-0 h-dvh max-h-none w-full max-w-none border-0 bg-black p-0 text-white lg:hidden"
      >
        <div className="flex min-h-full flex-col px-[22px] pb-8" style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}>
          <div className="flex h-12 items-center justify-between">
            <img src={LOGO} alt="Serious Shi(f)t" width={110} height={38} className="block h-[34px] w-auto object-contain" />
            <button ref={closeRef} type="button" onClick={close} aria-label="Close navigation" className="grid h-11 w-11 place-items-center rounded-full text-3xl text-white hover:bg-white/15">×</button>
          </div>
          <nav aria-label="Primary" className="mt-8 flex flex-1 flex-col justify-center">
            {MENU_LINKS.map((link, index) => link.internal ? (
              <Link key={link.label} to={link.href} onClick={close} className="flex min-h-14 items-center border-b !text-white hover:!text-[var(--color-yellow)]" style={{ borderColor: 'rgba(255,255,255,0.18)' }}>
                <span className="mr-4 font-mono text-xs text-white/65">{String(index + 1).padStart(2, '0')}</span>
                <span className="t-display text-[clamp(25px,8vw,34px)]">{link.label}</span>
              </Link>
            ) : (
              <a key={link.label} href={link.href} target="_blank" rel="noopener noreferrer" onClick={close} className="flex min-h-14 items-center border-b !text-white hover:!text-[var(--color-yellow)]" style={{ borderColor: 'rgba(255,255,255,0.18)' }}>
                <span className="mr-4 font-mono text-xs text-white/65">{String(index + 1).padStart(2, '0')}</span>
                <span className="t-display text-[clamp(25px,8vw,34px)]">{link.label}</span>
              </a>
            ))}
          </nav>
        </div>
      </dialog>
    </>
  )
}

/* ── Footer ──────────────────────────────────────────────────────────── */

function Marquee() {
  const row = [...LOGOS, ...LOGOS]
  return (
    <div className="overflow-hidden bg-white pb-[26px] pt-1">
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

      <div className="flex flex-col items-center gap-[26px] px-6 pb-10 pt-11 text-white" style={{ background: 'var(--color-darker)' }}>
        <img src={LOGO} alt="Serious Shi(f)t" width={127} height={44} className="block h-11 w-auto object-contain" />

        <div className="flex items-center gap-[26px]">
          {SOCIALS.map((social) => (
            <a
              key={social.label} href={social.href} target="_blank" rel="noopener noreferrer"
              aria-label={`TrendWatching on ${social.label}`}
              className="t-display grid h-11 w-11 place-items-center rounded-full text-[13px] text-white transition-colors hover:!bg-[var(--color-yellow)] hover:!text-[var(--color-ink)]"
            ><span className="grid h-[34px] w-[34px] place-items-center rounded-full" style={{ border: '1px solid rgba(255,255,255,0.5)' }}>{social.mark}</span></a>
          ))}
        </div>

        <Rule />

        <div className="flex flex-col items-center gap-3 text-center">
          <span className="t-display text-[21px] leading-[1.16]" style={{ letterSpacing: '-0.022em' }}>Find out first.</span>
          <span className="text-sm leading-[1.45]" style={{ color: 'rgba(255,255,255,0.72)' }}>Be the first to know.</span>
          <a href={SUBSCRIBE_URL} target="_blank" rel="noopener noreferrer" className="pill-cta mt-1.5 h-12 px-6 text-[15px]">
            Subscribe to Serious Shift
          </a>
        </div>

        <Rule />

        <div className="flex flex-col items-center gap-[18px] lg:flex-row lg:gap-10">
          {FOOTER_LINKS.map((l) => (
            <a
              key={l.label} href={l.href} target="_blank" rel="noopener noreferrer"
              className="t-eyebrow inline-flex min-h-11 items-center !text-white/85 transition-colors hover:!text-[var(--color-yellow)]"
              style={{ fontSize: 14, fontWeight: 650, letterSpacing: '0.1em' }}
            >{l.label}</a>
          ))}
        </div>

        <div className="mt-1 text-[11px]" style={{ letterSpacing: '0.06em', color: 'rgba(255,255,255,0.72)' }}>
          © {new Date().getFullYear()} TrendWatching · Serious Shi(f)t
        </div>
      </div>
    </footer>
  )
}

const Rule = () => <div className="h-px w-full max-w-[620px]" style={{ background: 'rgba(255,255,255,0.18)' }} />
