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
  | 'templates'
  | 'addons'
  | 'continuity'
  | 'rehearsal'
  | 'sampling'
  | 'filmnight'
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
  needs_video?: boolean
  accepts_ref_video?: boolean
  accepts_start_image?: boolean
  output: string
  blurb: string
}

export interface EngineModel {
  id: string
  label: string
  modes: GenMode[]
  hf_id: string | null
  min_vram_gb: number
  kind: string
  notes?: string
  installed?: boolean
  active?: boolean
  download_status?: string
  download_progress?: number
  download_error?: string | null
  download_message?: string | null
  local_path?: string | null
  tier?: string
  custom?: boolean
  discovered?: boolean
  distilled?: boolean
  wan2gp?: boolean
  format?: string
  component_files?: Record<string, string>
}

export interface EngineModelsPack {
  models: EngineModel[]
  active_model_id?: string | null
  count: number
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
  started_at?: string | null
  updated_at?: string
  elapsed_sec?: number
  eta_sec?: number
  step?: number
  steps_total?: number
  workflow?: Record<string, unknown>
  cancel_requested?: boolean
  text_encoder?: string
  audio_path?: string | null
}

export interface TextEncoderPreset {
  id: string
  label: string
  hf_id?: string | null
  local_path?: string | null
  slot?: string
  notes?: string
  source?: string
  kind?: string
}

export interface LoraFile {
  id: string
  name: string
  path: string
  size_mb: number
  family?: string
  source?: string
  root?: string
}

export interface Wan2gpComponent {
  id: string
  name: string
  path: string
  kind: string
  label: string
  size_mb: number
  source?: string
  root?: string
}

export interface ModelTemplateComponent {
  id: string
  role: string
  label: string
  hf_id: string
  dest?: string
  required?: boolean
  notes?: string
  download_status?: string
  download_progress?: number
  download_message?: string
  installed?: boolean
  local_path?: string | null
}

export interface ModelTemplate {
  id: string
  label: string
  kind: string
  modes: GenMode[]
  min_vram_gb: number
  tier?: string
  blurb: string
  primary_model_id?: string
  primary_label?: string
  primary_hf_id?: string | null
  components: ModelTemplateComponent[]
  ready?: boolean
  progress?: number
  download_status?: string
}

export interface Wan2gpInventory {
  ckpts_dir: string
  roots: { ckpts: string[]; loras: string[] }
  modes?: string[]
  by_mode?: Record<string, number>
  video_packs: EngineModel[]
  image_models: EngineModel[]
  audio_models: EngineModel[]
  upsample_models: EngineModel[]
  loras: LoraFile[]
  text_encoders: TextEncoderPreset[]
  local_text_encoders: TextEncoderPreset[]
  components: Wan2gpComponent[]
  counts: Record<string, number>
  settings?: {
    wan2gp_ckpts_path?: string
    wan2gp_loras_path?: string
    wan2gp_text_encoders_path?: string
    wan2gp_assets_path?: string
  }
}

export interface EngineStatus {
  backend: string
  mmgp?: {
    available?: boolean
    package?: string
    blurb?: string
  }
  wan2gp?: {
    available?: boolean
    root?: string
    python?: string
    reason?: string
    model_count?: number
  }
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
  active_model_id?: string | null
  queue_length: number
  preset_id: string
  models_path: string
  loras_path?: string
  loras?: LoraFile[]
  lora_count?: number
  text_encoders?: TextEncoderPreset[]
  memory_profiles?: unknown[]
  current_job_id?: string | null
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
  identity_fingerprint?: number[] | null
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
  vision_score?: number | null
  identity_score?: number | null
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
  caption_x?: number
  caption_y?: number
  caption_start?: number
  caption_end?: number | null
  filter_id?: string
  filter_intensity?: number
  director_note?: string
  scale?: number
  pan_x?: number
  pan_y?: number
  volume?: number
  fade_in?: number
  fade_out?: number
  transition?: string
  transition_dur?: number
}

export interface AudioClip {
  id: string
  label: string
  kind: 'music' | 'song' | 'score' | 'ambience' | 'sfx' | 'vo' | 'other'
  media_path?: string | null
  timeline_start: number
  duration_sec: number
  trim_in?: number
  trim_out?: number | null
  volume: number
  fade_in?: number
  fade_out?: number
  muted?: boolean
  track: number
  order: number
}

export interface AgentAttachment {
  id?: string
  kind: 'image' | 'file' | 'character' | 'scene'
  path?: string | null
  name?: string
  character_id?: string | null
  scene_id?: string | null
  mime?: string
}

export interface AgentMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  attachments?: AgentAttachment[]
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
  audio_timeline?: AudioClip[]
  agent_messages: AgentMessage[]
  preset_id: string
  target_duration_sec: number
  visual_style: string
  image_format: 'png' | 'jpg' | 'webp'
  video_format: 'mp4' | 'webm' | 'gif'
  audio_format: 'wav' | 'mp3'
  frame_size_id?: string
  aspect_ratio?: string
  width?: number
  height?: number
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
  coach_headline?: string
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
  keep_model_loaded?: boolean
  wan2gp_ckpts_path?: string
  wan2gp_loras_path?: string
  wan2gp_text_encoders_path?: string
  wan2gp_assets_path?: string
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
  rocm?: boolean
  vram_gb?: number | null
  backend?: string
  ready_for_inference?: boolean
  will_preview?: boolean
  suggested_preset?: string
  first_run_headline?: string
  first_run_detail?: string
  notes?: string[]
}

export interface AgentStatus {
  provider: string
  label: string
  model: string
  needs_key: boolean
  key_set: boolean
  reachable: boolean
  detail: string
  models?: string[]
  model_ready?: boolean
  ok?: boolean
  ping_ok?: boolean
  ping_detail?: string
}

export interface RecipeInfo {
  id: string
  title: string
  blurb: string
  tags: string[]
}

export interface MemoryProfile {
  id: string
  label: string
  target_vram_gb: number
  notes?: string
  memory: {
    placement: string
    placement_label: string
    dtype: string
    attention_slicing: boolean
    vae_slicing: boolean
    vae_tiling: boolean
    text_encoder_on_cpu: boolean
    cpu_offload: boolean
    blurb: string
  }
  generation?: {
    default_width?: number
    default_height?: number
    default_frames?: number
    fps?: number
    cpu_offload?: boolean
  }
}

export interface Preset {
  id: string
  label: string
  target_vram_gb: number
  notes?: string
  memory?: MemoryProfile['memory']
}
