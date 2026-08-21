/**
 * Work with us — the site's one commercial CTA, on every shift page.
 *
 * It used to be the last cell of the Opportunity territories rail, so it only
 * ever rendered where `territories` was visible: Consumers. Three spheres out
 * of four never showed it at all, and on the fourth a reader had to swipe past
 * the last territory card to find it.
 *
 * It is not a contract module — it carries no per-shift data and must not be
 * something the visibility matrix can hide — but it READS as one: the pages
 * render it as the last child of the reading canvas, so it takes the column's
 * width and the `--module-gap` rhythm from the modules above it rather than
 * spanning the page like the footer.
 */
import { Link } from '../lib/router'

export function WorkWithUs() {
  return (
    <section className="wwu widen" aria-labelledby="wwu-title">
      <div className="wwu-card">
        <h2
          id="wwu-title" className="t-display text-balance"
          style={{ margin: 0, fontSize: 'var(--t-wwu)', fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.025em' }}
        >
          Ready for the shift?
        </h2>
        <p
          className="text-pretty"
          style={{ margin: 0, maxWidth: 430, fontSize: 14.5, lineHeight: 1.55, color: 'var(--color-ink-body)' }}
        >
          Work directly with our team to turn AI shifts into things worth building. From Bangkok to Boston.
        </p>
        {/* Same destination as the card this replaces — the About page's
            services section, per the 12 Aug 2026 Miro review. */}
        <Link to="/about#services" className="pill-contact">Talk To Us</Link>
      </div>
    </section>
  )
}
