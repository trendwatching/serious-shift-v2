/** The hero statistic band. */
export function StatBand({ stat, size = 58 }) {
  if (!stat?.value) return null
  return (
    <div
      className="bleed box-border flex items-center gap-[18px] py-[34px] text-white lg:gap-10 lg:py-14"
      // The design shipped this band as a pink PNG, which only ever suited
      // Society — and cost 256 KB. A gradient built from the accent gives every
      // domain its own band and removes the request entirely.
      style={{
        backgroundImage:
          'radial-gradient(120% 140% at 12% 15%, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0) 55%), ' +
          'linear-gradient(115deg, var(--a-hot) 0%, var(--a) 46%, var(--a-abyss) 100%)',
      }}
    >
      <span
        className="shrink-0 leading-[0.9]"
        style={{
          fontFamily: 'var(--font-title)',
          // The numeral is the anchor of the band; give it real scale once
          // there's room, but keep the mobile size exactly as designed.
          fontSize: `clamp(${size}px, ${size / 3.9}vw, ${Math.round(size * 1.7)}px)`,
          letterSpacing: '-0.015em',
        }}
      >
        {stat.value}
      </span>
      <span className="flex flex-1 flex-col gap-2">
        <span className="text-[13.5px] leading-[1.45] text-pretty lg:text-[17px] lg:leading-[1.5]">{stat.text}</span>
        {stat.source && <span className="text-[11px] leading-[1.4] opacity-75 lg:text-[12.5px]">{stat.source}</span>}
      </span>
    </div>
  )
}
