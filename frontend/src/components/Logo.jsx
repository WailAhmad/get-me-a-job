/**
 * Logo — single source of truth for the JobsLand brand mark.
 *
 * Props
 *   variant   "light" (default) | "dark"   – kept for compatibility
 *   height    number (px)  – rendered height  (default 36)
 *   width     number|null  – explicit width; null = let aspect-ratio rule
 *   glow      bool         – adds the teal/blue drop-shadow glow (default false)
 *   style     object       – extra inline styles forwarded to <img>
 */
export default function Logo({
  variant = 'light',
  height  = 36,
  width   = null,
  glow    = false,
  style   = {},
}) {
  const src = '/jobsland_logo.jpeg'

  const glowFilter = glow
    ? 'drop-shadow(0 0 28px rgba(20,184,166,0.35)) drop-shadow(0 0 56px rgba(14,165,233,0.18))'
    : undefined

  return (
    <img
      src={src}
      alt="JobsLand"
      style={{
        height,
        width: width || Math.round(height * 0.94),
        objectFit: 'contain',
        objectPosition: 'center',
        flexShrink: 0,
        filter: glowFilter,
        background: '#02040a',
        boxShadow: glow
          ? '0 24px 86px rgba(20,184,166,0.16), 0 0 0 1px rgba(125,211,252,0.08)'
          : '0 12px 34px rgba(0,0,0,0.28)',
        ...style,
      }}
    />
  )
}
