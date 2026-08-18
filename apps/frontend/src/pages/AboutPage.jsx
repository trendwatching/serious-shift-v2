/**
 * About.jsx — the one authored page on the site.
 *
 * Everything else is a projection of the weekly map document; this is fixed
 * copy, so it lives in the repo rather than the database. That is deliberate:
 * it changes a few times a year, it must survive a failed map fetch, and
 * routing it through the publication pipeline would mean the page describing
 * the pipeline could be taken down by it.
 *
 * Six image-led sections, one full-bleed statement band, two service cards.
 * Ported from the delivered design build.
 */
import { Link } from '../lib/router'
import { useDocumentMeta } from '../lib/useDocumentMeta'
import { Footer } from '../chrome/Footer'
import { ABOUT_URL, CONTACT_URL, METHODOLOGY_URL, SUBSCRIBE_URL, TRENDWATCHING_URL, WHATSAPP_URL } from '../lib/site'

/**
 * Inline link: black text, black underline.
 *
 * The underline was magenta — the design's own treatment — until the 18 Aug
 * 2026 review: "red looks like pointing out a spelling error". The hover still
 * goes magenta, so the link keeps a colour response; only the resting rule is
 * ink. This is the site's only coloured text-decoration, so "everywhere" is
 * this one component.
 */
const A = ({ href, children }) => (
  <a
    href={href}
    target={href.startsWith('#') ? undefined : '_blank'}
    rel="noopener noreferrer"
    className="!text-[var(--color-ink)] underline decoration-[1.5px] underline-offset-[3px] transition-colors hover:!text-[#ED026B]"
    style={{ textDecorationColor: 'var(--color-ink)' }}
  >
    {children}
  </a>
)

/**
 * `after` renders inside the section, below its prose. The statement band needs
 * that: it bleeds to the viewport edges with `-22px` margins, which only reach
 * the edges from inside a container that is inset by 22px. As a sibling of the
 * sections it sat directly on the page root, which has no gutter, so the band
 * ran 22px past the right edge and gave /about a horizontal scrollbar.
 */
/**
 * Intrinsic pixel sizes, so the browser can reserve the space before the bytes
 * arrive.
 *
 * Without them an `h-auto w-full` image is zero pixels tall until it loads and
 * then pushes everything below it down. That is not only a layout shift: the
 * router scrolls to a `#section` in a layout effect, before any image has
 * loaded, so five of the six nav rows — all `/about#…` — landed 330–570px above
 * their heading, by a distance that changed with the network. It passed locally
 * on a fast machine and failed in CI, twice, at different offsets.
 *
 * Real width/height rather than one `aspect-ratio`, because these five differ:
 * 1.40, 1.59, 1.55, 1.36, 1.46.
 */
const IMAGE_DIMS = {
  '/shift/about-crowd.jpg': [1400, 999],
  '/shift/about-thinkers.jpg': [1400, 957],
  '/shift/about-team.jpg': [1400, 1026],
  '/shift/about-reports.jpg': [1400, 903],
  '/shift/about-playbook.jpg': [1400, 879],
  '/shift/about-whatsapp.jpg': [1400, 903],
}

/**
 * `paddingBlock`, not `padding`. The shorthand also sets padding-inline, and an
 * inline style beats every rule — so `padding: '36px 22px 40px'` on an element
 * carrying `.gutter` quietly pinned this page to a 22px gutter at every width
 * while the rest of the site moved to the fluid one. /about was the only page
 * whose measure did not match its neighbours, which is most of why it read as
 * a different site.
 */
const Section = ({ id, image, alt, eyebrow, children, after }) => (
  <section id={id} className="about-section canvas gutter anchor-top" style={{ paddingBlock: '36px 40px' }}>
    <div className="about-body">
      {image && (
        <div className="overflow-hidden rounded-[20px]">
          <img
            src={image} alt={alt} loading="lazy" decoding="async"
            width={IMAGE_DIMS[image]?.[0]} height={IMAGE_DIMS[image]?.[1]}
            className="block h-auto w-full"
          />
        </div>
      )}
      <div className="flex flex-col gap-3.5">
        <h2 className="about-eyebrow">{eyebrow}</h2>
        {children}
      </div>
    </div>
    {after}
  </section>
)

const P = ({ children }) => (
  <p className="text-[15px] leading-[1.6] text-pretty" style={{ color: '#3E3949' }}>{children}</p>
)

const ServiceCard = ({ n, title, children }) => (
  <div className="card flex flex-col gap-2.5 rounded-[20px] p-[18px]">
    <span className="flex items-center gap-2.5">
      <span
        className="t-display grid size-[26px] place-items-center rounded-full text-xs font-extrabold"
        style={{ background: 'var(--color-yellow)', color: 'var(--color-ink)' }}
      >{n}</span>
      <span className="t-display text-[15.5px] font-bold">{title}</span>
    </span>
    <span className="text-[14.5px] leading-[1.55] text-pretty" style={{ color: '#3E3949' }}>{children}</span>
  </div>
)

export default function About() {
  useDocumentMeta('About', 'Why Serious Shift exists, how we build it, and who is behind it.')

  return (
    <article className="min-h-dvh bg-white" style={{ animation: 'abRise 0.45s var(--ease-out)' }}>
      {/* The masthead had three separate faults, and together they are why this
          page looked broken rather than merely plain.

          It sat on the page root instead of in the canvas, so `w-prose` — which
          is not a class; Tailwind's is `max-w-prose`, and this one emitted no
          CSS at all — was the only thing meant to be holding it. The title and
          the standfirst therefore ran from x=0, hard against the viewport edge,
          while every section below them was centred in a 660px column.

          And it had `pt-8`, 32px, to clear a bar that is absolutely positioned
          and 84–116px tall. The Home pill was drawn entirely behind the black
          bar and the H1 started 24px behind it too. */}
      <header className="about-masthead canvas gutter" style={{ paddingTop: 'calc(var(--topbar) + 22px)', paddingBottom: 40 }}>
        <Link
          to="/"
          className="inline-flex h-[30px] items-center gap-[7px] rounded-full bg-white px-[13px] text-xs !text-[var(--color-ink)]"
          style={{ boxShadow: '0 3px 10px rgba(27,22,32,0.18)', fontFamily: 'var(--font-display)', fontWeight: 650 }}
        >
          <span aria-hidden="true" className="rotate-180 text-[13px] leading-none opacity-70">→</span>
          Home
        </Link>

        <h1 className="t-display leading-none" style={{ marginTop: 20, fontSize: 'var(--t-about)', letterSpacing: '-0.035em' }}>
          About<span className="italic">.</span>
        </h1>
        {/* The standfirst that sat here ("Why Serious Shift exists, how we
            build it, and who is behind it.") came out on the 18 Aug 2026
            review. It survives as the page's meta description, which is where
            a summary of the page belongs. */}
      </header>

      <Section
        image="/shift/about-crowd.jpg" alt="AI and society, as a collage of cut-out photographs" eyebrow="Why & who & what"
        after={(
          /* The one full-bleed band on the page. It is the argument the whole
             site rests on, so it gets the site's only black statement surface —
             and the design nests it inside this section, which is also the only
             place its negative margins land on the viewport edges. */
          <div className="bleed py-[30px]" style={{ marginTop: 4, background: 'var(--color-ink)' }}>
            <div className="flex flex-col gap-3 text-white">
              <span className="t-eyebrow" style={{ color: 'var(--color-yellow)' }}>The point</span>
              <span className="t-display text-2xl font-semibold leading-[1.28]" style={{ letterSpacing: '-0.018em' }}>
                Seriously, if not now, then when?
              </span>
            </div>
          </div>
        )}
      >
        <P>Everything predicted three years ago is now unfolding: AI is becoming the organizational engine and orchestrating layer. Agents are here. You can just feel the systems building.</P>
        <P>If you’re responsible for AI strategy, the stakes have changed dramatically. Your biggest challenge? Finding the time to understand what matters, and turning it into action beyond ‘prompting courses for everyone’.</P>
        <P>To the rescue: <strong>Serious Shift</strong>, powered by <A href={TRENDWATCHING_URL}>TrendWatching</A>, giving decision-makers a <A href={ABOUT_URL}>continuously updated intelligence layer</A> on how AI is reshaping consumers, organizations, economies and society.</P>
        <P>The signals, distilled into trends, opportunities and <strong>actions</strong>.</P>
      </Section>

      <Section id="methodology" image="/shift/about-thinkers.jpg" alt="The network of thinkers Serious Shift tracks" eyebrow="Methodology">
        <P>We relentlessly track 100+ of the world’s most consequential <A href={METHODOLOGY_URL}>thinkers</A> and organizations on AI and societal change, in real time. Alongside those voices, TrendWatching’s own <strong>experts</strong> contribute human and synthetic perspectives, sharpening the analysis and synthesis.</P>
        <P>The result: a living consensus drawn from the <strong>sharpest human and artificial minds</strong> in the field, updated as those minds update, and translated into the language of strategy rather than academia.</P>
      </Section>

      <Section id="services" image="/shift/about-team.jpg" alt="The TrendWatching team in a workshop" eyebrow="Services">
        <P>The TrendWatching team behind Serious Shift is developing a portfolio of services. First up:</P>
        <ServiceCard n="1" title="Bonus Content">
          TrendWatching Pioneer and Enterprise <A href={ABOUT_URL}>members</A> will soon receive a forever-updated report on <strong>AI × Consumer Behaviour Shifts</strong> + a new Serious Shift Ideation <A href={ABOUT_URL}>Playbook</A>.
        </ServiceCard>
        <ServiceCard n="2" title="Workshops">
          Sign up your team for a <strong>Serious Shift Workshop</strong>, translating the AI forces reshaping your industry into concrete future products and action plans.
        </ServiceCard>
        <P>To learn more, please contact <A href={CONTACT_URL}>Giulia Bolzan</A>, our Business Development Director.</P>
      </Section>

      <Section id="trendwatching" image="/shift/about-reports.jpg" alt="TrendWatching Fast Forward reports" eyebrow="TrendWatching">
        <P>Serious Shift is powered, created and curated by <A href={TRENDWATCHING_URL}>TrendWatching</A>, one of the world’s leading consumer trend firms. For more than 20 years, we’ve helped tens of thousands of business professionals worldwide spot emerging consumer trends and innovations, turning them into new products, services and strategies. <A href={TRENDWATCHING_URL}>More…</A></P>
      </Section>

      <Section image="/shift/about-playbook.jpg" alt="The Serious Shift Trends × AI × Strategy Playbook" eyebrow="Coming soon">
        <P>The Serious Shift website is in beta. We’re hard at work to <strong>bring the trend content alive</strong> (visuals, video, audio), to <strong>introduce a virtual trend analyst</strong> you can have a conversation with, and to <strong>develop ideation tools</strong> that let you take a trend and turn it directly into a strategy plan and related new business concept.</P>
        <P>The systems get smarter every week, so will Serious Shift, and so then will you.</P>
      </Section>

      <Section
        id="subscribe" image="/shift/about-whatsapp.jpg"
        alt="One shift each weekday, on WhatsApp" eyebrow="Subscribe / follow"
      >
        <P>Want to embark with us on a journey? <A href={WHATSAPP_URL}>Join us on WhatsApp</A> today, and receive one shift each weekday.</P>
        <P>And yes, do <A href={SUBSCRIBE_URL}>sign up for TrendWatching’s free membership</A> if you haven’t yet, so we can keep you updated on major new Serious Shift and TrendWatching features.</P>
        <a
          href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer"
          className="inline-flex h-12 items-center gap-[9px] self-start rounded-full px-[22px] text-[15px] transition-transform duration-300 hover:-translate-y-0.5"
          style={{
            background: 'var(--color-whatsapp)', color: 'var(--color-ink)',
            fontFamily: 'var(--font-display)', fontWeight: 650,
          }}
        >
          <img src="/shift/whatsapp-logo.png" alt="" width={22} height={22} className="block size-[22px] object-contain" />
          Join us on WhatsApp
        </a>
      </Section>

      <Footer />
    </article>
  )
}
