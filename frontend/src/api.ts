import type {
  AgentProviderInfo,
  AgentStatus,
  AudioClip,
  CharacterProfile,
  ContinuityData,
  EngineJob,
  EngineModel,
  EngineStatus,
  GpuEstimate,
  Health,
  PersonalImportJob,
  PersonalProfile,
  Preset,
  Project,
  ProjectSummary,
  SceneProfile,
  Settings,
  TimelineClip,
  ModelTemplate,
  Wan2gpInventory,
} from './types'

function errorMessageFromBody(text: string, status: number): string {
  const raw = (text || '').trim()
  if (!raw) return status === 404 ? 'Not found' : `Request failed (${status})`
  try {
    const j = JSON.parse(raw) as { detail?: unknown }
    if (typeof j.detail === 'string' && j.detail.trim()) return j.detail
    if (Array.isArray(j.detail)) {
      const parts = j.detail
        .map((d) =>
          typeof d === 'string'
            ? d
            : d && typeof d === 'object' && 'msg' in d
              ? String((d as { msg: unknown }).msg)
              : '',
        )
        .filter(Boolean)
      if (parts.length) return parts.join('; ')
    }
  } catch {
    /* plain text */
  }
  if (raw === '{"detail":"Not Found"}' || /"detail"\s*:\s*"Not Found"/i.test(raw)) {
    return 'Not found — click Update in Pinokio, then Stop and Start again.'
  }
  return raw.length > 280 ? raw.slice(0, 280) + '…' : raw
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
      ...init,
    })
  } catch {
    throw new Error(
      'API not running (port 8787). In Pinokio: Stop StudioNels → Update → Start, then retry.',
    )
  }
  if (!res.ok) {
    const text = await res.text()
    throw new Error(errorMessageFromBody(text, res.status))
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<Health>('/api/health'),
  presets: () => req<Preset[]>('/api/presets'),
  getSettings: () => req<Settings>('/api/settings'),
  putSettings: (body: Settings) =>
    req<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(body) }),
  agentProviders: () =>
    req<{
      providers: AgentProviderInfo[]
      status: AgentStatus
    }>('/api/agent/providers'),
  agentTest: async () => {
    try {
      return await req<AgentStatus>('/api/agent/test', { method: 'POST', body: '{}' })
    } catch (err) {
      // Older Pinokio installs may not have /api/agent/test yet — fall back to probe.
      const msg = err instanceof Error ? err.message : String(err)
      if (!/not found/i.test(msg)) throw err
      try {
        const r = await req<{
          providers: AgentProviderInfo[]
          status: AgentStatus
        }>('/api/agent/providers')
        return {
          ...r.status,
          ping_detail:
            r.status.detail ||
            'Status from providers probe — Update StudioNels in Pinokio for full chat test.',
        }
      } catch {
        const h = await req<Health>('/api/health')
        return {
          provider: h.agent_provider || 'ollama',
          label: h.agent_label || 'Ollama',
          model: '',
          needs_key: false,
          key_set: false,
          reachable: Boolean(h.agent_reachable || h.ollama),
          detail:
            h.agent_detail ||
            (h.ollama
              ? 'Ollama reachable via health check'
              : 'Ollama offline — start the Ollama app, then try again'),
          ok: Boolean(h.agent_reachable || h.ollama),
          ping_ok: Boolean(h.agent_reachable || h.ollama),
        }
      }
    }
  },
  getPersonal: () => req<PersonalProfile>('/api/personal'),
  putPersonal: (body: {
    github_url?: string
    huggingface_url?: string
    huggingface_token?: string
    creator_display_name?: string
  }) => req<PersonalProfile>('/api/personal', { method: 'PUT', body: JSON.stringify(body) }),
  importPersonal: (body: { kind: 'model' | 'lora' | 'addon'; source: string; name?: string }) =>
    req<PersonalImportJob>('/api/personal/import', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  personalImports: () => req<PersonalImportJob[]>('/api/personal/imports'),
  personalImportJob: (id: string) => req<PersonalImportJob>(`/api/personal/imports/${id}`),
  listProjects: () => req<ProjectSummary[]>('/api/projects'),
  createProject: (body: {
    title: string
    mode: string
    logline?: string
    preset_id?: string
    frame_size_id?: string
  }) => req<Project>('/api/projects', { method: 'POST', body: JSON.stringify(body) }),
  getProject: (id: string) => req<Project>(`/api/projects/${id}`),
  saveProject: (id: string) =>
    req<Project>(`/api/projects/${id}/save`, { method: 'POST', body: '{}' }),
  putProject: (project: Project) =>
    req<Project>(`/api/projects/${project.id}`, {
      method: 'PUT',
      body: JSON.stringify(project),
    }),
  deleteProject: (id: string) =>
    req<{ ok: boolean }>(`/api/projects/${id}`, { method: 'DELETE' }),
  agent: (id: string, message: string, replace_shots = true) =>
    req<Project>(`/api/projects/${id}/agent`, {
      method: 'POST',
      body: JSON.stringify({ message, replace_shots }),
    }),
  agentChat: (
    id: string,
    message: string,
    attachments: import('./types').AgentAttachment[] = [],
  ) =>
    req<{
      project: Project
      message: string
      ui_actions: Array<{ type: string; tab?: string; text?: string; stage?: string }>
      used_builtin?: boolean
      provider?: string
    }>(`/api/projects/${id}/agent/chat`, {
      method: 'POST',
      body: JSON.stringify({ message, replace_shots: true, attachments }),
    }),
  addCharacter: (id: string, body: Partial<CharacterProfile>) =>
    req<Project>(`/api/projects/${id}/characters`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateCharacter: (id: string, character: CharacterProfile) =>
    req<Project>(`/api/projects/${id}/characters/${character.id}`, {
      method: 'PUT',
      body: JSON.stringify(character),
    }),
  deleteCharacter: (id: string, characterId: string) =>
    req<Project>(`/api/projects/${id}/characters/${characterId}`, { method: 'DELETE' }),
  addScene: (id: string, body: Partial<SceneProfile>) =>
    req<Project>(`/api/projects/${id}/scenes`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateScene: (id: string, scene: SceneProfile) =>
    req<Project>(`/api/projects/${id}/scenes/${scene.id}`, {
      method: 'PUT',
      body: JSON.stringify(scene),
    }),
  deleteScene: (id: string, sceneId: string) =>
    req<Project>(`/api/projects/${id}/scenes/${sceneId}`, { method: 'DELETE' }),
  addShot: (
    id: string,
    body: {
      title?: string
      action?: string
      dialogue?: string
      camera?: string
      duration_sec?: number
      prompt?: string
      storyboard_note?: string
      director_notes?: string
      character_ids?: string[]
      scene_id?: string | null
      insert_at?: number | null
    } = {},
  ) =>
    req<Project>(`/api/projects/${id}/shots`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  patchShot: (id: string, shotId: string, body: Record<string, unknown>) =>
    req<Project>(`/api/projects/${id}/shots/${shotId}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteShot: (id: string, shotId: string) =>
    req<Project>(`/api/projects/${id}/shots/${shotId}`, { method: 'DELETE' }),
  generate: (
    id: string,
    shot_ids?: string[],
    kind = 'video',
    mode?: string,
    opts?: {
      continue_from_previous?: boolean
      continue_from_take_id?: string
      is_rehearsal?: boolean
      inject_continuity?: boolean
    },
  ) =>
    req<Project>(`/api/projects/${id}/generate`, {
      method: 'POST',
      body: JSON.stringify({ shot_ids, kind, mode, ...opts }),
    }),
  continueSource: (id: string, shotId: string, takeId?: string) =>
    req<{
      ok: boolean
      detail?: string
      image_path?: string
      from_take_id?: string
      from_shot_title?: string
      thumb_path?: string
    }>(
      `/api/projects/${id}/shots/${shotId}/continue-source${
        takeId ? `?take_id=${encodeURIComponent(takeId)}` : ''
      }`,
    ),
  pinTake: (id: string, takeId: string) =>
    req<Project>(`/api/projects/${id}/takes/${takeId}/pin`, {
      method: 'POST',
      body: '{}',
    }),
  setTimeline: (id: string, clips: TimelineClip[]) =>
    req<Project>(`/api/projects/${id}/timeline`, {
      method: 'PUT',
      body: JSON.stringify(clips),
    }),
  setAudioTimeline: (id: string, clips: AudioClip[]) =>
    req<Project>(`/api/projects/${id}/audio-timeline`, {
      method: 'PUT',
      body: JSON.stringify(clips),
    }),
  addAudioClip: (id: string, clip: Partial<AudioClip>) =>
    req<Project>(`/api/projects/${id}/audio-timeline`, {
      method: 'POST',
      body: JSON.stringify(clip),
    }),
  deleteAudioClip: (id: string, clipId: string) =>
    req<Project>(`/api/projects/${id}/audio-timeline/${clipId}`, { method: 'DELETE' }),
  generateCaptions: (id: string, overwrite = false) =>
    req<Project>(`/api/projects/${id}/captions/generate?overwrite=${overwrite}`, {
      method: 'POST',
      body: '{}',
    }),
  timelineProgress: (id: string) =>
    req<{
      total_sec: number
      clip_count: number
      with_media: number
      pct_ready: number
      segments: Array<{
        clip_id: string
        shot_id: string
        title: string
        start: number
        end: number
        duration: number
        caption: string
        filter_id: string
        has_take: boolean
      }>
    }>(`/api/projects/${id}/timeline/progress`),
  captionsSrtUrl: (id: string) => `/api/projects/${id}/captions.srt`,
  engine: () => req<EngineStatus>('/api/engine'),
  engineLoras: () =>
    req<{ path: string; loras: import('./types').LoraFile[]; count: number }>('/api/engine/loras'),
  engineModels: () => req<import('./types').EngineModelsPack>('/api/engine/models'),
  engineModelDownload: (modelId: string, force = false) =>
    req<Record<string, unknown>>(
      `/api/engine/models/${encodeURIComponent(modelId)}/download?force=${force}`,
      { method: 'POST', body: '{}' },
    ),
  engineModelCancel: (modelId: string) =>
    req<Record<string, unknown>>(
      `/api/engine/models/${encodeURIComponent(modelId)}/cancel`,
      { method: 'POST', body: '{}' },
    ),
  engineModelClear: (modelId: string, deleteFiles = false) =>
    req<Record<string, unknown>>(
      `/api/engine/models/${encodeURIComponent(modelId)}/clear?delete_files=${deleteFiles}`,
      { method: 'POST', body: '{}' },
    ),
  engineModelActivate: (modelId: string) =>
    req<{ ok: boolean; active_model_id: string }>(
      `/api/engine/models/${encodeURIComponent(modelId)}/activate`,
      { method: 'POST', body: '{}' },
    ),
  engineModelAddCustom: (body: {
    hf_id: string
    label?: string
    kind?: string
    modes?: string[]
    min_vram_gb?: number
    default_steps?: number
    default_guidance?: number
    notes?: string
    activate?: boolean
  }) =>
    req<{ ok: boolean; model: EngineModel; models: EngineModel[] }>(
      '/api/engine/models/custom',
      { method: 'POST', body: JSON.stringify(body) },
    ),
  engineModelRemoveCustom: (modelId: string) =>
    req<{ ok: boolean; id: string }>(
      `/api/engine/models/custom/${encodeURIComponent(modelId)}`,
      { method: 'DELETE' },
    ),
  engineWan2gpScan: () =>
    req<
      Wan2gpInventory & {
        packs: EngineModel[]
        count: number
        total: number
      }
    >('/api/engine/wan2gp/scan'),
  engineWan2gpImport: (path: string, activate = true) =>
    req<{
      ok: boolean
      path: string
      packs: EngineModel[]
      models: EngineModel[]
      inventory: Wan2gpInventory
      counts: Record<string, number>
      hint: string
    }>('/api/engine/wan2gp/import', {
      method: 'POST',
      body: JSON.stringify({ path, activate }),
    }),
  engineAssets: () => req<Wan2gpInventory>('/api/engine/assets'),
  engineTemplates: () =>
    req<{ templates: ModelTemplate[]; count: number }>('/api/engine/templates'),
  engineTemplateInstall: (
    templateId: string,
    opts?: { include_optional?: boolean; activate?: boolean; force?: boolean },
  ) =>
    req<{
      ok: boolean
      template_id: string
      label: string
      started: unknown[]
      count: number
      hint: string
      templates: ModelTemplate[]
      models: EngineModel[]
    }>(`/api/engine/templates/${encodeURIComponent(templateId)}/install`, {
      method: 'POST',
      body: JSON.stringify(opts || { include_optional: true, activate: true }),
    }),
  engineJobs: () => req<EngineJob[]>('/api/engine/jobs'),
  engineJob: (id: string) => req<EngineJob>(`/api/engine/jobs/${id}`),
  engineCancelJob: (id: string) =>
    req<EngineJob>(`/api/engine/jobs/${encodeURIComponent(id)}/cancel`, {
      method: 'POST',
      body: '{}',
    }),
  engineCancelAll: () =>
    req<{ ok: boolean; stopped: number }>('/api/engine/jobs/cancel-all', {
      method: 'POST',
      body: '{}',
    }),
  engineDismissJob: (id: string) =>
    req<{ ok: boolean; id: string }>(`/api/engine/jobs/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    }),
  engineClearFinishedJobs: () =>
    req<{ ok: boolean; removed: number }>('/api/engine/jobs/clear-finished', {
      method: 'POST',
      body: '{}',
    }),
  engineWorkflows: () =>
    req<{ jobs: EngineJob[] }>('/api/engine/workflows'),
  engineGenerate: (body: Record<string, unknown>) =>
    req<EngineJob>('/api/engine/generate', { method: 'POST', body: JSON.stringify(body) }),
  engineEnhancePrompt: (body: {
    prompt: string
    negative_prompt?: string
    mode?: string
    style?: string | null
    force_builtin?: boolean
  }) =>
    req<{
      prompt: string
      negative_prompt: string
      notes: string
      source: string
    }>('/api/engine/enhance-prompt', { method: 'POST', body: JSON.stringify(body) }),
  engineEstimate: (body: Record<string, unknown>) =>
    req<GpuEstimate>('/api/engine/estimate', { method: 'POST', body: JSON.stringify(body) }),
  deleteTake: (id: string, takeId: string, deleteFiles = true) =>
    req<Project>(
      `/api/projects/${id}/takes/${takeId}?delete_files=${deleteFiles}`,
      { method: 'DELETE' },
    ),
  clearPreviewTakes: (id: string, deleteFiles = true) =>
    req<Project>(
      `/api/projects/${id}/takes/clear-previews?delete_files=${deleteFiles}`,
      { method: 'POST', body: '{}' },
    ),
  takeAddAudio: async (id: string, takeId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(
      `/api/projects/${id}/takes/${encodeURIComponent(takeId)}/add-audio`,
      { method: 'POST', body: fd },
    )
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<{
      ok: boolean
      project: Project
      message: string
    }>
  },
  cancelPersonalImport: (jobId: string) =>
    req<PersonalImportJob>(`/api/personal/imports/${jobId}/cancel`, {
      method: 'POST',
      body: '{}',
    }),
  clearPersonalImport: (jobId: string) =>
    req<{ ok: boolean }>(`/api/personal/imports/${jobId}`, { method: 'DELETE' }),
  getContinuity: (id: string) => req<ContinuityData>(`/api/projects/${id}/continuity`),
  putContinuity: (
    id: string,
    body: { rules: string[]; auto_reject_below?: number; rebuild_bible?: boolean },
  ) =>
    req<Project>(`/api/projects/${id}/continuity`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  rescoreContinuity: (id: string) =>
    req<Project>(`/api/projects/${id}/continuity/rescore`, { method: 'POST', body: '{}' }),
  rehearsal: (id: string, body?: { shot_ids?: string[]; takes_per_shot?: number; quality?: string }) =>
    req<Project>(`/api/projects/${id}/rehearsal`, {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),
  promoteTake: (id: string, takeId: string) =>
    req<Project>(`/api/projects/${id}/takes/${takeId}/promote`, {
      method: 'POST',
      body: '{}',
    }),
  exportNle: (id: string, fps = 24) =>
    req<{
      folder: string
      zip_path: string
      clip_count: number
      media_copied: number
      download_url: string
    }>(`/api/projects/${id}/export/nle?fps=${fps}`, { method: 'POST', body: '{}' }),
  engineUpload: async (file: File, kind: string = 'image') => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch(`/api/engine/upload?kind=${encodeURIComponent(kind)}`, {
      method: 'POST',
      body: fd,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<{ path: string; url: string }>
  },
  importDirectorVideo: async (id: string, file: File, opts?: { title?: string; insert_at?: number }) => {
    const fd = new FormData()
    fd.append('file', file)
    if (opts?.title) fd.append('title', opts.title)
    if (opts?.insert_at != null) fd.append('insert_at', String(opts.insert_at))
    const res = await fetch(`/api/projects/${id}/director/import-video`, {
      method: 'POST',
      body: fd,
    })
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<{
      ok: boolean
      project: import('./types').Project
      shot_id: string
      take_id: string
      clip_id: string
      duration_sec: number
      message: string
    }>
  },
  frameSizes: () =>
    req<{ sizes: import('./frameSizes').FrameSize[] }>('/api/frame-sizes'),
  setFrameSize: (id: string, frame_size_id: string) =>
    req<Project>(`/api/projects/${id}/frame-size`, {
      method: 'POST',
      body: JSON.stringify({ frame_size_id }),
    }),
  recipes: () => req<{ recipes: import('./types').RecipeInfo[] }>('/api/recipes'),
  applyRecipe: (id: string, recipe_id: string) =>
    req<Project>(`/api/projects/${id}/recipes/apply`, {
      method: 'POST',
      body: JSON.stringify({ recipe_id }),
    }),
  stitch: (id: string) =>
    req<{
      playlist: unknown
      preview_url?: string | null
      preview_path?: string | null
      method: string
      message: string
    }>(`/api/projects/${id}/stitch`, { method: 'POST', body: '{}' }),
  filmNight: (id: string, stage: 'full' | 'rehearse' | 'promote' | 'finals' | 'stitch' = 'full') =>
    req<{
      ok: boolean
      project?: Project
      message: string
      steps?: string[]
      next?: string | null
      stitch?: { preview_url?: string; message?: string }
    }>(`/api/projects/${id}/film-night`, {
      method: 'POST',
      body: JSON.stringify({ stage }),
    }),
  exportPack: (id: string) =>
    req<{
      zip_path: string
      download_url: string
      media_count: number
      title: string
      message: string
    }>(`/api/projects/${id}/export/pack`, { method: 'POST', body: '{}' }),
  listPacks: () =>
    req<{ packs: Array<{ path: string; name: string; size_mb: number; download_url: string }> }>(
      '/api/packs',
    ),
  importPack: (path: string) =>
    req<Project>(`/api/packs/import?path=${encodeURIComponent(path)}`, {
      method: 'POST',
      body: '{}',
    }),
  refreshIdentityLock: (id: string, characterId: string) =>
    req<Project>(`/api/projects/${id}/characters/${characterId}/identity-lock`, {
      method: 'POST',
      body: '{}',
    }),
}

export function mediaUrl(path?: string | null): string | undefined {
  if (!path) return undefined
  const normalized = path.replace(/\\/g, '/')
  for (const marker of ['/outputs/', '/uploads/', '/.studionels/media/']) {
    const idx = normalized.indexOf(marker)
    if (idx >= 0) {
      const rel = normalized.slice(idx + marker.length)
      // uploads live at /media/uploads when mirrored, else file API
      if (marker === '/uploads/') return `/api/file?path=${encodeURIComponent(path)}`
      return `/media/${rel}`
    }
  }
  return `/api/file?path=${encodeURIComponent(path)}`
}
