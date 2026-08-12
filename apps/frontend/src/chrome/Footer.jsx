/**
 * Three bands: the trust line on a yellow fade, an auto-scrolling logo rail,
 * and the black block with the lock-up and the subscribe CTA.
 *
 * The CTA is WhatsApp green with the WhatsApp mark. The delivered build drew it
 * in brand orange and an earlier sticky
 * orange and no mark, and the build is the spec.
 */
import { LOGOS, WHATSAPP_URL } from '../lib/site'

const LOGO = '/shift/serious-shift-logo-white.png'
const WHATSAPP_MARK = '/shift/whatsapp-logo.png'

/**
 * The list is rendered twice and translated by exactly -50%, so the second
 * copy is under the cursor at the moment the first ends and the seam never
 * shows. A single pass would snap back.
 */
function Marquee() {
  return (
    <div className="overflow-hidden bg-white" style={{ padding: '4px 0 26px' }} aria-hidden="true">
      <div className="flex w-max gap-[14px]" style={{ animation: 'ssMarquee 40s linear infinite' }}>
        {[...LOGOS, ...LOGOS].map((src, i) => (
          <span
            key={i}
            className="box-border flex shrink-0 items-center justify-center rounded-xl bg-white p-2"
            style={{
              width: 'calc(var(--bar-h) * 1.405)', height: 'calc(var(--bar-h) * 0.667)',
              boxShadow: '0 3px 12px rgba(27,22,32,0.08)',
            }}
          >
            <img
              src={src} alt="" loading="lazy" decoding="async"
              // Every client logo is exported at 240×114. CSS still sizes it;
              // the attributes only give the browser a ratio to hold.
              width={240} height={114}
              className="block max-h-full max-w-full object-contain"
              style={{ mixBlendMode: 'multiply' }}
            />
          </span>
        ))}
      </div>
    </div>
  )
}

/**
 * A footer is a page-level band: its surfaces run the full width of whatever
 * they sit in and only their CONTENTS are measured.
 *
 * It used to be `.widen`, which pinned all three bands to 940px and left a
 * ribbon floating under a 1440px page. That was a workaround for the real
 * problem — the pages rendered it *inside* the reading canvas and cancelled the
 * gutter with a negative margin, so it could never be wider than the column. It
 * is a sibling of the canvas now and simply fills its parent, which is what a
 * footer does at every width without a single fixed number.
 */
/**
 * `social` gates the trust line and client-logo rail. Every page shows them
 * since the 12 Aug 2026 review asked for the band back on the sphere pages,
 * reversing the 5 Aug "no social proof on those screens" note. The prop stays
 * because the next flip of this decision should be a one-caller change again.
 */
export function Footer({ social = true }) {
  return (
    <footer className="w-full">
      {social && (
        <div
          style={{
            padding: '40px 24px 34px',
            backgroundImage: 'var(--grad-yellow)',
          }}
        >
          <p
            className="t-display footer-inner text-center text-pretty"
            style={{ fontSize: 'var(--t-trust)', fontWeight: 700, lineHeight: 1.2, letterSpacing: '-0.02em' }}
          >
            TrendWatching and Serious Shift are trusted by 50,000+ members worldwide
          </p>
        </div>
      )}

      {social && <Marquee />}

      <div style={{ padding: '52px 24px 56px', background: 'var(--color-darker)', color: '#fff' }}>
        <div className="footer-inner flex flex-col items-center" style={{ gap: 30 }}>
        {/* 0.905 → 1.13 (same 2.892 aspect): the 5 Aug review flagged the
            "Powered by TrendWatching" line inside the PNG as unreadable at the
            old size. A re-cut asset with a larger byline is with design. */}
        <img
          src={LOGO} alt="Serious Shi(f)t, powered by TrendWatching"
          width={220} height={76}
          className="block object-contain"
          style={{ height: 'calc(var(--bar-h) * 1.13)', width: 'calc(var(--bar-h) * 3.268)' }}
        />
        {/* Dark ink, not white: white on #25D366 is 1.98:1 and unreadable.
            Ink is 8.96:1 and it is the same move the yellow pill already makes,
            so a bright brand colour carrying dark type reads as the house
            style rather than an exception. */}
        <a
          href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer"
          className="ss-cta inline-flex items-center"
          style={{
            height: 'var(--cta-h)', padding: '0 24px', borderRadius: 999, gap: 10,
            background: 'var(--color-whatsapp)', color: 'var(--color-ink)',
            fontFamily: 'var(--font-display)', fontSize: 'var(--t-cta)', fontWeight: 700,
            letterSpacing: '0.08em', textTransform: 'uppercase',
            transition: 'transform 0.28s var(--ease-out), box-shadow 0.28s ease',
          }}
        >
          <img src={WHATSAPP_MARK} alt="" width={22} height={22} className="block size-[22px] object-contain" />
          Join us on WhatsApp
        </a>
        </div>
      </div>
    </footer>
  )
}
