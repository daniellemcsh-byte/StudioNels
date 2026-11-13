import type { GenMode } from './types'

export interface InspirationClip {
  id: string
  title: string
  mode: GenMode
  prompt: string
  blurb: string
  vibe: string
  durationHint: string
  accent: string
}

export const INSPIRATION_CLIPS: InspirationClip[] = [
  {
    id: 'neon-courier',
    title: 'Neon memory courier',
    mode: 't2v',
    prompt:
      'Cinematic night alley, courier in a silver jacket carrying glowing glass jars of memories, wet asphalt reflections, cyan and magenta neon, slow tracking shot',
    blurb: 'Text → video mood piece for sci‑fi shorts.',
    vibe: 'Cyber · rain · story',
    durationHint: '~3s draft',
    accent: '#39ffc7',
  },
  {
    id: 'portrait-still',
    title: 'Hero portrait still',
    mode: 't2i',
    prompt:
      'Character portrait of a quiet courier, silver jacket, soft rim light, film still, coherent face, shallow depth of field',
    blurb: 'Text → image for character refs.',
    vibe: 'Cast · lookbook',
    durationHint: 'still',
    accent: '#ff3dce',
  },
  {
    id: 'animate-ref',
    title: 'Animate a still',
    mode: 'i2v',
    prompt: 'Gentle camera push-in, subtle hair movement, cinematic breathing life',
    blurb: 'Image → video — bring a ref to life.',
    vibe: 'Motion · continuity',
    durationHint: '~2–4s',
    accent: '#b8ff3d',
  },
  {
    id: 'same-face',
    title: 'Keep the same face',
    mode: 'ref2i',
    prompt: 'Same person in a rainy train station, neon signage, matching wardrobe and face',
    blurb: 'Reference → image for consistent characters.',
    vibe: 'Identity · series',
    durationHint: 'still',
    accent: '#7ed0ff',
  },
  {
    id: 'ref-walk',
    title: 'Reference walk cycle',
    mode: 'ref2v',
    prompt: 'Same character walking through foggy docks at dawn, medium tracking shot, coherent face',
    blurb: 'Reference → video for scene continuity.',
    vibe: 'Character lock',
    durationHint: '~3s',
    accent: '#ff9d4a',
  },
  {
    id: 'audio-bed',
    title: 'Night ambience bed',
    mode: 't2a',
    prompt: 'Soft rainy city ambience with distant neon buzz and sparse synth pulses, cinematic underscore',
    blurb: 'Text → audio for director beds.',
    vibe: 'Sound · mood',
    durationHint: '6–10s',
    accent: '#c08cff',
  },
  {
    id: 'music-chorus',
    title: 'Music video chorus lift',
    mode: 't2v',
    prompt:
      'Music video chorus: dancer under strobing stage lights, smoke, wide to close punch-ins, high energy, saturated color',
    blurb: 'Fast visual ideas for MV beats.',
    vibe: 'Rhythm · lights',
    durationHint: '~4s',
    accent: '#39ffc7',
  },
  {
    id: 'ad-hook',
    title: 'Ad hook close-up',
    mode: 't2v',
    prompt:
      'Bold product hook: macro close-up of a glass jar glowing on wet stone, rack focus, premium commercial lighting',
    blurb: 'Short promo / ad cold opens.',
    vibe: 'Commercial',
    durationHint: '~2s',
    accent: '#ff3dce',
  },
  {
    id: 'upsample-polish',
    title: 'Polish a draft',
    mode: 'upsample_image',
    prompt: 'Upscale and sharpen a draft still for storyboard print',
    blurb: 'Upsample image after a quick draft.',
    vibe: 'Finish · clarity',
    durationHint: '2× / 4×',
    accent: '#b8ff3d',
  },
]
