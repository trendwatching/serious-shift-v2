/** The hero statistic band. */
export function StatBand({ stat, size = 58 }) {
  if (!stat?.value) return null

  // The design's numeral is drawn for a five-character figure ("18-34"). Real
  // values are longer more often than not — over half run past six characters
  // and some are phrases ("no countervailing institutions"). At the design's
  // 99px, "24 months" measured 478px of a 660px row and left the explanatory
  // text in a 142px column, 306px tall. So the ceiling scales down with length,
  // and the row wraps: once the numeral is too wide to leave the text a usable
  // column, the text drops beneath it instead of being crushed beside it.
  const chars = [...String(stat.value)].length
  const max = Math.max(28, Math.round(size * 1.7 * Math.min(1, 6 / Math.max(chars, 6))))

  return (
    <div
      className="bleed box-border flex flex-wrap items-center gap-[18px] py-[34px] text-white md:gap-8 md:py-11 lg:gap-10 lg:py-14"
      role="region"
      aria-label="Key statistic"
      // The design shipped this band as a pink PNG, which only ever suited
      // Society — and cost 256 KB. A gradient built from the accent gives every
      // domain its own band and removes the request entirely.
      style={{
        backgroundImage:
          'linear-gradient(rgba(13,11,16,0.38), rgba(13,11,16,0.38)), ' +
          'radial-gradient(120% 140% at 12% 15%, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0) 55%), ' +
          'linear-gradient(115deg, var(--a-hot) 0%, var(--a) 46%, var(--a-abyss) 100%)',
      }}
    >
      <h2 className="sr-only">Key statistic</h2>
      <span
        className="shrink-0 leading-[0.9]"
        style={{
          fontFamily: 'var(--font-title)',
          // The numeral is the anchor of the band; give it real scale once
          // there's room, but keep the mobile size exactly as designed.
          fontSize: `clamp(${Math.min(size, max)}px, ${size / 3.9}vw, ${max}px)`,
          letterSpacing: '-0.015em',
        }}
      >
        {stat.value}
      </span>
      {/* basis is what decides the wrap: below ~260px the text is not worth
          setting beside the numeral, so the row breaks instead. */}
      <span className="flex flex-1 basis-[260px] flex-col gap-2">
        <span className="text-[13.5px] leading-[1.45] text-pretty md:text-[15.5px] md:leading-[1.5] lg:text-[17px]">{stat.text}</span>
        {stat.source && (stat.url ? (
          <a href={stat.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center self-start text-[11px] leading-[1.4] underline underline-offset-4 md:text-[12px] lg:text-[12.5px]" aria-label={`Read source: ${stat.source}`}>{stat.source}</a>
        ) : <span className="text-[11px] leading-[1.4] opacity-85 md:text-[12px] lg:text-[12.5px]">{stat.source}</span>)}
      </span>
    </div>
  )
}
