/**
 * NavBar — the dark, rounded, floating top navigation.
 *
 * Present on every page (rendered once from App.jsx). Left: the Serious Shi(f)t
 * logo (always white on the dark bar). Center/right: the primary nav links.
 * Far right: the light/dark theme toggle. On mobile the links collapse behind
 * a hamburger that expands an in-bar menu.
 */
import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Icon } from '../../views/map/icons'
import { NAV_LINKS, SUBSCRIBE_URL } from './links'

function NavItem({ link, onClick, mobile = false }) {
  const base = mobile
    ? 'text-sm font-semibold tracking-wide uppercase py-2'
    : 'text-[11px] font-semibold tracking-widest uppercase transition-colors'
  const rest = 'text-[var(--nav-ink-dim)] hover:text-[var(--nav-ink)]'
  const active = 'text-[var(--nav-ink)]'

  if (link.to) {
    return (
      <NavLink
        to={link.to}
        end={link.to === '/map'}
        onClick={onClick}
        className={({ isActive }) => `${base} ${isActive ? active : rest}`}
      >
        {link.label}
      </NavLink>
    )
  }
  return (
    <a
      href={link.href}
      target="_blank"
      rel="noopener noreferrer"
      onClick={onClick}
      className={`${base} ${rest}`}
    >
      {link.label}
    </a>
  )
}

export default function NavBar({ theme, onToggleTheme }) {
  const [open, setOpen] = useState(false)

  return (
    <header className="sticky top-0 z-50 px-3 sm:px-6 pt-3 sm:pt-4">
      <div className="nav-bar max-w-7xl mx-auto">
        <div className="flex items-center justify-between gap-4 px-4 sm:px-6 h-16">
          {/* Logo */}
          <NavLink to="/" className="flex items-center shrink-0" aria-label="Serious Shi(f)t — home">
            <img
              src="/logo.png"
              alt="Serious Shi(f)t"
              className="ss-logo--on-dark h-8 sm:h-9 w-auto select-none"
              draggable="false"
            />
          </NavLink>

          {/* Desktop nav */}
          <nav className="hidden lg:flex items-center gap-6">
            {NAV_LINKS.map((l) => (
              <NavItem key={l.label} link={l} />
            ))}
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            <a
              href={SUBSCRIBE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="pill-cta hidden sm:inline-flex items-center px-4 py-2 text-[11px] font-semibold tracking-widest uppercase"
            >
              Subscribe
            </a>
            <button
              onClick={onToggleTheme}
              aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
              className="w-9 h-9 flex items-center justify-center rounded-full text-[var(--nav-ink-dim)] hover:text-[var(--nav-ink)] hover:bg-white/10 transition-colors"
            >
              {theme === 'light'
                ? <Icon.Moon className="w-4 h-4" />
                : <Icon.Sun className="w-4 h-4" />}
            </button>
            <button
              onClick={() => setOpen((v) => !v)}
              aria-label="Toggle menu"
              aria-expanded={open}
              className="lg:hidden w-9 h-9 flex items-center justify-center rounded-full text-[var(--nav-ink-dim)] hover:text-[var(--nav-ink)] hover:bg-white/10 transition-colors"
            >
              {open ? <Icon.Close className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile menu */}
        {open && (
          <nav className="lg:hidden animate-in border-t border-white/10 px-6 pb-4 pt-2 flex flex-col">
            {NAV_LINKS.map((l) => (
              <NavItem key={l.label} link={l} mobile onClick={() => setOpen(false)} />
            ))}
            <a
              href={SUBSCRIBE_URL}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="pill-cta mt-3 inline-flex justify-center items-center px-4 py-2.5 text-xs font-semibold tracking-widest uppercase"
            >
              Subscribe to Serious Shift
            </a>
          </nav>
        )}
      </div>
    </header>
  )
}

function MenuIcon(p) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" {...p}>
      <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
    </svg>
  )
}
