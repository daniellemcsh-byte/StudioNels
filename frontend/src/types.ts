export type Mode = 'film' | 'short' | 'music_video' | 'ad' | 'experiment'

export type TabId =
  | 'inspiration'
  | 'agent'
  | 'profiles'
  | 'time'
  | 'shots'
  | 'storyboard'
  | 'characters'
  | 'creator'
  | 'generate'
  | 'audio'
  | 'upsample'
  | 'models'
  | 'addons'
  | 'continuity'
  | 'rehearsal'
  | 'sampling'
  | 'director'
  | 'learning'
  | 'sources'
  | 'info'
  | 'settings'

export type GenMode =
  | 't2i'
  | 't2v'
  | 'i2v'
  | 'ref2i'
  | 'ref2v'
  | 't2a'
  | 'upsample_image'
  | 'upsample_video'

export interface EngineMode {
  id: GenMode
  label: string
  needs_image: boolean
  needs_reference: boolean
  output: string
  blurb: string
}

export interface EngineModel {
  id: string
  label: string
  modes: GenMode[]
  hf_id: string
  min_vram_gb: number
  kind: string
  notes?: string
}

export interface EngineJob {
  id: string
  status: string
  progress: number
  message: string
  mode: GenMode
  model_id: string
  model_label: string
  prompt: string
  media_path?: string | null
  thumb_path?: string | null
  preview?: boolean
  error?: string | null
  created_at: string
}

export interface LoraFile {
  id: string
  name: string
  path: string
  size_mb: number
}

export interface EngineStatus {
  backend: string
  device: {
    torch_available: boolean
    ready_for_inference: boolean
    device_name: string
    vram_gb: number | null
    rocm: boolean
    backend: string
    notes: string[]
  }
  modes: EngineMode[]
  models: EngineModel[]
  queue_length: number
  preset_id: string
  models_path: string
  loras_path?: string
  loras?: LoraFile[]
  lora_count?: number
}

export interface CharacterProfile {
  id: string
  name: string
  role: string
  look: string
  personality: string
  voice_notes: string
  character_lock?: string
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
  continuity_score?: number | null
  continuity_flags?: string[]
  prompt_used?: string
  is_rehearsal?: boolean
  rejected?: boolean
}

export interface TimelineClip {
  id: string
  shot_id: string
  take_id?: string | null
  start_sec: number
  end_sec?: number | null
  trim_in?: number
  trim_out?: number | null
  speed?: number
  pinned: boolean
  order: number
  caption?: string
  caption_style?: string
  filter_id?: string
  filter_intensity?: number
  director_note?: string
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
  target_duration_sec: number
  visual_style: string
  image_format: 'png' | 'jpg' | 'webp'
  video_format: 'mp4' | 'webm' | 'gif'
  audio_format: 'wav' | 'mp3'
  world_bible?: string
  continuity_rules?: string[]
  auto_reject_below?: number
  continue_from_previous?: boolean
  default_filter_id?: string
  captions_enabled?: boolean
  meta: Record<string, unknown>
}

export interface GpuEstimate {
  ok: boolean
  fit: 'comfortable' | 'tight' | 'wont_fit' | 'cpu_slow' | 'preview_only' | 'unknown'
  mode: string
  model_id?: string
  model_label?: string
  device_name: string
  vram_available_gb: number | null
  vram_estimate_gb: number
  eta_sec: number
  eta_label: string
  steps: number
  width: number
  height: number
  frames: number
  quality: string
  cpu_offload: boolean
  suggested_preset: string
  warnings: string[]
  advice: string[]
  can_queue: boolean
  will_preview: boolean
}

export interface ContinuityData {
  bible: {
    title: string
    style: string
    logline: string
    cast: Array<{ id: string; name: string; look: string; lock: string; must_keep: string[] }>
    world: Array<{ id: string; name: string; location: string; must_keep: string[] }>
    rules: string[]
    text: string
    auto_reject_below: number
  }
  world_bible: string
  rules: string[]
  auto_reject_below: number
  takes: Array<{
    id: string
    shot_id: string
    label: string
    continuity_score: number | null
    continuity_flags: string[]
    rejected: boolean
    is_rehearsal: boolean
  }>
}

export interface ProjectSummary {
  id: string
  title: string
  mode: Mode
  updated_at: string
  shot_count: number
  preset_id: string
}

export type AgentProvider =
  | 'builtin'
  | 'ollama'
  | 'openai'
  | 'anthropic'
  | 'openrouter'
  | 'custom'

export interface Settings {
  preset_id: string
  ollama_url: string
  ollama_model: string
  agent_provider: AgentProvider
  agent_model: string
  agent_api_base: string
  agent_api_key: string
  agent_api_key_set?: boolean
  github_url: string
  huggingface_url: string
  huggingface_token: string
  huggingface_token_set?: boolean
  creator_display_name: string
  auto_save: boolean
  friendly_mode: boolean
  default_gen_mode: string
  cpu_offload: boolean
}

export interface PersonalProfile {
  github_url: string
  huggingface_url: string
  huggingface_token_set: boolean
  display_name: string
  imports: PersonalImportJob[]
  hints: Record<string, string>
}

export interface PersonalImportJob {
  id: string
  kind: 'model' | 'lora' | 'addon'
  source: string
  name: string
  status: string
  progress: number
  message: string
  local_path?: string | null
  error?: string | null
  created_at: string
  updated_at: string
}

export interface AgentProviderInfo {
  id: AgentProvider
  label: string
  blurb: string
  needs_key: boolean
  default_model: string
  default_base: string
}

export interface Health {
  ok: boolean
  ollama: boolean
  engine: string
  torch: boolean
  gpu: boolean
  device_name: string
  preset_id: string
  data_dir: string
  agent_provider?: string
  agent_label?: string
  agent_reachable?: boolean
  agent_detail?: string
}

export interface Preset {
  id: string
  label: string
  target_vram_gb: number
  notes?: string
}
