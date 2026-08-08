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
            style={{ width: 118, height: 56, boxShadow: '0 3px 12px rgba(27,22,32,0.08)' }}
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

export function Footer() {
  return (
    <footer className="widen">
      <div
        className="t-display text-center text-pretty"
        style={{
          padding: '40px 24px 34px',
          backgroundImage: 'var(--grad-yellow)',
          fontSize: 23, fontWeight: 700, lineHeight: 1.2, letterSpacing: '-0.02em',
        }}
      >
        TrendWatching and Serious Shift are trusted by 50,000+ members worldwide
      </div>

      <Marquee />

      <div
        className="flex flex-col items-center"
        style={{ padding: '52px 24px 56px', background: 'var(--color-darker)', gap: 30, color: '#fff' }}
      >
        <img
          src={LOGO} alt="Serious Shi(f)t, powered by TrendWatching"
          width={220} height={76}
          className="block h-[76px] w-[220px] object-contain"
        />
        {/* Dark ink, not white: white on #25D366 is 1.98:1 and unreadable.
            Ink is 8.96:1 and it is the same move the yellow pill already makes,
            so a bright brand colour carrying dark type reads as the house
            style rather than an exception. */}
        <a
          href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer"
          className="ss-cta inline-flex items-center"
          style={{
            height: 50, padding: '0 24px', borderRadius: 999, gap: 10,
            background: 'var(--color-whatsapp)', color: 'var(--color-ink)',
            fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700,
            letterSpacing: '0.08em', textTransform: 'uppercase',
            transition: 'transform 0.28s var(--ease-out), box-shadow 0.28s ease',
          }}
        >
          <img src={WHATSAPP_MARK} alt="" width={22} height={22} className="block size-[22px] object-contain" />
          Join us on WhatsApp
        </a>
      </div>
    </footer>
  )
}
