import type {
  AgentProviderInfo,
  CharacterProfile,
  ContinuityData,
  EngineJob,
  EngineStatus,
  GpuEstimate,
  Health,
  Preset,
  Project,
  ProjectSummary,
  SceneProfile,
  Settings,
  TimelineClip,
} from './types'

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
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
      status: {
        provider: string
        label: string
        model: string
        needs_key: boolean
        key_set: boolean
        reachable: boolean
        detail: string
      }
    }>('/api/agent/providers'),
  listProjects: () => req<ProjectSummary[]>('/api/projects'),
  createProject: (body: { title: string; mode: string; logline?: string; preset_id?: string }) =>
    req<Project>('/api/projects', { method: 'POST', body: JSON.stringify(body) }),
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
  engine: () => req<EngineStatus>('/api/engine'),
  engineLoras: () =>
    req<{ path: string; loras: import('./types').LoraFile[]; count: number }>('/api/engine/loras'),
  engineJobs: () => req<EngineJob[]>('/api/engine/jobs'),
  engineJob: (id: string) => req<EngineJob>(`/api/engine/jobs/${id}`),
  engineGenerate: (body: Record<string, unknown>) =>
    req<EngineJob>('/api/engine/generate', { method: 'POST', body: JSON.stringify(body) }),
  engineEstimate: (body: Record<string, unknown>) =>
    req<GpuEstimate>('/api/engine/estimate', { method: 'POST', body: JSON.stringify(body) }),
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
  engineUpload: async (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const res = await fetch('/api/engine/upload', { method: 'POST', body: fd })
    if (!res.ok) throw new Error(await res.text())
    return res.json() as Promise<{ path: string; url: string }>
  },
}

export function mediaUrl(path?: string | null): string | undefined {
  if (!path) return undefined
  const normalized = path.replace(/\\/g, '/')
  for (const marker of ['/outputs/', '/uploads/', '/.framewright/media/']) {
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
