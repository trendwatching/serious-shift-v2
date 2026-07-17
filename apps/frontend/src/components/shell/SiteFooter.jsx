/**
 * SiteFooter — the white→yellow gradient footer band with the subscribe CTA.
 * Rendered once per page from App.jsx, after IdeateSection + TrustedBy.
 */
import { Link } from 'react-router-dom'
import { FOOTER_LINKS, SUBSCRIBE_URL } from './links'

function FooterLink({ link }) {
  const cls =
    'font-display font-semibold text-xl sm:text-2xl text-ink hover:text-accent transition-colors'
  return link.to ? (
    <Link to={link.to} className={cls}>{link.label}</Link>
  ) : (
    <a href={link.href} target="_blank" rel="noopener noreferrer" className={cls}>
      {link.label}
    </a>
  )
}

export default function SiteFooter() {
  return (
    <footer className="footer-band mt-4">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
        <div className="grid gap-10 md:grid-cols-[1fr_1fr_1.1fr] md:gap-8">
          {/* Brand */}
          <div>
            <img
              src="/logo.png"
              alt="Serious Shi(f)t"
              className="ss-logo h-10 w-auto select-none"
              draggable="false"
            />
            <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-soft">
              powered by TrendWatching
            </p>
          </div>

          {/* Explainer prompts */}
          <nav className="flex flex-col gap-4">
            {FOOTER_LINKS.map((l) => (
              <FooterLink key={l.label} link={l} />
            ))}
          </nav>

          {/* Subscribe */}
          <div className="md:border-l md:border-ink/15 md:pl-8">
            <h2 className="font-display font-bold text-2xl sm:text-3xl text-ink leading-tight mb-3">
              Find out here before anywhere else.
            </h2>
            <p className="text-ink-soft text-sm mb-6 max-w-sm">
              Click the subscribe button to be the first one to know.
            </p>
            <a
              href={SUBSCRIBE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="pill-cta inline-flex items-center px-7 py-3.5 text-sm font-semibold tracking-wide"
            >
              Subscribe to Serious Shift
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
