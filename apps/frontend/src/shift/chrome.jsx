/**
 * chrome.jsx — the black top bar, the menu overlay, and the site footer.
 *
 * The bar is the design's fixed black header; on a real device it absorbs the
 * notch via env(safe-area-inset-top) rather than the concept's hard-coded 58px
 * status-bar offset.
 */
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LOGOS, SOCIALS, SUBSCRIBE_URL, FOOTER_LINKS, MENU_LINKS } from './content'
import { useDomains } from './useDomains'

const LOGO = '/shift/serious-shift-logo-white.png'

/* ── Top bar + menu ──────────────────────────────────────────────────── */

export function TopBar() {
  const [open, setOpen] = useState(false)
  const { domains } = useDomains()
  const navigate = useNavigate()

  const go = (to) => { setOpen(false); navigate(to) }

  return (
    <>
      <header
        className="sticky top-0 z-40 bg-black a-fade"
        style={{ paddingTop: 'max(14px, env(safe-area-inset-top))' }}
      >
        <div className="mx-auto flex items-center justify-between px-[22px] pb-3.5 lg:max-w-[1180px] lg:px-8">
          <Link to="/" aria-label="Serious Shi(f)t — home" className="shrink-0">
            <img src={LOGO} alt="Serious Shi(f)t" width={110} height={38} className="block h-[34px] w-auto object-contain lg:h-[38px]" draggable="false" />
          </Link>
          <button
            type="button" onClick={() => setOpen((v) => !v)}
            aria-label="Menu" aria-expanded={open}
            className="flex cursor-pointer flex-col items-end gap-[5px] pb-2.5 pl-3.5 pt-1"
          >
            {[26, 20, 13].map((w) => (
              <span key={w} className="block h-[2.5px] rounded-sm bg-white transition-all" style={{ width: open ? 22 : w }} />
            ))}
          </button>
        </div>
      </header>

      {open && (
        <nav
          className="fixed inset-x-0 z-40 bg-black px-[22px] pb-[26px] pt-2 text-white"
          style={{ top: 'calc(max(14px, env(safe-area-inset-top)) + 48px)', animation: 'ssRise 0.42s var(--ease-out) both' }}
        >
          <div className="mx-auto lg:max-w-[1180px] lg:px-8">
            {domains.map((d) => (
              <MenuRow key={d.id} dot={d.dot} label={d.name} meta={`${d.count} shifts`} onClick={() => go(`/map/${d.slug}`)} />
            ))}
            <MenuRow dot="var(--color-yellow)" label="The room" meta="1,400 members" href={SUBSCRIBE_URL} onClick={() => setOpen(false)} />
            <MenuRow dot="var(--color-yellow)" label="Saved" meta="3 shifts" onClick={() => setOpen(false)} />

            {/* Secondary destinations — the wider Serious Shift / TrendWatching site. */}
            <div className="mt-5 flex flex-col gap-1 lg:flex-row lg:gap-8">
              {MENU_LINKS.map((l) => (
                <a
                  key={l.label} href={l.href} target="_blank" rel="noopener noreferrer"
                  onClick={() => setOpen(false)}
                  className="t-eyebrow py-2 !text-white/70 transition-colors hover:!text-[var(--color-yellow)]"
                >{l.label}</a>
              ))}
            </div>
          </div>
        </nav>
      )}
    </>
  )
}

function MenuRow({ dot, label, meta, onClick, href }) {
  const inner = (
    <>
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: dot }} />
      <span className="t-display text-xl" style={{ fontWeight: 600, letterSpacing: '-0.01em' }}>{label}</span>
      <span className="ml-auto text-xs" style={{ color: 'rgba(255,255,255,0.5)' }}>{meta}</span>
    </>
  )
  const cls = 'flex w-full items-center gap-3 border-b py-[15px] text-left !text-white transition-colors hover:!text-[var(--color-yellow)]'
  const style = { borderColor: 'rgba(255,255,255,0.12)' }

  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer" onClick={onClick} className={cls} style={style}>{inner}</a>
  ) : (
    <button type="button" onClick={onClick} className={cls} style={style}>{inner}</button>
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
          {SOCIALS.map((s) => (
            <a
              key={s} href={SUBSCRIBE_URL} target="_blank" rel="noopener noreferrer"
              className="t-display grid h-[34px] w-[34px] place-items-center rounded-full text-[13px] text-white transition-colors hover:!bg-[var(--color-yellow)] hover:!text-[var(--color-ink)]"
              style={{ border: '1px solid rgba(255,255,255,0.28)' }}
            >{s}</a>
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
              className="t-eyebrow !text-white/85 transition-colors hover:!text-[var(--color-yellow)]"
              style={{ fontSize: 14, fontWeight: 650, letterSpacing: '0.1em' }}
            >{l.label}</a>
          ))}
        </div>

        <div className="mt-1 text-[11px]" style={{ letterSpacing: '0.06em', color: 'rgba(255,255,255,0.45)' }}>
          © {new Date().getFullYear()} TrendWatching · Serious Shi(f)t
        </div>
      </div>
    </footer>
  )
}

const Rule = () => <div className="h-px w-full max-w-[620px]" style={{ background: 'rgba(255,255,255,0.18)' }} />
