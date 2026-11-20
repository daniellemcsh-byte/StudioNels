export type AudioKind = 'music' | 'song' | 'sfx' | 'ambience' | 'score' | 'voice'

export interface VoiceAccent {
  id: string
  label: string
  region: string
  prompt_hint: string
}

export interface AudioKindOption {
  id: AudioKind
  label: string
  blurb: string
  prompt_prefix: string
}

export const VOICE_ACCENTS: VoiceAccent[] = [
  {
    id: 'neutral',
    label: 'Neutral',
    region: 'General',
    prompt_hint: 'clear neutral singing voice',
  },
  {
    id: 'british-rp',
    label: 'British (RP)',
    region: 'UK',
    prompt_hint: 'British Received Pronunciation singing accent',
  },
  {
    id: 'british-north',
    label: 'British Northern',
    region: 'UK',
    prompt_hint: 'Northern English singing accent',
  },
  {
    id: 'irish',
    label: 'Irish',
    region: 'Ireland',
    prompt_hint: 'Irish singing accent',
  },
  {
    id: 'scottish',
    label: 'Scottish',
    region: 'Scotland',
    prompt_hint: 'Scottish singing accent',
  },
  {
    id: 'american-general',
    label: 'American',
    region: 'US',
    prompt_hint: 'General American singing accent',
  },
  {
    id: 'american-southern',
    label: 'American Southern',
    region: 'US',
    prompt_hint: 'Southern US singing accent',
  },
  {
    id: 'australian',
    label: 'Australian',
    region: 'AU',
    prompt_hint: 'Australian singing accent',
  },
  {
    id: 'french',
    label: 'French-English',
    region: 'FR',
    prompt_hint: 'light French-accented English vocals',
  },
  {
    id: 'spanish',
    label: 'Spanish-English',
    region: 'ES',
    prompt_hint: 'light Spanish-accented English vocals',
  },
  {
    id: 'nigerian',
    label: 'Nigerian English',
    region: 'NG',
    prompt_hint: 'Nigerian English singing accent',
  },
  {
    id: 'indian',
    label: 'Indian English',
    region: 'IN',
    prompt_hint: 'Indian English singing accent',
  },
]

export const AUDIO_KINDS: AudioKindOption[] = [
  {
    id: 'music',
    label: 'Music (instrumental)',
    blurb: 'Beds, loops, underscoring — no vocals.',
    prompt_prefix: 'Instrumental music track',
  },
  {
    id: 'song',
    label: 'Song (with vocals)',
    blurb: 'Full song idea with a singing voice.',
    prompt_prefix: 'Complete song with lead vocals and lyrics feel',
  },
  {
    id: 'score',
    label: 'Film score',
    blurb: 'Cinematic underscore for your shots.',
    prompt_prefix: 'Cinematic film score cue',
  },
  {
    id: 'voice',
    label: 'Dialogue (voice)',
    blurb: 'A character speaks a line — voice designed from a description.',
    prompt_prefix: '',
  },
  {
    id: 'ambience',
    label: 'Ambience',
    blurb: 'Places and atmospheres.',
    prompt_prefix: 'Atmospheric ambient soundscape',
  },
  {
    id: 'sfx',
    label: 'Sound effects',
    blurb: 'Hits, whooshes, foley-style moments.',
    prompt_prefix: 'Sound effect',
  },
]

export const MUSIC_MOODS = [
  'dreamy',
  'dark',
  'uplifting',
  'tense',
  'romantic',
  'epic',
  'minimal',
  'groovy',
  'melancholy',
  'playful',
]
