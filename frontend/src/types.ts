export type Mode = 'film' | 'short' | 'music_video' | 'ad' | 'experiment'

export type TabId =
  | 'agent'
  | 'profiles'
  | 'shots'
  | 'storyboard'
  | 'characters'
  | 'sampling'
  | 'director'
  | 'settings'

export interface CharacterProfile {
  id: string
  name: string
  role: string
  look: string
  personality: string
  voice_notes: string
  reference_path?: string | null
  tags: string[]
}

export interface SceneProfile {
  id: string
  name: string
  location: string
  time_of_day: string
  mood: string
  visual_notes: string
  reference_path?: string | null
  tags: string[]
}

export interface Shot {
  id: string
  index: number
  title: string
  action: string
  dialogue: string
  camera: string
  duration_sec: number
  character_ids: string[]
  scene_id?: string | null
  prompt: string
  negative_prompt: string
  status: 'draft' | 'queued' | 'generating' | 'ready' | 'failed'
  pinned_take_id?: string | null
  storyboard_note: string
  director_notes: string
}

export interface Take {
  id: string
  shot_id: string
  label: string
  media_path?: string | null
  thumb_path?: string | null
  seed?: number | null
  score_note: string
  created_at: string
  is_placeholder: boolean
}

export interface TimelineClip {
  id: string
  shot_id: string
  take_id?: string | null
  start_sec: number
  end_sec?: number | null
  pinned: boolean
  order: number
}

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export interface Project {
  id: string
  title: string
  mode: Mode
  logline: string
  created_at: string
  updated_at: string
  characters: CharacterProfile[]
  scenes: SceneProfile[]
  shots: Shot[]
  takes: Take[]
  timeline: TimelineClip[]
  agent_messages: AgentMessage[]
  preset_id: string
  meta: Record<string, unknown>
}

export interface ProjectSummary {
  id: string
  title: string
  mode: Mode
  updated_at: string
  shot_count: number
  preset_id: string
}

export interface Settings {
  preset_id: string
  ollama_url: string
  ollama_model: string
  comfyui_url: string
  auto_save: boolean
  friendly_mode: boolean
}

export interface Health {
  ok: boolean
  ollama: boolean
  comfyui: boolean
  preset_id: string
  data_dir: string
}

export interface Preset {
  id: string
  label: string
  target_vram_gb: number
  notes?: string
}
