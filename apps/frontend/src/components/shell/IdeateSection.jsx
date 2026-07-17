/**
 * IdeateSection — the recurring "Ideate with us!" paid-services promo band.
 *
 * Appears near the foot of every page (above TrustedBy + Footer). Pitches
 * the workshops offering and nods to the LLMs behind the intelligence.
 */
import { WORKSHOPS_URL } from './links'

const MODELS = ['ChatGPT', 'Claude', 'Gemini']

export default function IdeateSection() {
  return (
    <section className="max-w-7xl mx-auto px-4 sm:px-6">
      <div
        className="relative overflow-hidden rounded-3xl border border-hairline px-6 sm:px-12 py-10 sm:py-14"
        style={{ background: 'color-mix(in oklab, var(--color-c-society) 6%, var(--color-paper))' }}
      >
        {/* soft decorative glow */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full blur-3xl opacity-40"
          style={{ background: 'radial-gradient(circle, var(--color-c-economy), transparent 70%)' }}
        />
        <div className="relative grid gap-8 md:grid-cols-[1.4fr_1fr] md:items-center">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-accent mb-3">
              Paid services
            </p>
            <h2 className="font-display text-3xl sm:text-4xl text-ink leading-tight mb-3">
              Ideate with us!
            </h2>
            <p className="text-ink-soft text-base leading-relaxed max-w-xl mb-6">
              Turn these shifts into your own daring opportunities. Learn from top
              experts and their thinking on how AI will transform society, the
              economy, consumers and organisations — then run a workshop with us.
            </p>
            <a
              href={WORKSHOPS_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="pill-cta inline-flex items-center px-6 py-3 text-sm font-semibold tracking-wide"
            >
              Explore workshops →
            </a>
          </div>

          {/* LLM chip cluster */}
          <div className="flex md:justify-end">
            <div className="flex flex-wrap gap-3 max-w-xs">
              {MODELS.map((m) => (
                <span
                  key={m}
                  className="rounded-full border border-hairline bg-paper px-4 py-2 text-sm font-medium text-ink-soft shadow-sm"
                >
                  {m}
                </span>
              ))}
              <span className="rounded-full px-4 py-2 text-sm font-semibold text-accent">
                + more
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
