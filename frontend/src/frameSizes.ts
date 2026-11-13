export type FrameOrientation = 'landscape' | 'portrait' | 'square'

export interface FrameSize {
  id: string
  label: string
  orientation: FrameOrientation
  ratio: string
  width: number
  height: number
  blurb: string
}

/** Mirrors backend frame_sizes — landscape, portrait, 1:1, and friends. */
export const FRAME_SIZES: FrameSize[] = [
  {
    id: '16:9-hd',
    label: '16:9 Landscape HD',
    orientation: 'landscape',
    ratio: '16:9',
    width: 1280,
    height: 720,
    blurb: 'YouTube / film default',
  },
  {
    id: '16:9-draft',
    label: '16:9 Landscape draft',
    orientation: 'landscape',
    ratio: '16:9',
    width: 768,
    height: 432,
    blurb: 'Low VRAM friendly',
  },
  {
    id: '16:9-1080',
    label: '16:9 Full HD',
    orientation: 'landscape',
    ratio: '16:9',
    width: 1920,
    height: 1080,
    blurb: '1080p — needs more VRAM',
  },
  {
    id: '21:9',
    label: '21:9 Ultrawide',
    orientation: 'landscape',
    ratio: '21:9',
    width: 1280,
    height: 548,
    blurb: 'Cinematic letterbox feel',
  },
  {
    id: '4:3',
    label: '4:3 Classic',
    orientation: 'landscape',
    ratio: '4:3',
    width: 1024,
    height: 768,
    blurb: 'TV / retro frame',
  },
  {
    id: '3:2',
    label: '3:2 Photo',
    orientation: 'landscape',
    ratio: '3:2',
    width: 1152,
    height: 768,
    blurb: 'Still-camera landscape',
  },
  {
    id: '1:1',
    label: '1:1 Square',
    orientation: 'square',
    ratio: '1:1',
    width: 1024,
    height: 1024,
    blurb: 'Instagram feed / equal crop',
  },
  {
    id: '1:1-draft',
    label: '1:1 Square draft',
    orientation: 'square',
    ratio: '1:1',
    width: 512,
    height: 512,
    blurb: 'Fast square for low VRAM',
  },
  {
    id: '9:16',
    label: '9:16 Portrait',
    orientation: 'portrait',
    ratio: '9:16',
    width: 720,
    height: 1280,
    blurb: 'TikTok / Reels / Shorts',
  },
  {
    id: '9:16-draft',
    label: '9:16 Portrait draft',
    orientation: 'portrait',
    ratio: '9:16',
    width: 432,
    height: 768,
    blurb: 'Vertical, gentler on VRAM',
  },
  {
    id: '4:5',
    label: '4:5 Portrait',
    orientation: 'portrait',
    ratio: '4:5',
    width: 864,
    height: 1080,
    blurb: 'Instagram portrait post',
  },
  {
    id: '3:4',
    label: '3:4 Portrait',
    orientation: 'portrait',
    ratio: '3:4',
    width: 768,
    height: 1024,
    blurb: 'Tall still / soft vertical',
  },
  {
    id: '2:3',
    label: '2:3 Portrait photo',
    orientation: 'portrait',
    ratio: '2:3',
    width: 768,
    height: 1152,
    blurb: 'Still-camera portrait',
  },
]

export function frameById(id?: string | null): FrameSize {
  return FRAME_SIZES.find((f) => f.id === id) || FRAME_SIZES.find((f) => f.id === '16:9-draft')!
}

export function framesByOrientation(orientation: FrameOrientation): FrameSize[] {
  return FRAME_SIZES.filter((f) => f.orientation === orientation)
}
