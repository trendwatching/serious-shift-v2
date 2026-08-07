/**
 * pages.jsx — the three routed reading views.
 *
 *   /map/:domainSlug                    → DomainSheet  (gradient header + shift list)
 *   /map/:domainSlug/:ktSlug            → ShiftDetail
 *   /map/:domainSlug/:ktSlug/:subSlug   → SubShiftDetail
 *
 * Each is a real route so shifts deep-link and the browser Back button works;
 * the entrance animation is what gives them the design's "sheet slides up" feel.
 *
 * The two detail views deliberately contain no section logic: the page body is
 * whatever module list the backend supplied, rendered by <Modules>. Adding,
 * removing or reordering a section is a data change (see modules.jsx).
 */
import { useEffect } from 'react'
import { Link, useParams } from '../router'
import { useDocumentMeta } from '../hooks/useDocumentMeta'
import { useResolved } from './useDomains'
import { ShiftFooter } from './chrome'
import { Breadcrumb, BreadcrumbMenu } from './Breadcrumb'
import { Modules } from './modules'
import { GradientHero, Eyebrow, Frame } from './sections'
import { quoteTitle } from './theme'
import { failureState } from './failure'

/**
 * The breadcrumb floats over the hero rather than docking under the header.
 *
 * That is the design's placement, and it is also what lets the hero keep its
 * full height: a docked trail would eat 40px from every reading view. It
 * replaces the circular back chevron the earlier mockups carried — one control
 * that says where you are beats one that only says "back".
 */
const CrumbLayer = ({ children }) => (
  <div className="pointer-events-none absolute inset-x-0 z-[48]" style={{ top: 'calc(var(--topbar) + 30px)' }}>
    <Frame><div className="w-prose pointer-events-auto max-w-[320px]">{children}</div></Frame>
  </div>
)

/** Frame plus the module rhythm — the body of a shift or sub-shift page.
 *
 * `Frame` is the wide track; each module is pulled back to `--measure` or left
 * at `--frame` by the wrapper in modules.jsx, so this file no longer decides
 * how wide anything is. */
const Column = ({ children }) => (
  <Frame className="flex flex-col gap-[var(--module-gap)] pt-[26px] md:pt-10 lg:pt-12">{children}</Frame>
)

function Missing({ what }) {
  useDocumentMeta('Page not found', undefined, { notFound: true })
  return (
    <div className="grid min-h-[60vh] place-items-center px-6 text-center">
      <div className="flex flex-col items-center gap-4">
        <Eyebrow color="var(--color-ink-dim)">Not found</Eyebrow>
        <h1 className="t-display text-2xl">We couldn’t find that {what}.</h1>
        <Link to="/" className="pill-yellow">Back to the domains</Link>
      </div>
    </div>
  )
}

/** The map document could not be loaded. Distinct from "not found": nothing is
 *  readable right now, and saying so is better than rendering stale prose. */
export function Unavailable({ error, onRetry }) {
  const failure = failureState(error)
  return (
    <div className="grid min-h-[60vh] place-items-center px-6 text-center">
      <div className="flex flex-col items-center gap-4">
        <Eyebrow color="var(--color-ink-dim)">{failure.eyebrow}</Eyebrow>
        <h1 className="t-display text-2xl">{failure.title}</h1>
        <p className="max-w-[380px]" style={{ color: 'var(--color-ink-soft)' }}>
          {failure.body}
        </p>
        {onRetry && <button type="button" className="pill-yellow" onClick={onRetry}>Retry</button>}
      </div>
    </div>
  )
}

const Loading = () => <div className="grid min-h-[60vh] place-items-center px-6" aria-busy="true" aria-label="Loading map content"><div className="w-full max-w-[660px] animate-pulse space-y-4" aria-hidden="true"><div className="h-10 w-2/3 rounded-lg bg-black/10"/><div className="h-24 rounded-2xl bg-black/10"/><div className="h-40 rounded-2xl bg-black/10"/></div></div>

function StaleNotice({ show, onRetry }) {
  if (!show) return null
  return <div role="status" className="mx-auto mt-4 flex min-h-11 max-w-[660px] items-center justify-between gap-4 rounded-xl bg-[var(--color-yellow)] px-4 text-sm"><span>Showing saved data because the live refresh failed.</span><button type="button" onClick={onRetry} className="min-h-11 font-bold underline underline-offset-4">Retry</button></div>
}

function SiblingNavigation({ previous, next, hrefFor, label }) {
  if (!previous && !next) return null
  return (
    <Frame className="mt-10">
      <nav aria-label={label} className="w-prose grid grid-cols-2 gap-3 border-t pt-6" style={{ borderColor: 'var(--color-hairline)' }}>
        <h2 className="sr-only">{label}</h2>
        {previous ? (
          <Link to={hrefFor(previous)} className="card card-lift flex min-h-20 flex-col justify-center gap-1 p-4" rel="prev">
            <span className="t-eyebrow" style={{ color: 'var(--color-ink-dim)' }}>← Previous</span>
            <span className="t-title text-[14px] leading-[1.25]" style={{ color: 'var(--color-ink)' }}>{quoteTitle(previous.title)}</span>
          </Link>
        ) : <span />}
        {next && (
          <Link to={hrefFor(next)} className="card card-lift flex min-h-20 flex-col items-end justify-center gap-1 p-4 text-right" rel="next">
            <span className="t-eyebrow" style={{ color: 'var(--color-ink-dim)' }}>Next →</span>
            <span className="t-title text-[14px] leading-[1.25]" style={{ color: 'var(--color-ink)' }}>{quoteTitle(next.title)}</span>
          </Link>
        )}
      </nav>
    </Frame>
  )
}

/* ── Domain sheet ────────────────────────────────────────────────────────── */

export function DomainSheet() {
  const { domainSlug } = useParams()
  const { domain, loading, unavailable, stale, error, retry } = useResolved({ domainSlug })
  useDocumentMeta(domain?.name, domain?.blurb)

  if (loading && !domain) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain) return <Missing what="domain" />

  return (
    <article className="a-expand relative min-h-dvh" data-domain={domain.id} style={{ backgroundImage: domain.grad }}>
      <CrumbLayer>
        <Breadcrumb crumb={domain.crumb} items={[{ label: 'Home', to: '/' }, { label: domain.name }]} />
      </CrumbLayer>

      <GradientHero
        grad={domain.grad}
        face="display"
        minHeight={340}
        bottomPad={62}
        eyebrow={`${domain.num} / 04`}
        title={domain.name}
        blurb={domain.blurb}
      />

      {/* The sheet rides up over the gradient. The overlap is what makes it read
          as a card lifted off the hero rather than the next band down. */}
      <div
        className="relative z-[2] min-h-[520px] bg-white pb-[130px] pt-2"
        style={{ borderRadius: '28px 28px 0 0', marginTop: -34 }}
      >
        <StaleNotice show={stale} onRetry={retry} />
        <Frame>
          {/* The shift list is read line by line, so it stays at the measure
              even though the frame around it is wider. */}
          <div className="w-prose">
            <h2 className="sr-only">Key shifts</h2>
            {domain.keyShifts.map((s, i) => (
              <Link
                key={s.id}
                to={`/map/${domain.slug}/${s.slug}`}
                className="a-rise flex gap-4 border-b py-[22px] transition-colors hover:bg-[var(--color-paper)]"
                style={{ borderColor: 'var(--color-hairline-soft)', animationDelay: `${(0.06 + i * 0.07).toFixed(2)}s` }}
              >
                <div className="pt-1 font-mono text-xs" style={{ color: 'var(--color-ink-faint)' }}>{s.num}</div>
                <div className="flex flex-1 flex-col gap-1.5">
                  <h3 className="t-title text-[19px] leading-[1.2] md:text-[21px] lg:text-[22px]" style={{ color: 'var(--color-ink)' }}>{quoteTitle(s.title)}</h3>
                  <p className="t-body" style={{ color: 'var(--color-ink-mid)' }}>{s.dek}</p>
                  {/* Type and read time only. The design drops velocity here:
                      the row is a decision about whether to open the page, and
                      "rising" does not help make it. */}
                  <p className="text-xs" style={{ color: 'var(--color-ink-dim)' }}>Key shift · {s.read}</p>
                </div>
              </Link>
            ))}
          </div>

          {/* The synthesis phase writes a few cross-cutting insights per domain
              every run. This is where they land — short cards, so they take the
              wide track and read as a grid rather than a stack. */}
          {domain.insights?.length > 0 && (
            <section className="w-wide flex flex-col gap-2.5 pt-10">
              <Eyebrow as="h2">What it adds up to</Eyebrow>
              <div className="grid gap-2.5 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
                {domain.insights.map((s) => (
                  <div key={s.id} className="card flex flex-col gap-2 p-4 lg:p-5">
                    <h3 className="t-display text-[15px] leading-[1.25] lg:text-[17px]" style={{ letterSpacing: '-0.01em' }}>{s.name}</h3>
                    <p className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{s.description}</p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </Frame>
      </div>

      <ShiftFooter />
    </article>
  )
}

/* ── Shift detail ────────────────────────────────────────────────────────── */

export function ShiftDetail() {
  const { domainSlug, ktSlug } = useParams()
  const { domain, shift, shiftSiblings, loading, unavailable, stale, error, retry } = useResolved({ domainSlug, ktSlug })
  useDocumentMeta(shift?.title, shift?.dek)

  if (loading && !shift) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift) return <Missing what="shift" />

  return (
    <article className="a-expand relative min-h-dvh bg-white" data-domain={domain.id}>
      <CrumbLayer>
        <Breadcrumb
          crumb={domain.crumb}
          items={[
            { label: 'Home', to: '/' },
            { label: domain.name, to: `/map/${domain.slug}` },
            { label: shift.title.replace(/[“”"]/g, '') },
          ]}
        />
      </CrumbLayer>

      <GradientHero
        grad={domain.grad}
        stripes
        image={shift.heroImage}
        imageWash="linear-gradient(180deg, rgba(245,0,127,0.42) 0%, rgba(200,0,107,0.5) 46%, rgba(74,0,39,0.9) 100%)"
        minHeight={shift.heroImage ? 560 : 340}
        // A key shift is the one page long enough for the hero to earn a
        // shrink: it hands the reader the title, then gets out of the way.
        shrink={shift.heroImage
          ? { from: 620, to: 340, rate: 0.85, fontFrom: 46, fontTo: 29, fontRate: 0.055 }
          : undefined}
        eyebrow={`${domain.name} · ${shift.kicker}`}
        title={shift.title}
      />

      <StaleNotice show={stale} onRetry={retry} />

      <Column>
        <Modules
          modules={shift.modules}
          ctx={{
            scope: 'shift',
            domain,
            subs: shift.subshifts,
            basePath: `/map/${domain.slug}/${shift.slug}`,
          }}
        />
      </Column>

      <SiblingNavigation
        {...shiftSiblings}
        label="Adjacent key shifts"
        hrefFor={(item) => `/map/${domain.slug}/${item.slug}`}
      />

      <div className="mt-[22px]"><ShiftFooter /></div>
    </article>
  )
}

/* ── Sub-shift detail ────────────────────────────────────────────────────── */

export function SubShiftDetail() {
  const { domainSlug, ktSlug, subSlug } = useParams()
  const { domain, shift, sub, subSiblings, loading, unavailable, stale, error, retry } = useResolved({ domainSlug, ktSlug, subSlug })
  useDocumentMeta(sub?.title, sub?.dek)

  // A sub-shift is a fresh reading context — always open at the top.
  useEffect(() => { window.scrollTo(0, 0) }, [subSlug])

  if (loading && !sub) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift || !sub) return <Missing what="sub-shift" />

  return (
    <article className="a-expand relative min-h-dvh bg-white" data-domain={domain.id}>
      {/* The menu variant, not the trail. A sub-shift is navigationally
          terminal — the design gives it no sibling rail, no related shifts and
          no next pager — so the crumb has to be the way sideways as well as up,
          and it lists the whole domain rather than only the ancestors. */}
      <CrumbLayer>
        <BreadcrumbMenu
          label={sub.title.replace(/[“”"]/g, '')}
          domainLabel={domain.name}
          domainTo={`/map/${domain.slug}`}
          crumb={domain.crumb}
          dot={domain.dot}
          activeShift={shift.slug}
          activeSub={sub ? shift.subshifts.findIndex((s) => s.slug === sub.slug) : null}
          groups={domain.keyShifts.map((k) => ({
            slug: k.slug,
            title: k.title.replace(/[“”"]/g, ''),
            to: `/map/${domain.slug}/${k.slug}`,
            subs: k.subshifts.map((s) => ({
              slug: s.slug,
              title: s.title.replace(/[“”"]/g, ''),
              to: `/map/${domain.slug}/${k.slug}/${s.slug}`,
            })),
          }))}
        />
      </CrumbLayer>

      {/* Sunset, not the domain gradient. A sub-shift is a level down, and the
          design marks that with a fixed palette rather than a darker version of
          the parent — which would have read as the same page again. */}
      <GradientHero
        grad="var(--grad-sunset)"
        face="display"
        minHeight={sub.heroImage ? 420 : 300}
        image={sub.heroImage}
        imageWash="linear-gradient(180deg, rgba(27,22,32,0) 42%, rgba(74,0,39,0.72) 100%)"
        eyebrow={<><Link to={`/map/${domain.slug}/${shift.slug}`} className="!text-[var(--color-yellow)] underline underline-offset-4">Sub-shift of “{shift.title}”</Link> · AI × {domain.name}</>}
        eyebrowColor="var(--color-yellow)"
        title={sub.title}
        sub={sub.context}
      />

      <StaleNotice show={stale} onRetry={retry} />

      <Column>
        <Modules modules={sub.modules} ctx={{ scope: 'sub_shift', domain, subs: [] }} />
      </Column>

      <SiblingNavigation
        {...subSiblings}
        label="Adjacent sub-shifts"
        hrefFor={(item) => `/map/${domain.slug}/${shift.slug}/${item.slug}`}
      />

      <div className="mt-[22px]"><ShiftFooter /></div>
    </article>
  )
}
