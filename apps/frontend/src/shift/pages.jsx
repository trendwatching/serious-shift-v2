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
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useDocumentMeta } from '../hooks/useDocumentMeta'
import { useResolved } from './useDomains'
import { ShiftFooter } from './chrome'
import { Modules } from './modules'
import { GradientHero, Eyebrow, Frame } from './sections'
import { quoteTitle } from './theme'

/** Frame plus the module rhythm — the body of a shift or sub-shift page.
 *
 * `Frame` is the wide track; each module is pulled back to `--measure` or left
 * at `--frame` by the wrapper in modules.jsx, so this file no longer decides
 * how wide anything is. */
const Column = ({ children }) => (
  <Frame className="flex flex-col gap-[var(--module-gap)] pt-[26px] md:pt-10 lg:pt-12">{children}</Frame>
)

function Missing({ what }) {
  return (
    <div className="grid min-h-[60vh] place-items-center px-6 text-center">
      <div className="flex flex-col items-center gap-4">
        <Eyebrow color="var(--color-ink-dim)">Not found</Eyebrow>
        <p className="t-display text-2xl">We couldn’t find that {what}.</p>
        <Link to="/" className="pill-yellow">Back to the domains</Link>
      </div>
    </div>
  )
}

/** The map document could not be loaded. Distinct from "not found": nothing is
 *  readable right now, and saying so is better than rendering stale prose. */
export function Unavailable({ error, onRetry }) {
  return (
    <div className="grid min-h-[60vh] place-items-center px-6 text-center">
      <div className="flex flex-col items-center gap-4">
        <Eyebrow color="var(--color-ink-dim)">Unavailable</Eyebrow>
        <p className="t-display text-2xl">This week’s map couldn’t be loaded.</p>
        <p className="max-w-[380px]" style={{ color: 'var(--color-ink-soft)' }}>
          {error?.status >= 500
            ? 'The map service is having trouble. Your last successful pages remain cached.'
            : 'Check your connection, then try again.'}
        </p>
        {onRetry && <button type="button" className="pill-yellow" onClick={onRetry}>Retry</button>}
      </div>
    </div>
  )
}

const Loading = () => <div className="min-h-[60vh]" aria-busy="true" />

/* ── Domain sheet ────────────────────────────────────────────────────────── */

export function DomainSheet() {
  const { domainSlug } = useParams()
  const navigate = useNavigate()
  const { domain, loading, unavailable, error, retry } = useResolved({ domainSlug })
  useDocumentMeta(domain?.name, domain?.blurb)

  if (loading && !domain) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain) return <Missing what="domain" />

  return (
    <article className="a-expand min-h-dvh" data-domain={domain.id} style={{ backgroundImage: domain.grad }}>
      <GradientHero
        grad={domain.grad}
        face="display"
        minHeight={0}
        onBack={() => navigate('/')}
        eyebrow={`${domain.num} · horizon ${domain.horizon}`}
        title={domain.name}
        blurb={domain.blurb}
      />

      <div
        className="mt-2 min-h-[520px] bg-white pb-[130px] pt-2"
        style={{ borderRadius: '28px 28px 0 0' }}
      >
        <Frame>
          {/* The shift list is read line by line, so it stays at the measure
              even though the frame around it is wider. */}
          <div className="w-prose">
            {domain.keyShifts.map((s, i) => (
              <Link
                key={s.id}
                to={`/map/${domain.slug}/${s.slug}`}
                className="a-rise flex gap-4 border-b py-[22px] transition-colors hover:bg-[var(--color-paper)]"
                style={{ borderColor: 'var(--color-hairline-soft)', animationDelay: `${(0.06 + i * 0.07).toFixed(2)}s` }}
              >
                <div className="pt-1 font-mono text-xs" style={{ color: 'var(--color-ink-faint)' }}>{s.num}</div>
                <div className="flex flex-1 flex-col gap-1.5">
                  <div className="t-title text-[19px] leading-[1.2] md:text-[21px] lg:text-[22px]" style={{ color: 'var(--color-ink)' }}>{quoteTitle(s.title)}</div>
                  <div className="t-body" style={{ color: 'var(--color-ink-mid)' }}>{s.dek}</div>
                  <div className="text-xs" style={{ color: 'var(--color-ink-dim)' }}>
                    Key shift{s.velocity ? ` · ${s.velocity}` : ''} · {s.read}
                  </div>
                </div>
              </Link>
            ))}
          </div>

          {/* The synthesis phase writes a few cross-cutting insights per domain
              every run. This is where they land — short cards, so they take the
              wide track and read as a grid rather than a stack. */}
          {domain.insights?.length > 0 && (
            <section className="w-wide flex flex-col gap-2.5 pt-10">
              <Eyebrow>What it adds up to</Eyebrow>
              <div className="grid gap-2.5 md:grid-cols-2 lg:gap-4 xl:grid-cols-3">
                {domain.insights.map((s) => (
                  <div key={s.id} className="card flex flex-col gap-2 p-4 lg:p-5">
                    <span className="t-display text-[15px] leading-[1.25] lg:text-[17px]" style={{ letterSpacing: '-0.01em' }}>{s.name}</span>
                    <span className="t-body text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{s.description}</span>
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
  const navigate = useNavigate()
  const { domain, shift, loading, unavailable, error, retry } = useResolved({ domainSlug, ktSlug })
  useDocumentMeta(shift?.title, shift?.dek)

  if (loading && !shift) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift) return <Missing what="shift" />

  return (
    <article className="a-expand min-h-dvh bg-white" data-domain={domain.id}>
      <GradientHero
        grad={domain.grad}
        stripes
        onBack={() => navigate(`/map/${domain.slug}`)}
        eyebrow={`${domain.name} · ${shift.kicker}`}
        title={shift.title}
      />

      <Column>
        <Modules
          modules={shift.modules}
          ctx={{
            scope: 'shift',
            domain,
            subs: shift.subshifts,
            onOpenSub: (b) => navigate(`/map/${domain.slug}/${shift.slug}/${b.slug}`),
            onNavigate: (r) => navigate(r.href),
          }}
        />
      </Column>

      <div className="mt-[22px]"><ShiftFooter /></div>
    </article>
  )
}

/* ── Sub-shift detail ────────────────────────────────────────────────────── */

export function SubShiftDetail() {
  const { domainSlug, ktSlug, subSlug } = useParams()
  const navigate = useNavigate()
  const { domain, shift, sub, loading, unavailable, error, retry } = useResolved({ domainSlug, ktSlug, subSlug })
  useDocumentMeta(sub?.title, sub?.dek)

  // A sub-shift is a fresh reading context — always open at the top.
  useEffect(() => { window.scrollTo(0, 0) }, [subSlug])

  if (loading && !sub) return <Loading />
  if (unavailable) return <Unavailable error={error} onRetry={retry} />
  if (!domain || !shift || !sub) return <Missing what="sub-shift" />

  return (
    <article className="a-expand min-h-dvh bg-white" data-domain={domain.id}>
      <GradientHero
        grad="var(--a-grad-hot)"
        minHeight={260}
        onBack={() => navigate(`/map/${domain.slug}/${shift.slug}`)}
        eyebrow={`Sub-shift ${sub.num}`}
        eyebrowColor="var(--color-yellow)"
        title={sub.title}
        sub={sub.context}
      />

      <Column>
        <Modules modules={sub.modules} ctx={{ scope: 'sub_shift', domain, subs: [] }} />
      </Column>

      <div className="mt-[22px]"><ShiftFooter /></div>
    </article>
  )
}
