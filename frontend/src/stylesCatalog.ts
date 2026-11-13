export interface VisualStyle {
  id: string
  label: string
  blurb: string
  prompt_suffix: string
}

export interface DurationPreset {
  id: string
  label: string
  seconds: number
  hint: string
}

export const VISUAL_STYLES: VisualStyle[] = [
  {
    id: 'cinematic',
    label: 'Cinematic',
    blurb: 'Film lighting, shallow depth, grounded realism.',
    prompt_suffix:
      'cinematic lighting, anamorphic feel, film grain, naturalistic color, shallow depth of field',
  },
  {
    id: 'animation',
    label: 'Animation',
    blurb: 'Stylized 3D / CG animated look.',
    prompt_suffix: 'stylized 3D animation, smooth shading, expressive motion, animated feature look',
  },
  {
    id: 'clay',
    label: 'Clay / stop-motion',
    blurb: 'Claymation / plasticine physical models.',
    prompt_suffix:
      'claymation stop-motion, plasticine textures, handmade miniature set, tactile fingerprints in clay',
  },
  {
    id: 'cartoon',
    label: 'Cartoon',
    blurb: '2D cartoon / comic energy.',
    prompt_suffix: '2D cartoon style, bold outlines, flat vibrant colors, expressive cartoon motion',
  },
  {
    id: 'anime',
    label: 'Anime',
    blurb: 'Japanese animation aesthetic.',
    prompt_suffix: 'anime style, cel shading, dramatic eyes, dynamic camera, anime film framing',
  },
  {
    id: 'pixel',
    label: 'Pixel / retro',
    blurb: 'Retro game / pixel art vibe.',
    prompt_suffix: 'pixel art style, retro game aesthetic, limited palette, crisp pixels',
  },
  {
    id: 'documentary',
    label: 'Documentary',
    blurb: 'Handheld, observational realism.',
    prompt_suffix: 'documentary style, natural light, handheld camera feel, observational realism',
  },
  {
    id: 'noir',
    label: 'Noir',
    blurb: 'High contrast shadows and mystery.',
    prompt_suffix: 'film noir, high contrast shadows, moody black and cyan tones, mysterious atmosphere',
  },
]

export const DURATION_PRESETS: DurationPreset[] = [
  { id: 'clip', label: 'Clip', seconds: 15, hint: 'Quick test / social clip' },
  { id: 'short', label: 'Short', seconds: 60, hint: '1 minute short' },
  { id: 'sketch', label: 'Sketch', seconds: 180, hint: '3 minute sketch' },
  { id: 'shortfilm', label: 'Short film', seconds: 600, hint: '~10 minutes' },
  { id: 'mid', label: 'Mid-length', seconds: 1200, hint: '~20 minutes' },
  { id: 'featurette', label: 'Featurette', seconds: 2700, hint: '~45 minutes' },
  { id: 'feature', label: 'Feature', seconds: 5400, hint: '~90 minutes' },
  { id: 'custom', label: 'Custom', seconds: 0, hint: 'Type your own length' },
]

export function formatDuration(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m ${sec}s`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
}
