/** Director look filters + caption styles — applied as metadata for preview/export. */

export interface DirectorFilter {
  id: string
  label: string
  blurb: string
  css: string
}

export const DIRECTOR_FILTERS: DirectorFilter[] = [
  { id: 'none', label: 'None', blurb: 'No grade', css: 'none' },
  { id: 'warm', label: 'Warm', blurb: 'Sunset glow', css: 'sepia(0.25) saturate(1.15) brightness(1.05)' },
  { id: 'cool', label: 'Cool', blurb: 'Blue hour', css: 'saturate(0.9) hue-rotate(195deg) brightness(1.02)' },
  { id: 'noir', label: 'Noir', blurb: 'High contrast B&W', css: 'grayscale(1) contrast(1.35) brightness(0.95)' },
  { id: 'vivid', label: 'Vivid', blurb: 'Pop colours', css: 'saturate(1.45) contrast(1.1)' },
  { id: 'fade', label: 'Fade', blurb: 'Soft washed look', css: 'contrast(0.85) brightness(1.08) saturate(0.75)' },
  { id: 'dream', label: 'Dream', blurb: 'Soft glow', css: 'brightness(1.1) saturate(1.1) contrast(0.9)' },
  { id: 'vhs', label: 'VHS', blurb: 'Retro tape', css: 'contrast(1.2) saturate(1.3) hue-rotate(-8deg)' },
  { id: 'sepia', label: 'Sepia', blurb: 'Old photo', css: 'sepia(0.7) contrast(1.05)' },
  { id: 'neon', label: 'Neon', blurb: 'Night city punch', css: 'saturate(1.6) contrast(1.2) brightness(1.05)' },
]

export interface CaptionStyle {
  id: string
  label: string
  blurb: string
}

export const CAPTION_STYLES: CaptionStyle[] = [
  { id: 'bottom', label: 'Bottom centre', blurb: 'Classic subtitles' },
  { id: 'top', label: 'Top centre', blurb: 'Titles / lower-third flip' },
  { id: 'lower-third', label: 'Lower third', blurb: 'Name/place cards' },
  { id: 'center', label: 'Centre punch-in', blurb: 'Big title moment' },
  { id: 'free', label: 'Free position', blurb: 'Drag on the video' },
]

export interface TransitionPreset {
  id: string
  label: string
  blurb: string
}

export const TRANSITIONS: TransitionPreset[] = [
  { id: 'none', label: 'Hard cut', blurb: 'Instant change' },
  { id: 'fade', label: 'Fade', blurb: 'Fade through black' },
  { id: 'dissolve', label: 'Dissolve', blurb: 'Cross-dissolve' },
  { id: 'wipe', label: 'Wipe', blurb: 'Edge wipe' },
  { id: 'slide', label: 'Slide', blurb: 'Push slide' },
  { id: 'zoom', label: 'Zoom', blurb: 'Zoom through' },
  { id: 'flash', label: 'Flash', blurb: 'White flash cut' },
]

export function transitionPreviewCss(id: string | null | undefined, t = 0): string {
  // t = 0..1 how far through the transition preview
  const x = Math.max(0, Math.min(1, t))
  switch (id) {
    case 'fade':
      return `opacity ${0.35 + 0.65 * (1 - x)}`
    case 'dissolve':
      return `opacity ${1 - x * 0.55}`
    case 'wipe':
      return `clip-path inset(0 ${x * 100}% 0 0)`
    case 'slide':
      return `transform translateX(${(1 - x) * -18}%)`
    case 'zoom':
      return `transform scale(${1 + x * 0.12}); opacity ${1 - x * 0.35}`
    case 'flash':
      return `brightness(${1 + (x < 0.5 ? x * 4 : (1 - x) * 4)})`
    default:
      return ''
  }
}

export function filterCss(id: string | null | undefined, intensity = 1): string {
  const f = DIRECTOR_FILTERS.find((x) => x.id === id) || DIRECTOR_FILTERS[0]
  if (!f || f.id === 'none') return 'none'
  const t = Math.max(0, Math.min(1, intensity))
  if (t >= 0.99) return f.css
  // Blend toward identity by lowering opacity of effect via CSS — approximate with reduced strength
  return f.css.replace(/[\d.]+/g, (n) => {
    const v = Number(n)
    if (Number.isNaN(v) || v === 0) return n
    // For values around 1, lerp toward 1; for others scale toward 0/1 carefully
    if (v > 1) return String(1 + (v - 1) * t)
    if (v < 1) return String(1 - (1 - v) * t)
    return n
  })
}

export function formatTimecode(sec: number): string {
  const s = Math.max(0, sec)
  const m = Math.floor(s / 60)
  const r = s - m * 60
  return `${m}:${r.toFixed(1).padStart(4, '0')}`
}
