/**
 * TrustedBy — the "trusted by 30,000+ members worldwide" client-logo strip.
 *
 * Real brand marks aren't bundled yet, so we render tasteful monochrome
 * word-logos as a faithful placeholder (see plan → Open items). They sit
 * muted on the page canvas and lift to full ink on hover.
 */
const CLIENTS = [
  'Hero', 'TATA', 'SAMSUNG', 'dentsu',
  'Singapore Airlines', 'DANONE', 'RIVIAN', 'watsons',
]

export default function TrustedBy() {
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
      <p className="text-center font-mono text-[10px] sm:text-[11px] uppercase tracking-[0.2em] text-ink-faint mb-8">
        TrendWatching &amp; Serious Shift are trusted by 30,000+ members worldwide
      </p>
      <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-5">
        {CLIENTS.map((name) => (
          <span
            key={name}
            className="font-display font-bold text-base sm:text-lg text-ink-faint/70 hover:text-ink transition-colors select-none"
          >
            {name}
          </span>
        ))}
      </div>
    </section>
  )
}
