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
import { useResolved } from './useDomains'
import { ShiftFooter } from './chrome'
import { Modules } from './modules'
import { GradientHero, Eyebrow } from './sections'

/** Reading column: full-bleed on mobile, centred measure on desktop. */
const Column = ({ children }) => (
  <div className="mx-auto flex w-full flex-col gap-[30px] px-[22px] pt-[26px] lg:max-w-[860px] lg:gap-10 lg:pt-12">
    {children}
  </div>
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

const Loading = () => <div className="min-h-[60vh]" aria-busy="true" />

/* ── Domain sheet ────────────────────────────────────────────────────────── */

export function DomainSheet() {
  const { domainSlug } = useParams()
  const navigate = useNavigate()
  const { domain, loading } = useResolved({ domainSlug })

  if (loading && !domain) return <Loading />
  if (!domain) return <Missing what="domain" />

  return (
    <article className="a-expand min-h-dvh" style={{ backgroundImage: domain.grad }}>
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
        <div className="mx-auto w-full px-[22px] lg:max-w-[860px]">
          {domain.keyShifts.map((s, i) => (
            <Link
              key={s.id}
              to={`/map/${domain.slug}/${s.slug}`}
              className="a-rise flex gap-4 border-b py-[22px] transition-colors hover:bg-[var(--color-paper)]"
              style={{ borderColor: 'var(--color-hairline-soft)', animationDelay: `${(0.06 + i * 0.07).toFixed(2)}s` }}
            >
              <div className="pt-1 font-mono text-xs" style={{ color: 'var(--color-ink-faint)' }}>{s.num}</div>
              <div className="flex flex-1 flex-col gap-1.5">
                <div className="t-title text-[19px] leading-[1.2] lg:text-[22px]" style={{ color: 'var(--color-ink)' }}>{s.title}</div>
                <div className="text-[13.5px] leading-[1.5]" style={{ color: 'var(--color-ink-mid)' }}>{s.dek}</div>
                <div className="text-xs" style={{ color: 'var(--color-ink-dim)' }}>
                  Key shift{s.velocity ? ` · ${s.velocity}` : ''} · {s.read}
                </div>
              </div>
            </Link>
          ))}

          {/* The synthesis phase writes a few cross-cutting insights per domain
              every run. This is where they land. */}
          {domain.insights?.length > 0 && (
            <section className="flex flex-col gap-2.5 pt-10">
              <Eyebrow>What it adds up to</Eyebrow>
              <div className="grid gap-2.5 lg:grid-cols-2">
                {domain.insights.map((s) => (
                  <div key={s.id} className="card flex flex-col gap-2 p-4 lg:p-5">
                    <span className="t-display text-[15px] leading-[1.25] lg:text-[17px]" style={{ letterSpacing: '-0.01em' }}>{s.name}</span>
                    <span className="text-[13.5px] leading-[1.5] text-pretty" style={{ color: 'var(--color-ink-mid)' }}>{s.description}</span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      </div>

      <ShiftFooter />
    </article>
  )
}

/* ── Shift detail ────────────────────────────────────────────────────────── */

export function ShiftDetail() {
  const { domainSlug, ktSlug } = useParams()
  const navigate = useNavigate()
  const { domain, shift, loading } = useResolved({ domainSlug, ktSlug })

  if (loading && !shift) return <Loading />
  if (!domain || !shift) return <Missing what="shift" />

  return (
    <article className="a-expand min-h-dvh bg-white">
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
  const { domain, shift, sub, loading } = useResolved({ domainSlug, ktSlug, subSlug })

  // A sub-shift is a fresh reading context — always open at the top.
  useEffect(() => { window.scrollTo(0, 0) }, [subSlug])

  if (loading && !sub) return <Loading />
  if (!domain || !shift || !sub) return <Missing what="sub-shift" />

  return (
    <article className="a-expand min-h-dvh bg-white">
      <GradientHero
        grad="var(--grad-pink-hot)"
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
