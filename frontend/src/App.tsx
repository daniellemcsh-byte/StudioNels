import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api, mediaUrl } from './api'
import { LEARN_TOPICS, type LearnSectionId } from './learning'
import DirectorStudio from './DirectorStudio'
import StoryboardStudio from './StoryboardStudio'
import FilmNightTab from './FilmNightTab'
import FirstRunWizard, { shouldShowFirstRun } from './FirstRunWizard'
import { INSPIRATION_CLIPS, inspirationRunsNow, type InspirationClip } from './inspiration'
import {
  DURATION_PRESETS,
  VISUAL_STYLES,
  formatDuration,
} from './stylesCatalog'
import { FRAME_SIZES, frameById, framesByOrientation } from './frameSizes'
import type { RecipeInfo } from './types'
import {
  AUDIO_KINDS,
  MUSIC_MOODS,
  VOICE_ACCENTS,
  type AudioKind,
} from './audioCatalog'
import {
  CHARACTER_TRAITS,
  DEFAULT_TRAITS,
  buildCharacterPrompt,
} from './characterCreator'
import type {
  AgentAttachment,
  AgentProvider,
  AgentProviderInfo,
  AgentStatus,
  CharacterProfile,
  ContinuityData,
  EngineJob,
  EngineModel,
  EngineStatus,
  EngineWarmStatus,
  GenMode,
  GpuEstimate,
  Health,
  LoraFile,
  Mode,
  Preset,
  Project,
  ProjectSummary,
  SceneProfile,
  Settings,
  Shot,
  TabId,
  ModelTemplate,
  Wan2gpInventory,
} from './types'
import './styles.css'

const GEN_STAGES = ['Queue', 'Load', 'Setup', 'Generate', 'Finish'] as const

function formatClock(sec: number): string {
  const s = Math.max(0, Math.floor(sec || 0))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

function jobElapsedSec(job: EngineJob, nowMs = Date.now()): number {
  if (job.status !== 'running' && typeof job.elapsed_sec === 'number') {
    return Math.max(0, job.elapsed_sec)
  }
  const start = job.started_at || (job.status === 'running' || job.status === 'queued' ? job.created_at : null)
  if (start) {
    const t0 = Date.parse(start)
    if (Number.isFinite(t0)) return Math.max(0, Math.floor((nowMs - t0) / 1000))
  }
  return typeof job.elapsed_sec === 'number' ? job.elapsed_sec : 0
}

function jobEtaSec(job: EngineJob): number | null {
  if (typeof job.eta_sec === 'number' && job.eta_sec >= 0) return job.eta_sec
  const m =
    (job.message || '').match(/~\s*(\d+)m(\d+)s\s*left/i) ||
    (job.message || '').match(/~\s*(\d+)s\s*left/i)
  if (!m) return null
  if (m[2] != null) return Number(m[1]) * 60 + Number(m[2])
  return Number(m[1])
}

function useNowMs(active: boolean, ms = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    setNow(Date.now())
    const t = window.setInterval(() => setNow(Date.now()), ms)
    return () => window.clearInterval(t)
  }, [active, ms])
  return now
}

/** Human-readable what a job is doing right now (queue / dock / status bar). */
function describeJobActivity(job: EngineJob, nowMs = Date.now()): {
  phase: string
  detail: string
  tone: 'idle' | 'wait' | 'load' | 'run' | 'done' | 'fail' | 'stop'
  stageIndex: number
  stages: readonly string[]
  elapsedLabel: string
  etaLabel: string
  stepLabel: string
  timerLabel: string
} {
  const msg = (job.message || '').toLowerCase()
  const pct = Math.round((job.progress || 0) * 100)
  const stages = GEN_STAGES
  const elapsedLabel = formatClock(jobElapsedSec(job, nowMs))
  const eta = jobEtaSec(job)
  const etaLabel = eta != null ? `~${formatClock(eta)} left` : ''
  const stepFromJob =
    job.step != null && job.steps_total != null ? `step ${job.step}/${job.steps_total}` : ''
  const stepMatch =
    (job.message || '').match(/step\s+(\d+)\s*\/\s*(\d+)/i) ||
    (job.message || '').match(/step\s+(\d+)\s+of\s+(\d+)/i)
  const stepLabel = stepFromJob || (stepMatch ? `step ${stepMatch[1]}/${stepMatch[2]}` : '')
  const timerLabel =
    job.status === 'queued'
      ? `waiting ${elapsedLabel}`
      : [elapsedLabel, etaLabel].filter(Boolean).join(' · ')
  const modeLabel =
    job.mode === 't2v' || job.mode === 'i2v' || job.mode === 'ref2v'
      ? 'video'
      : job.mode === 't2a'
        ? 'audio'
        : job.mode === 'upsample_image' || job.mode === 'upsample_video'
          ? 'upsample'
          : 'image'

  const pack = (
    phase: string,
    detail: string,
    tone: 'idle' | 'wait' | 'load' | 'run' | 'done' | 'fail' | 'stop',
    stageIndex: number,
  ) => ({ phase, detail, tone, stageIndex, stages, elapsedLabel, etaLabel, stepLabel, timerLabel })

  if (job.status === 'queued') {
    return pack('Waiting in queue', `Next up · ${job.model_label}`, 'wait', 0)
  }
  if (job.status === 'cancelled') {
    return pack('Stopped', job.message || 'Cancelled — workflow kept', 'stop', 0)
  }
  if (job.status === 'failed') {
    return pack('Failed', job.error || job.message || 'See error', 'fail', 0)
  }
  if (job.status === 'done') {
    const out =
      modeLabel === 'video'
        ? 'Video ready'
        : modeLabel === 'audio'
          ? 'Audio ready'
          : modeLabel === 'upsample'
            ? 'Upsample ready'
            : 'Image ready'
    return pack(
      job.preview ? `Preview ${out.toLowerCase()}` : out,
      job.message || `${pct}%`,
      'done',
      4,
    )
  }

  // Avoid matching "already-downloaded" / similar advice text as a real download.
  if (
    /download(?:ing)?\s+(?:model|weights|files)|from hugging face|fetching from|hf hub/.test(msg)
  ) {
    return pack('Downloading model files', job.message || `${pct}%`, 'load', 1)
  }
  if (
    /boot(?:ing)?|checking gpu|pytorch|starting (?:gpu )?worker|warm engine|worker boot|importing/.test(
      msg,
    )
  ) {
    return pack('Booting engine', job.message || `${pct}%`, 'load', 1)
  }
  if (
    /loading pipeline|loading.*weights|loading.*model|first amd load|reading weights/.test(msg)
  ) {
    return pack('Loading model weights', job.message || `${pct}%`, 'load', 1)
  }
  if (/text encoder/.test(msg)) {
    return pack('Loading text encoder', job.message || `${pct}%`, 'load', 2)
  }
  if (/lora/.test(msg)) {
    return pack('Applying LoRA', job.message || `${pct}%`, 'load', 2)
  }
  if (/mux|attach.*audio|audio attached/.test(msg)) {
    return pack('Attaching audio to video', job.message || `${pct}%`, 'run', 3)
  }
  if (/upsample|upsampling/.test(msg)) {
    return pack('Upsampling', job.message || `${pct}%`, 'run', 3)
  }
  if (/preview/.test(msg)) {
    return pack(`Creating preview ${modeLabel}`, job.message || `${pct}%`, 'run', 3)
  }
  if (/decod|assembling frames|exporting mp4|denoise done/.test(msg)) {
    return pack('Decoding / exporting', job.message || `${pct}%`, 'run', 3)
  }
  if (/generat|denois|step\s*\d|waiting on gpu/.test(msg) || (job.progress || 0) >= 0.2) {
    const stepMatch =
      (job.message || '').match(/step\s+(\d+)\s*\/\s*(\d+)/i) ||
      (job.message || '').match(/step\s+(\d+)\s+of\s+(\d+)/i)
    const stepBit = stepMatch ? ` · step ${stepMatch[1]}/${stepMatch[2]}` : ''
    const staleSec = (() => {
      if (!job.updated_at) return 0
      const t = Date.parse(job.updated_at)
      return Number.isFinite(t) ? Math.max(0, Math.floor((nowMs - t) / 1000)) : 0
    })()
    const hung =
      job.status === 'running' &&
      ((staleSec >= 90 && !(job.step && job.step > 0)) ||
        (jobElapsedSec(job, nowMs) >= 600 && !(job.step && job.step > 0)))
    const phase = hung
      ? 'Stuck — Stop & retry'
      : modeLabel === 'video'
        ? `Generating video${stepBit}`
        : modeLabel === 'audio'
          ? `Generating audio${stepBit}`
          : modeLabel === 'upsample'
            ? `Upsampling${stepBit}`
            : `Generating image${stepBit}`
    const detail = hung
      ? `${job.message || `${pct}%`} · Still on this model. A large one streams from RAM, so the first step is the slow one.`
      : job.message || `${pct}%`
    return pack(phase, detail, hung ? 'fail' : 'run', 3)
  }
  if (/start/.test(msg)) {
    return pack('Booting engine', job.message || `${job.model_label} · ${pct}%`, 'load', 1)
  }
  return pack(
    job.status === 'running' ? `Working on ${modeLabel}` : job.status,
    job.message || job.prompt || `${pct}%`,
    'run',
    3,
  )
}

function GenerationStageBar({
  job,
  showTipsLink,
  onOpenTips,
}: {
  job: EngineJob
  showTipsLink?: boolean
  onOpenTips?: () => void
}) {
  const live = job.status === 'running' || job.status === 'queued'
  const nowMs = useNowMs(live)
  const act = describeJobActivity(job, nowMs)
  const pct = Math.round((job.progress || 0) * 100)
  const slowLoad =
    live && act.stageIndex <= 2 && (job.progress || 0) < 0.25
  const slowGen =
    job.status === 'running' &&
    act.stageIndex === 3 &&
    /starting denoise|Generating…|step 0\/|Waiting on GPU/i.test(job.message || '')
  const noStepYet =
    job.status === 'running' && !(job.step && job.step > 0) && (job.progress || 0) >= 0.18

  return (
    <div className="gen-stage-bar">
      <div className="gen-timer-row" aria-live="polite">
        <div className="gen-timer-clock" title="Elapsed">
          <span className="gen-timer-label">Elapsed</span>
          <strong>{act.elapsedLabel || '0:00'}</strong>
        </div>
        <div className="gen-timer-clock" title="Estimated time remaining">
          <span className="gen-timer-label">ETA</span>
          <strong>{act.etaLabel ? act.etaLabel.replace(' left', '') : '—'}</strong>
        </div>
        <div className="gen-timer-clock" title="Denoise step">
          <span className="gen-timer-label">Step</span>
          <strong>{act.stepLabel ? act.stepLabel.replace(/^step\s+/i, '') : '—'}</strong>
        </div>
        <div className="gen-timer-clock" title="Progress">
          <span className="gen-timer-label">Done</span>
          <strong>{pct}%</strong>
        </div>
      </div>
      {noStepYet && jobElapsedSec(job, nowMs) >= 120 ? (
        <p className="fit-warn tiny gen-stall-hint">
          Still before step 1 after {act.elapsedLabel}
          {pct < 20
            ? ' — still loading this model into RAM. The step counter starts after that.'
            : ' — a large model streams from RAM, so step 1 can sit for a few minutes while the elapsed clock moves.'}
        </p>
      ) : null}
      <div className="gen-stage-track" role="list" aria-label="Generation stages">
        {act.stages.map((label, i) => {
          const state = i < act.stageIndex ? 'done' : i === act.stageIndex ? 'active' : 'todo'
          return (
            <div key={label} className={`gen-stage ${state}`} role="listitem">
              <span className="gen-stage-dot" />
              <span className="gen-stage-label">{label}</span>
            </div>
          )
        })}
      </div>
      <div className="gen-stage-meta">
        <strong className={`job-phase tone-${act.tone}`}>{act.phase}</strong>
        <span className="muted tiny gen-stage-detail">{act.detail}</span>
      </div>
      <div className="progress">
        <div style={{ width: `${pct}%` }} />
      </div>
      {(slowLoad || slowGen) && showTipsLink && onOpenTips ? (
        <div className="gen-speed-tips">
          <p className="muted tiny">
            {slowGen
              ? 'Still working — the Elapsed clock ticking means it is not frozen. First denoise step on AMD can take a while; 98% VRAM is normal.'
              : 'First AMD load can take several minutes while weights move into VRAM. Want it faster next time?'}
          </p>
          <button type="button" className="btn acid tiny" onClick={onOpenTips}>
            Speed-up tips
          </button>
        </div>
      ) : null}
    </div>
  )
}

function SpeedTipsPanel({
  open,
  onClose,
  onOpenLearning,
}: {
  open: boolean
  onClose: () => void
  onOpenLearning?: () => void
}) {
  if (!open) return null
  return (
    <div className="panel speed-tips-panel">
      <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>Speed up generation</h3>
        <button type="button" className="btn ghost tiny" onClick={onClose}>
          Close
        </button>
      </div>
      <ol className="speed-tips-list">
        <li>
          <strong>Draft quality</strong> — fewer steps; use High only after the look works.
        </li>
        <li>
          <strong>Shorter clips</strong> — 2–3s, 8–16 fps, or lower frame count.
        </li>
        <li>
          <strong>Smaller size</strong> — start at 768×432 before going 1080p.
        </li>
        <li>
          <strong>Any Ready model</strong> — Wan, LTX, FLUX, and the rest run on the same engine. A smaller one finishes a test sooner.
        </li>
        <li>
          <strong>One job at a time</strong> — and finish model download (Ready) before generating.
        </li>
        <li>
          <strong>First load is slow</strong> — ROCm compiles kernels once; later runs are quicker.
        </li>
        <li>
          <strong>The engine stays warm</strong> — the first clip loads the model, the next one reuses it.
        </li>
      </ol>
      {onOpenLearning ? (
        <button type="button" className="btn secondary tiny" onClick={onOpenLearning}>
          Open full Speed tips guide
        </button>
      ) : null}
    </div>
  )
}

function EngineWarmLine() {
  const [warm, setWarm] = useState<EngineWarmStatus | null>(null)
  useEffect(() => {
    let cancelled = false
    const tick = () => {
      api
        .engineWarm()
        .then((w) => {
          if (!cancelled) setWarm(w)
        })
        .catch(() => undefined)
    }
    tick()
    const t = window.setInterval(tick, 2000)
    return () => {
      cancelled = true
      window.clearInterval(t)
    }
  }, [])
  if (!warm) return null
  if (warm.preloading) {
    return (
      <p className="job-phase tone-load tiny" style={{ marginBottom: 10 }}>
        {warm.message || 'Preloading model into RAM/VRAM…'}
      </p>
    )
  }
  if (warm.cached?.length) {
    return (
      <p className="job-phase tone-done tiny" style={{ marginBottom: 10 }}>
        Ready: {warm.cached[0]}
      </p>
    )
  }
  return null
}

function modelStatus(m: EngineModel): string {
  return m.download_status || (m.installed ? 'installed' : 'not_downloaded')
}

function modelDownloadLabel(st: string, pct = 0): string {
  if (st === 'installed') return 'Downloaded'
  if (st === 'downloading') return `Downloading · ${Math.max(0, Math.min(100, pct))}%`
  if (st === 'not_downloaded') return 'Not downloaded'
  if (st === 'stalled') return 'Download stalled'
  if (st === 'failed') return 'Download failed'
  if (st === 'cancelled') return 'Download cancelled'
  return st || 'Unknown'
}

function modelDownloadBadgeClass(st: string): string {
  if (st === 'installed') return 'ready'
  if (st === 'downloading') return 'running'
  if (st === 'failed' || st === 'stalled') return 'failed'
  if (st === 'not_downloaded' || st === 'cancelled') return 'missing'
  return 'queued'
}

function describeDownloadActivity(m: EngineModel): {
  phase: string
  detail: string
  tone: 'load' | 'fail' | 'stop'
} {
  const pct = Math.round((m.download_progress || 0) * 100)
  const st = m.download_status || ''
  if (st === 'stalled') {
    return {
      phase: 'Download stalled',
      detail: m.download_message || `${m.label} · ${pct}% — Cancel / Clear / Retry`,
      tone: 'fail',
    }
  }
  if (st === 'failed') {
    return { phase: 'Download failed', detail: m.download_error || m.download_message || m.label, tone: 'fail' }
  }
  if (st === 'cancelled') {
    return { phase: 'Download cancelled', detail: m.download_message || m.label, tone: 'stop' }
  }
  return {
    phase: 'Downloading model',
    detail: m.download_message || `${m.label} · ${pct}%`,
    tone: 'load',
  }
}

function ModelDownloadProgress({
  model,
  compact = false,
  onCancel,
  onRetry,
}: {
  model: EngineModel
  compact?: boolean
  onCancel?: () => void
  onRetry?: () => void
}) {
  const st = model.download_status || ''
  const pct = Math.max(0, Math.min(100, Math.round((model.download_progress || 0) * 100)))
  const act = describeDownloadActivity(model)
  const live = st === 'downloading' || st === 'stalled'
  if (!live && st !== 'failed' && st !== 'cancelled') return null

  return (
    <div
      className={`download-progress ${compact ? 'compact' : ''} tone-${act.tone}`}
      role="status"
      aria-live="polite"
      aria-label={`${act.phase} ${pct}%`}
    >
      <div className="download-progress-head">
        <strong>{act.phase}</strong>
        <span className="download-progress-pct">{pct}%</span>
      </div>
      <div className="progress download-progress-bar" aria-hidden>
        <div style={{ width: `${pct}%` }} />
      </div>
      <div className="download-progress-meta muted tiny">
        {model.label}
        {model.download_message ? ` · ${model.download_message}` : act.detail ? ` · ${act.detail}` : ''}
      </div>
      {(onCancel || onRetry) && (
        <div className="inline-actions" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
          {live && onCancel ? (
            <button type="button" className="btn ghost tiny" onClick={onCancel}>
              Cancel download
            </button>
          ) : null}
          {(st === 'failed' || st === 'stalled' || st === 'cancelled') && onRetry ? (
            <button type="button" className="btn acid tiny" onClick={onRetry}>
              Retry download
            </button>
          ) : null}
        </div>
      )}
    </div>
  )
}

const NAV_GROUPS: { id: string; label: string; blurb: string; items: { id: TabId; label: string }[] }[] = [
  {
    id: 'make',
    label: 'Make',
    blurb: 'Video, stills, sound',
    items: [
      { id: 'generate', label: 'Video & image' },
      { id: 'audio', label: 'Audio' },
      { id: 'models', label: 'Models' },
      { id: 'upsample', label: 'Sharpen' },
    ],
  },
  {
    id: 'film',
    label: 'Film',
    blurb: 'Cuts and finished takes',
    items: [
      { id: 'filmnight', label: 'Film night' },
      { id: 'director', label: 'Director' },
      { id: 'shots', label: 'Shots' },
      { id: 'storyboard', label: 'Storyboard' },
      { id: 'sampling', label: 'Takes' },
    ],
  },
  {
    id: 'story',
    label: 'Story',
    blurb: 'People, look, and script',
    items: [
      { id: 'agent', label: 'Agent' },
      { id: 'characters', label: 'Characters' },
      { id: 'creator', label: 'New character' },
      { id: 'profiles', label: 'People & places' },
      { id: 'time', label: 'Look & length' },
      { id: 'inspiration', label: 'Inspiration' },
      { id: 'continuity', label: 'Match looks' },
    ],
  },
  {
    id: 'more',
    label: 'More',
    blurb: 'Tests, help, settings',
    items: [
      { id: 'rehearsal', label: 'Rehearsal' },
      { id: 'templates', label: 'Templates' },
      { id: 'learning', label: 'Learning' },
      { id: 'sources', label: 'My links' },
      { id: 'addons', label: 'Add-ons' },
      { id: 'info', label: 'About' },
      { id: 'settings', label: 'Settings' },
    ],
  },
]

function groupForTab(tabId: TabId): string {
  return NAV_GROUPS.find((g) => g.items.some((i) => i.id === tabId))?.id || 'make'
}

export type InspirationSeed = {
  mode: GenMode
  prompt: string
  title: string
}

const MODES: { id: Mode; label: string }[] = [
  { id: 'short', label: 'Short film' },
  { id: 'film', label: 'Film' },
  { id: 'music_video', label: 'Music video' },
  { id: 'ad', label: 'Ad / promo' },
  { id: 'experiment', label: 'Experiment' },
]


function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** "just now", "5 min ago", "3 h ago", "2 days ago", else a date. */
function formatAgo(iso: string) {
  const t = Date.parse(iso)
  if (!Number.isFinite(t)) return ''
  const s = Math.max(0, (Date.now() - t) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} day${s < 86400 * 2 ? '' : 's'} ago`
  return new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

function Brand() {
  return (
    <div className="brand-mark" aria-label="StudioNels">
      <span className="dot" aria-hidden />
      <span className="brand-text">StudioNels</span>
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [settings, setSettings] = useState<Settings | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [tab, setTab] = useState<TabId>('generate')
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    make: true,
  })
  const [showWizard, setShowWizard] = useState(false)
  const [newFrameSize, setNewFrameSize] = useState('16:9-draft')
  const [navOpen, setNavOpen] = useState(true)
  const [inspirationSeed, setInspirationSeed] = useState<InspirationSeed | null>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const goTab = (id: TabId) => {
    setTab(id)
    setOpenGroups({ [groupForTab(id)]: true })
  }
  const [showNew, setShowNew] = useState(false)
  const [homeView, setHomeView] = useState<'home' | 'learning' | 'sources'>('home')
  const [title, setTitle] = useState('My first local film')
  const [mode, setMode] = useState<Mode>('short')
  const [agentText, setAgentText] = useState('')
  const [agentAttachments, setAgentAttachments] = useState<AgentAttachment[]>([])
  const [replaceShots, setReplaceShots] = useState(true)
  // Home: quick start + recent work.
  const [quickPrompt, setQuickPrompt] = useState('')
  const [quickMode, setQuickMode] = useState<'t2v' | 't2i'>('t2v')
  const [quickTarget, setQuickTarget] = useState('')
  const [showEmptyProjects, setShowEmptyProjects] = useState(false)
  const [homeJobs, setHomeJobs] = useState<EngineJob[]>([])
  const homeTakes = homeJobs.filter((j) => j.status === 'done' && !!j.media_path && !isAudioPath(j.media_path))
  const latestTakeFor = (projectId: string) => homeTakes.find((j) => j.project_id === projectId)
  const takeCountFor = (projectId: string) => homeJobs.filter((j) => j.project_id === projectId && j.status === 'done').length

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 2800)
  }

  const useInspiration = (clip: InspirationClip) => {
    if (!project) return
    setInspirationSeed({ mode: clip.mode, prompt: clip.prompt, title: clip.title })
    goTab('generate')
    notify(
      inspirationRunsNow(clip.mode)
        ? `“${clip.title}” is on Video & image. Press Generate when you want it.`
        : `“${clip.title}” needs a photo. Add one on Video & image, then press Generate.`,
    )
  }

  const refreshHome = async () => {
    const [h, p, s, list, jobs] = await Promise.all([
      api.health(),
      api.presets(),
      api.getSettings(),
      api.listProjects(),
      api.engineJobs().catch(() => [] as EngineJob[]),
    ])
    setHealth(h)
    setPresets(p)
    setSettings(s)
    setProjects(list)
    setHomeJobs(jobs)
  }

  useEffect(() => {
    refreshHome()
      .then(async () => {
        const h = await api.health()
        if (shouldShowFirstRun(h)) setShowWizard(true)
      })
      .catch((e) => notify(String(e.message || e)))
  }, [])

  /** Home quick start: open a project on Make with the typed prompt ready. */
  const quickStart = async () => {
    const text = quickPrompt.trim()
    if (!text) return
    setBusy(true)
    try {
      const targetId = quickTarget === '' ? projects[0]?.id : quickTarget
      const p =
        quickTarget === '__new__' || !targetId
          ? await api.createProject({
              title: text.length > 40 ? `${text.slice(0, 40).trim()}…` : text,
              mode: 'short',
              preset_id: settings?.preset_id,
              frame_size_id: newFrameSize,
            })
          : await api.getProject(targetId)
      setProject(p)
      setInspirationSeed({ mode: quickMode, prompt: text, title: 'Quick start' })
      goTab('generate')
      setQuickPrompt('')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const openProject = async (id: string, toTab?: TabId) => {
    setBusy(true)
    try {
      const p = await api.getProject(id)
      setProject(p)
      if (toTab) {
        goTab(toTab)
        return
      }
      // Film night + Director are the home path once work exists
      if ((p.takes && p.takes.length > 0) || (p.timeline && p.timeline.length > 0)) {
        goTab('director')
      } else if (p.shots.length > 0) {
        goTab('filmnight')
      } else {
        goTab('agent')
      }
    } finally {
      setBusy(false)
    }
  }

  const createProject = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const p = await api.createProject({
        title,
        mode,
        preset_id: settings?.preset_id,
        frame_size_id: newFrameSize,
      })
      setShowNew(false)
      setProject(p)
      goTab('filmnight')
      await refreshHome()
      notify('Project created — Film night is ready when shots exist.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!project) return
    setBusy(true)
    try {
      const p = await api.saveProject(project.id)
      setProject(p)
      notify('Saved. Safe to power off — your workflow is on disk.')
      await refreshHome()
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const applyAgentUiActions = async (
    actions: Array<{ type: string; tab?: string; text?: string; stage?: string }>,
    projectId: string,
    userMessage: string,
  ) => {
    const low = userMessage.toLowerCase()
    const userAskedNav = /(?:open|go to|show|switch to)\s/.test(low) || /film night|director/.test(low)
    for (const a of actions || []) {
      if (a.type === 'navigate' && a.tab) {
        // Stay on Agent unless the user asked to leave, or Film night is starting
        const leavingChat = a.tab !== 'agent'
        const filmNight = a.tab === 'filmnight'
        if (leavingChat && !userAskedNav && !filmNight) continue
        if (leavingChat && filmNight && !actions.some((x) => x.type === 'run_film_night') && !/film night/.test(low)) {
          continue
        }
        goTab(a.tab as TabId)
      } else if (a.type === 'notify' && a.text) {
        notify(a.text)
      } else if (a.type === 'run_film_night') {
        goTab('filmnight')
        try {
          const stage = (a.stage || 'full') as
            | 'full'
            | 'rehearse'
            | 'promote'
            | 'finals'
            | 'stitch'
          const res = await api.filmNight(projectId, stage)
          if (res.project) setProject(res.project)
          notify(res.message || 'Film night started.')
        } catch (err) {
          notify(String((err as Error).message || err))
        }
      }
    }
  }

  const runAgent = async () => {
    if (!project) return
    if (!agentText.trim() && agentAttachments.length === 0) return
    const message = agentText.trim()
    setBusy(true)
    try {
      const pending = [...agentAttachments]
      const res = await api.agentChat(project.id, message, pending)
      setProject(res.project)
      setAgentText('')
      setAgentAttachments([])
      const actions = res.ui_actions || []
      await applyAgentUiActions(actions, res.project.id, message)
      const leftChat = actions.some(
        (a) =>
          (a.type === 'navigate' && a.tab && a.tab !== 'agent') ||
          a.type === 'run_film_night',
      )
      const askedToLeave =
        /(?:open|go to|show|switch to)\s/.test(message.toLowerCase()) ||
        /film night|open director/.test(message.toLowerCase())
      // Stay on Agent for normal chat; only leave when user asked (or Film night runs)
      if (!leftChat || !askedToLeave) goTab('agent')
    } catch (err) {
      // Fallback to classic shot planner if chat endpoint missing on old server
      try {
        const p = await api.agent(project.id, message || 'Plan with attached refs', replaceShots)
        setProject(p)
        setAgentText('')
        setAgentAttachments([])
        goTab('agent')
        notify('Shot list updated — stay in chat, or open Shots when you want.')
      } catch {
        notify(String((err as Error).message || err))
      }
    } finally {
      setBusy(false)
    }
  }

  const attachCharacterToAgent = (c: CharacterProfile) => {
    setAgentAttachments((prev) => {
      if (prev.some((a) => a.character_id === c.id)) return prev
      return [
        ...prev,
        {
          kind: 'character',
          character_id: c.id,
          name: c.name,
          path: c.reference_path || null,
        },
      ]
    })
    goTab('agent')
    notify(`Added ${c.name} to agent chat.`)
  }

  const attachSceneToAgent = (s: SceneProfile) => {
    setAgentAttachments((prev) => {
      if (prev.some((a) => a.scene_id === s.id)) return prev
      return [
        ...prev,
        {
          kind: 'scene',
          scene_id: s.id,
          name: s.name,
          path: s.reference_path || null,
        },
      ]
    })
    goTab('agent')
    notify(`Added scene ${s.name} to agent chat.`)
  }

  const generateShots = async (shotIds?: string[], continueChain = true) => {
    if (!project) return
    setBusy(true)
    try {
      const chain = continueChain && (project.continue_from_previous ?? true)
      const p = await api.generate(project.id, shotIds, 'video', undefined, {
        continue_from_previous: chain,
        inject_continuity: true,
      })
      setProject(p)
      goTab(chain ? 'generate' : 'sampling')
      notify(
        chain
          ? 'Continuing sequence — each shot starts from the last frame of the previous take.'
          : health?.gpu
            ? 'Queued on the built-in engine — check Generate for progress.'
            : 'Queued on built-in preview engine. Install ROCm PyTorch + models for real gen.',
      )
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const generateRefs = async (kind: 'character_still' | 'scene_still') => {
    if (!project) return
    setBusy(true)
    try {
      const p = await api.generate(project.id, undefined, kind)
      setProject(p)
      notify('Reference stills updated.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  if (!project) {
    if (homeView === 'learning') {
      return (
        <div className="app-shell">
          <header className="studio-top">
            <div className="studio-title">
              <Brand />
              <span>Learning</span>
            </div>
            <div className="studio-actions">
              <button className="btn ghost" type="button" onClick={() => setHomeView('home')}>
                Back
              </button>
              <button className="btn acid" type="button" onClick={() => setShowNew(true)}>
                Start a project
              </button>
            </div>
          </header>
          <main className="studio-main">
            <LearningTab
              onGo={(id) => {
                if (id === 'sources') setHomeView('sources')
                else notify('Open a project to jump to that studio tab.')
              }}
            />
          </main>
          {toast && <div className="toast">{toast}</div>}
          {showNew && (
            <div className="modal-backdrop" onClick={() => setShowNew(false)}>
              <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={createProject}>
                <h2>New project</h2>
                <div className="field">
                  <label htmlFor="title-learn">Title</label>
                  <input id="title-learn" value={title} onChange={(e) => setTitle(e.target.value)} required />
                </div>
                <div className="cta-row">
                  <button className="btn ghost" type="button" onClick={() => setShowNew(false)}>
                    Cancel
                  </button>
                  <button className="btn acid" type="submit" disabled={busy}>
                    Create
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      )
    }
    if (homeView === 'sources') {
      return (
        <div className="app-shell">
          <header className="studio-top">
            <div className="studio-title">
              <Brand />
              <span>My links</span>
            </div>
            <div className="studio-actions">
              <button className="btn ghost" type="button" onClick={() => setHomeView('home')}>
                Back
              </button>
              <button className="btn secondary" type="button" onClick={() => setHomeView('learning')}>
                Learning
              </button>
            </div>
          </header>
          <main className="studio-main">
            <SourcesTab notify={notify} />
          </main>
          {toast && <div className="toast">{toast}</div>}
        </div>
      )
    }

    return (
      <div className="app-shell home">
        <div className="home-top">
          <Brand />
          <div className="status-pills">
            <span
              className={`pill ${health?.agent_reachable ? 'on' : 'off'}`}
              title={health?.agent_detail || ''}
            >
              {health?.agent_reachable
                ? `${health?.agent_label || 'Agent'} · connected`
                : `${health?.agent_label || health?.agent_provider || 'Ollama'} · offline`}
            </span>
            <span className={`pill ${health?.gpu ? 'on' : 'off'}`}>
              Engine {health?.gpu ? health.device_name : 'preview (no GPU torch)'}
            </span>
            <span className="pill">
              Preset {settings?.preset_id || 'amd-low-vram'}
            </span>
          </div>
        </div>

        <section className="home-hero">
          <form
            className="panel quick-start"
            onSubmit={(e) => {
              e.preventDefault()
              void quickStart()
            }}
          >
            <h1>What do you want to make?</h1>
            <textarea
              rows={3}
              value={quickPrompt}
              onChange={(e) => setQuickPrompt(e.target.value)}
              placeholder="A rainy neon street at night, a courier in a silver jacket, slow tracking shot…"
              aria-label="Describe your shot"
            />
            <div className="quick-row">
              <div className="seg" role="radiogroup" aria-label="Video or image">
                {(
                  [
                    ['t2v', 'Video'],
                    ['t2i', 'Image'],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="radio"
                    aria-checked={quickMode === id}
                    className={quickMode === id ? 'active' : ''}
                    onClick={() => setQuickMode(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <select
                className="quick-target"
                value={quickTarget}
                onChange={(e) => setQuickTarget(e.target.value)}
                aria-label="Project to use"
              >
                {projects.length > 0 && <option value="">Into latest: {projects[0].title}</option>}
                <option value="__new__">Into a new project</option>
                {projects.slice(1, 12).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} · {formatAgo(p.updated_at)}
                  </option>
                ))}
              </select>
              <button className="btn acid" type="submit" disabled={busy || !quickPrompt.trim()}>
                Open in Make →
              </button>
            </div>
            <div className="quick-links">
              <button type="button" className="link-btn" onClick={() => setShowNew(true)}>
                Start a planned project (Agent, story, shots)
              </button>
              <span aria-hidden>·</span>
              <button type="button" className="link-btn" onClick={() => setHomeView('learning')}>
                Learning guide
              </button>
              <span aria-hidden>·</span>
              <button type="button" className="link-btn" onClick={() => setHomeView('sources')}>
                My GitHub / HF
              </button>
            </div>
          </form>

          {projects.length > 0 &&
            (() => {
              const latest = projects[0]
              const take = latestTakeFor(latest.id)
              return (
                <div className="panel continue-card">
                  <div className="section-label">Continue</div>
                  <div className="continue-media">
                    {take && isVideoPath(take.media_path) ? (
                      <video src={mediaUrl(take.media_path)} autoPlay muted loop playsInline />
                    ) : take?.media_path && !isAudioPath(take.media_path) ? (
                      <img src={mediaUrl(take.media_path)} alt="" />
                    ) : (
                      <span className="muted">No takes yet</span>
                    )}
                  </div>
                  <strong className="continue-title">{latest.title}</strong>
                  <span className="muted tiny">
                    {plural(latest.shot_count, 'shot')} · {plural(takeCountFor(latest.id), 'take')} ·{' '}
                    {formatAgo(latest.updated_at)}
                  </span>
                  <div className="cta-row">
                    <button className="btn acid" type="button" disabled={busy} onClick={() => openProject(latest.id)}>
                      Open
                    </button>
                    <button
                      className="btn ghost"
                      type="button"
                      disabled={busy}
                      onClick={() => openProject(latest.id, 'generate')}
                    >
                      Make a shot
                    </button>
                  </div>
                </div>
              )
            })()}
        </section>

        {health && (
          <section className={`amd-coach slim ${health.will_preview ? 'preview' : 'ready'}`}>
            <div>
              <strong>{health.first_run_headline || health.device_name}</strong>
              <span className="muted tiny">
                {' '}
                {health.will_preview
                  ? '· Preview mode until ROCm PyTorch + Diffusers are ready'
                  : '· Engine ready'}
                {health.rocm ? ' · ROCm' : ''} · Faces, refs and projects stay on this machine — no cloud.
              </span>
            </div>
            {health.suggested_preset && health.suggested_preset !== settings?.preset_id && (
              <button
                className="btn secondary"
                type="button"
                disabled={busy}
                onClick={async () => {
                  if (!settings) return
                  setBusy(true)
                  try {
                    const s = await api.putSettings({
                      ...settings,
                      preset_id: health.suggested_preset!,
                    })
                    setSettings(s)
                    notify(`Preset → ${health.suggested_preset}`)
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                Use {health.suggested_preset}
              </button>
            )}
          </section>
        )}

        {homeTakes.length > 0 && (
          <section className="home-projects">
            <div className="section-label">Recent takes</div>
            <div className="take-strip">
              {homeTakes.slice(0, 10).map((j) => (
                <button
                  key={j.id}
                  type="button"
                  className="take-chip"
                  title={j.prompt}
                  disabled={busy || !j.project_id}
                  onClick={() => j.project_id && openProject(j.project_id, 'generate')}
                >
                  {isVideoPath(j.media_path) ? (
                    <video src={`${mediaUrl(j.media_path)}#t=0.5`} muted preload="metadata" playsInline />
                  ) : (
                    <img src={mediaUrl(j.thumb_path || j.media_path)} alt="" />
                  )}
                  <span className="take-chip-label">{j.prompt || j.mode.toUpperCase()}</span>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="home-projects" id="projects">
          <div className="home-projects-head">
            <div className="section-label">Your projects</div>
            <button className="btn ghost tiny" type="button" onClick={() => setShowNew(true)}>
              + New project
            </button>
          </div>
          {projects.length === 0 ? (
            <div className="empty">No projects yet. Type an idea above, or start a planned project.</div>
          ) : (
            (() => {
              const used = projects.filter((p) => p.shot_count > 0 || takeCountFor(p.id) > 0)
              const empty = projects.filter((p) => !(p.shot_count > 0 || takeCountFor(p.id) > 0))
              const shown = showEmptyProjects ? [...used, ...empty] : used
              return (
                <>
                  {shown.length > 0 && (
                    <div className="project-grid">
                      {shown.map((p) => {
                        const take = latestTakeFor(p.id)
                        return (
                          <button
                            key={p.id}
                            className="project-tile with-thumb"
                            type="button"
                            disabled={busy}
                            onClick={() => openProject(p.id)}
                          >
                            <div className="project-thumb">
                              {take && isVideoPath(take.media_path) ? (
                                <video src={`${mediaUrl(take.media_path)}#t=0.5`} muted preload="metadata" playsInline />
                              ) : take?.media_path && !isAudioPath(take.media_path) ? (
                                <img src={mediaUrl(take.thumb_path || take.media_path)} alt="" />
                              ) : (
                                <span aria-hidden>✦</span>
                              )}
                            </div>
                            <h3>{p.title}</h3>
                            <p className="tiny muted">
                              {plural(p.shot_count, 'shot')} · {plural(takeCountFor(p.id), 'take')} ·{' '}
                              {formatAgo(p.updated_at)}
                            </p>
                          </button>
                        )
                      })}
                    </div>
                  )}
                  {empty.length > 0 && (
                    <button
                      className="link-btn show-empty"
                      type="button"
                      onClick={() => setShowEmptyProjects((v) => !v)}
                    >
                      {showEmptyProjects
                        ? 'Hide empty projects'
                        : `Show ${empty.length} empty project${empty.length === 1 ? '' : 's'}`}
                    </button>
                  )}
                </>
              )
            })()
          )}
        </section>

        {showNew && (
          <div className="modal-backdrop" onClick={() => setShowNew(false)}>
            <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={createProject}>
              <h2>New project</h2>
              <p>Pick a mode. You can change everything later.</p>
              <div className="field">
                <label htmlFor="title">Title</label>
                <input id="title" value={title} onChange={(e) => setTitle(e.target.value)} required />
              </div>
              <div className="field">
                <label htmlFor="mode">Mode</label>
                <select id="mode" value={mode} onChange={(e) => setMode(e.target.value as Mode)}>
                  {MODES.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="cta-row">
                <button className="btn acid" type="submit" disabled={busy}>
                  Create
                </button>
                <button className="btn ghost" type="button" onClick={() => setShowNew(false)}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}
        {showWizard && (
          <FirstRunWizard
            health={health}
            settings={settings}
            setSettings={(s) => setSettings(s)}
            notify={notify}
            onDone={() => setShowWizard(false)}
            onStartProject={(frameSizeId) => {
              setNewFrameSize(frameSizeId)
              setShowNew(true)
            }}
          />
        )}
        {toast && <div className="toast">{toast}</div>}
      </div>
    )
  }

  const activeLabel =
    NAV_GROUPS.flatMap((g) => g.items).find((i) => i.id === tab)?.label || tab

  return (
    <div className={`app-shell studio ${navOpen ? 'nav-open' : 'nav-collapsed'}`}>
      <header className="studio-top">
        <div className="studio-title">
          <button
            className="btn ghost nav-toggle"
            type="button"
            aria-label={navOpen ? 'Hide menu' : 'Show menu'}
            onClick={() => setNavOpen((v) => !v)}
          >
            {navOpen ? '☰ Hide' : '☰ Menu'}
          </button>
          <Brand />
          <strong>{project.title}</strong>
          <span>
            {activeLabel} · {project.mode.replace('_', ' ')} · {project.shots.length} shots
          </span>
        </div>
        <div className="studio-actions">
          <button className="btn ghost" type="button" onClick={() => setProject(null)}>
            Projects
          </button>
          <button className="btn secondary" type="button" disabled={busy} onClick={save}>
            Save
          </button>
          <button
            className="btn acid"
            type="button"
            disabled={busy || project.shots.length === 0}
            onClick={() => generateShots(undefined, project.continue_from_previous ?? true)}
            title={
              project.continue_from_previous !== false
                ? 'Chain: each shot continues from the last frame of the previous video'
                : 'Generate shots independently'
            }
          >
            {project.continue_from_previous !== false
              ? 'Continue all shots'
              : 'Generate all shots'}
          </button>
        </div>
      </header>

      <div className="studio-layout">
        <aside className={`side-nav ${navOpen ? 'open' : 'closed'}`} aria-label="Studio sections">
          <div className="side-nav-inner">
            <div className="side-nav-head">Studio</div>
            <p className="nav-blurb">One section at a time. Everything is still here.</p>
            {NAV_GROUPS.map((group) => {
              const open = !!openGroups[group.id]
              return (
                <div className="nav-group" key={group.id}>
                  <button
                    type="button"
                    className={`nav-group-btn ${open ? 'open' : ''}`}
                    onClick={() => setOpenGroups(open ? {} : { [group.id]: true })}
                    aria-expanded={open}
                  >
                    <span>
                      {group.label}
                      <small className="nav-group-blurb">{group.blurb}</small>
                    </span>
                    <span className="chev">{open ? '▾' : '▸'}</span>
                  </button>
                  {open && (
                    <div className="nav-sublist">
                      {group.items.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className={`nav-item ${tab === item.id ? 'active' : ''}`}
                          onClick={() => goTab(item.id)}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </aside>

        <main className="studio-body">
        {tab === 'inspiration' && (
          <InspirationTab
            busy={busy}
            onTry={useInspiration}
          />
        )}
        {tab === 'agent' && (
          <AgentTab
            project={project}
            text={agentText}
            setText={setAgentText}
            attachments={agentAttachments}
            setAttachments={setAgentAttachments}
            replaceShots={replaceShots}
            setReplaceShots={setReplaceShots}
            busy={busy}
            onSend={runAgent}
            notify={notify}
          />
        )}
        {tab === 'profiles' && (
          <ProfilesTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
          />
        )}
        {tab === 'time' && (
          <TimeStyleTab project={project} setProject={setProject} notify={notify} />
        )}
        {tab === 'shots' && (
          <ShotsTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
            onGenerate={(id) => generateShots([id])}
          />
        )}
        {tab === 'storyboard' && (
          <StoryboardTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
            onGenerate={generateShots}
          />
        )}
        {tab === 'characters' && (
          <CharactersTab
            project={project}
            setProject={setProject}
            busy={busy}
            onGenerateRefs={generateRefs}
            notify={notify}
            setBusy={setBusy}
            onAddCharToAgent={attachCharacterToAgent}
            onAddSceneToAgent={attachSceneToAgent}
          />
        )}
        {tab === 'creator' && (
          <CreatorTab
            project={project}
            setProject={setProject}
            notify={notify}
            health={health}
          />
        )}
        {tab === 'generate' && (
          <GenerateTab
            project={project}
            setProject={setProject}
            notify={notify}
            health={health}
            seed={inspirationSeed}
            onSeedConsumed={() => setInspirationSeed(null)}
            onOpenSpeedGuide={() => {
              try {
                window.sessionStorage.setItem('studionels_learn_section', 'speed')
              } catch {
                /* ignore */
              }
              goTab('learning')
            }}
          />
        )}
        {tab === 'audio' && (
          <AudioTab project={project} setProject={setProject} notify={notify} health={health} />
        )}
        {tab === 'upsample' && (
          <UpsampleTab project={project} notify={notify} />
        )}
        {(tab === 'models' || tab === 'templates') && (
          <ModelsTab notify={notify} focusTemplates={tab === 'templates'} />
        )}
        {tab === 'learning' && <LearningTab onGo={goTab} />}
        {tab === 'sources' && <SourcesTab notify={notify} />}
        {tab === 'addons' && <AddonsTab notify={notify} />}
        {tab === 'info' && <InfoTab />}
        {tab === 'continuity' && (
          <ContinuityTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
          />
        )}
        {tab === 'rehearsal' && (
          <RehearsalTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
          />
        )}
        {tab === 'sampling' && (
          <SamplingTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
          />
        )}
        {tab === 'filmnight' && (
          <FilmNightTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
            onOpenDirector={() => goTab('director')}
            onMakeTest={() => {
              goTab('inspiration')
              notify('Pick a card. It fills Video & image — press Generate there.')
            }}
            onAddShot={() => {
              void api
                .addShot(project.id, {
                  title: 'Shot 1',
                  action: '',
                  camera: 'medium',
                  duration_sec: 2,
                })
                .then((p) => {
                  setProject(p)
                  goTab('shots')
                  notify('First shot added. Write what happens, then come back to Film night.')
                })
                .catch((err) => notify(String((err as Error).message || err)))
            }}
          />
        )}
        {tab === 'director' && (
          <DirectorStudio
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
          />
        )}
        {tab === 'settings' && settings && (
          <SettingsTab
            project={project}
            setProject={setProject}
            settings={settings}
            setSettings={setSettings}
            presets={presets}
            health={health}
            notify={notify}
            onHealthRefresh={() => {
              void api.health().then(setHealth).catch(() => undefined)
            }}
          />
        )}
      </main>
      </div>
      {/* The Make page has its own stage + Recent list; the dock would duplicate it. */}
      {tab !== 'generate' && (
      <GenerationDock
        projectId={project.id}
        health={health}
        setProject={setProject}
        notify={notify}
        onOpenGenerate={() => goTab('generate')}
        onOpenSampling={() => goTab('sampling')}
        onRestoreWorkflow={() => {
          try {
            window.sessionStorage.setItem('studionels_restore_workflow', '1')
          } catch {
            /* ignore */
          }
          goTab('generate')
        }}
      />
      )}
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

const GEN_DOCK_MIN_KEY = 'studionels_gen_dock_minimized'

function GenerationDock({
  projectId,
  health,
  setProject,
  notify,
  onOpenGenerate,
  onOpenSampling,
  onRestoreWorkflow,
}: {
  projectId: string
  health: Health | null
  setProject: (p: Project) => void
  notify: (m: string) => void
  onOpenGenerate: () => void
  onOpenSampling: () => void
  onRestoreWorkflow: () => void
}) {
  const [jobs, setJobs] = useState<EngineJob[]>([])
  const [downloads, setDownloads] = useState<EngineModel[]>([])
  const [warm, setWarm] = useState<EngineWarmStatus | null>(null)
  const [minimized, setMinimized] = useState(() => {
    try {
      return window.localStorage.getItem(GEN_DOCK_MIN_KEY) === '1'
    } catch {
      return false
    }
  })
  const [stopping, setStopping] = useState(false)
  const prevActive = useRef(0)
  const userMinimized = useRef(minimized)
  const hasLive =
    jobs.some((j) => j.status === 'queued' || j.status === 'running') ||
    downloads.some((m) => m.download_status === 'downloading' || m.download_status === 'stalled') ||
    Boolean(warm?.preloading)
  const nowMs = useNowMs(hasLive)
  const warmReadyLabel = warm?.cached?.[0] || null
  const warmBusy = Boolean(warm?.preloading)

  const setMinimizedPref = (next: boolean) => {
    userMinimized.current = next
    setMinimized(next)
    try {
      window.localStorage.setItem(GEN_DOCK_MIN_KEY, next ? '1' : '0')
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    let cancelled = false
    const tick = async () => {
      try {
        const [list, pack, warmPack] = await Promise.all([
          api.engineJobs(),
          api.engineModels().catch(() => null),
          api.engineWarm().catch(() => null),
        ])
        if (cancelled) return
        setJobs(list.slice(0, 12))
        if (warmPack) setWarm(warmPack)
        const dls = (pack?.models || []).filter(
          (m) =>
            m.download_status === 'downloading' ||
            m.download_status === 'stalled' ||
            m.download_status === 'failed' ||
            m.download_status === 'cancelled',
        )
        setDownloads(dls)
        const active = list.filter((j) => j.status === 'queued' || j.status === 'running').length
        const dlActive = dls.filter((m) => m.download_status === 'downloading').length
        const doneNow = list.filter(
          (j) => j.status === 'done' || j.status === 'failed' || j.status === 'cancelled',
        ).length
        if (prevActive.current > 0 && active === 0 && doneNow > 0) {
          const p = await api.getProject(projectId)
          if (!cancelled) {
            setProject(p)
            const stopped = list.some((j) => j.status === 'cancelled')
            notify(
              stopped
                ? 'Stopped — prompts/settings kept. Restore workflow in Generate.'
                : health?.will_preview
                  ? `Jobs finished (preview mode). Check Sampling — ${p.takes.length} take(s).`
                  : `Jobs finished — ${p.takes.length} take(s). Open Sampling or Director.`,
            )
          }
        }
        // Only auto-expand when a new job/download starts AND the user did not minimize.
        if (
          (active > prevActive.current || dlActive > 0) &&
          !userMinimized.current
        ) {
          setMinimized(false)
        }
        prevActive.current = active
      } catch {
        /* api down */
      }
    }
    void tick()
    const t = window.setInterval(() => void tick(), 2500)
    return () => {
      cancelled = true
      window.clearInterval(t)
    }
  }, [projectId, setProject, notify, health?.will_preview])

  const active = jobs.filter((j) => j.status === 'queued' || j.status === 'running')
  const recent = jobs.slice(0, 6)
  const hasRestorable = jobs.some(
    (j) => j.workflow && (j.status === 'cancelled' || j.status === 'failed'),
  )
  const topDl = downloads.find((m) => m.download_status === 'downloading') || downloads[0]
  const topJob = active[0] || recent[0]
  const topAct = topJob ? describeJobActivity(topJob, nowMs) : null
  const lastFailed = !active.length && topAct?.tone === 'fail'
  const topProgress = topDl
    ? Math.round((topDl.download_progress || 0) * 100)
    : active.length
      ? Math.round(Math.max(...active.map((j) => j.progress || 0)) * 100)
      : recent[0]
        ? Math.round((recent[0].progress || 0) * 100)
        : 0
  if (
    recent.length === 0 &&
    downloads.length === 0 &&
    !health?.will_preview &&
    !warmReadyLabel &&
    !warmBusy
  ) {
    return null
  }

  if (minimized) {
    return (
      <div className="gen-dock gen-dock-mini" role="status" aria-live="polite">
        <button
          type="button"
          className="gen-dock-mini-btn"
          onClick={() => setMinimizedPref(false)}
          title="Expand generation box"
        >
          <span
            className="gen-dock-mini-dot"
            data-active={
              active.length > 0 ||
              downloads.some((d) => d.download_status === 'downloading') ||
              warmBusy
                ? '1'
                : '0'
            }
          />
          <span className="gen-dock-mini-label">
            {topDl && topDl.download_status === 'downloading'
              ? `Download · ${topProgress}%`
              : active.length > 0
                ? `${topAct?.phase || 'Generating'} · ${topProgress}%${
                    topAct?.timerLabel ? ` · ${topAct.timerLabel}` : ''
                  }`
                : warmBusy
                  ? warm?.message || 'Preloading model…'
                  : warmReadyLabel
                    ? `Ready: ${warmReadyLabel}`
                    : lastFailed
                      ? `Failed · ${(topAct?.detail || 'see the job').slice(0, 80)}`
                      : topAct
                        ? topAct.phase
                        : 'Engine'}
          </span>
          {active.length > 0 ? (
            <span className="gen-dock-mini-bar" aria-hidden>
              <span style={{ width: `${topProgress}%` }} />
            </span>
          ) : null}
          <span className="gen-dock-mini-expand">Expand</span>
        </button>
        {active.length > 0 ? (
          <button
            type="button"
            className="gen-dock-mini-stop"
            disabled={stopping}
            title="Stop all jobs"
            onClick={async () => {
              setStopping(true)
              try {
                const r = await api.engineCancelAll()
                notify(`Stopped ${r.stopped} job(s) — workflow kept.`)
                setJobs(await api.engineJobs())
              } catch (err) {
                notify(String((err as Error).message || err))
              } finally {
                setStopping(false)
              }
            }}
          >
            Stop
          </button>
        ) : null}
      </div>
    )
  }

  return (
    <div className="gen-dock open">
      <div className="gen-dock-head">
        <button
          type="button"
          className="gen-dock-title"
          onClick={() => setMinimizedPref(true)}
          title="Minimize generation box"
        >
          <strong>
            {topDl && topDl.download_status === 'downloading'
              ? `Downloading model · ${topProgress}%`
              : active.length > 0
                ? `${topAct?.phase || 'Generating'} · ${active.length} active`
                : warmBusy
                  ? 'Preloading model'
                  : lastFailed
                    ? 'Last job failed'
                    : topAct?.phase || (recent.length || downloads.length ? 'Generation' : 'Engine')}
          </strong>
          <span className="muted tiny">
            {topDl && topDl.download_status === 'downloading'
              ? topDl.download_message || topDl.label
              : topAct && active.length > 0
                ? `${topAct.timerLabel ? `${topAct.timerLabel} · ` : ''}${topAct.detail}`
                : lastFailed
                  ? (topAct?.detail || 'The job stopped. The reason is on the line below.').slice(0, 220)
                : warmBusy
                  ? warm?.message || 'Loading into RAM/VRAM…'
                  : warmReadyLabel
                    ? `Ready: ${warmReadyLabel}`
                    : health?.will_preview
                      ? 'Preview mode (placeholders until ROCm PyTorch)'
                      : health?.device_name || 'built-in'}
          </span>
        </button>
        <button
          type="button"
          className="btn ghost tiny gen-dock-min-btn"
          onClick={() => setMinimizedPref(true)}
          title="Minimize"
        >
          Minimize
        </button>
      </div>
      <div className="gen-dock-body">
        {warmBusy ? (
          <p className="job-phase tone-load tiny" style={{ margin: '0 0 8px' }}>
            {warm?.message || 'Preloading model into RAM/VRAM…'}
          </p>
        ) : warmReadyLabel ? (
          <p className="job-phase tone-done tiny" style={{ margin: '0 0 8px' }}>
            Ready: {warmReadyLabel}
          </p>
        ) : null}
        {health?.will_preview ? (
          <p className="muted tiny">
            Jobs still run — you get preview clips (color bars + prompt text), not full AI video
            yet. Takes show up in Sampling when each job finishes.
          </p>
        ) : null}
        {downloads.length > 0 ? (
          <div className="gen-dock-list" style={{ marginBottom: 10 }}>
            {downloads.map((m) => (
              <div className="gen-dock-row" key={`dl-${m.id}`}>
                <ModelDownloadProgress
                  model={m}
                  compact
                  onCancel={async () => {
                    try {
                      await api.engineModelCancel(m.id)
                      notify('Download cancelled')
                      const pack = await api.engineModels()
                      setDownloads(
                        pack.models.filter(
                          (x) =>
                            x.download_status === 'downloading' ||
                            x.download_status === 'stalled' ||
                            x.download_status === 'failed' ||
                            x.download_status === 'cancelled',
                        ),
                      )
                    } catch (err) {
                      notify(String((err as Error).message || err))
                    }
                  }}
                  onRetry={async () => {
                    try {
                      await api.engineModelDownload(m.id, true)
                      notify(`Downloading ${m.label}…`)
                    } catch (err) {
                      notify(String((err as Error).message || err))
                    }
                  }}
                />
              </div>
            ))}
          </div>
        ) : null}
        {recent.length === 0 && downloads.length === 0 ? (
          <p className="muted tiny">No jobs yet. Film night / Generate will show progress here.</p>
        ) : recent.length === 0 ? null : (
          <div className="gen-dock-list">
            {recent.map((job) => {
              const act = describeJobActivity(job, nowMs)
              return (
              <div className="gen-dock-row" key={job.id}>
                <div className="gen-dock-meta">
                  <span className={`job-phase tone-${act.tone}`}>
                    {act.phase}
                    {job.preview ? ' · preview' : ''}
                  </span>
                  {act.timerLabel ? (
                    <div className="gen-dock-timer" title="Elapsed / ETA">
                      {act.timerLabel}
                      {act.stepLabel ? ` · ${act.stepLabel}` : ''}
                    </div>
                  ) : null}
                  <div className="gen-dock-meta-actions">
                    <span className="muted tiny">{Math.round((job.progress || 0) * 100)}%</span>
                    <button
                      type="button"
                      className="gen-dock-x"
                      title="Remove from queue"
                      aria-label="Remove from queue"
                      disabled={stopping}
                      onClick={async () => {
                        setStopping(true)
                        try {
                          await api.engineDismissJob(job.id)
                          setJobs(await api.engineJobs())
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        } finally {
                          setStopping(false)
                        }
                      }}
                    >
                      ×
                    </button>
                  </div>
                </div>
                <div className="muted tiny truncate">
                  {job.mode.toUpperCase()} · {job.model_label} · {job.status}
                </div>
                <GenerationStageBar job={job} />
                <JobMedia job={job} compact />
                {job.error ? <div className="fit-warn tiny">{job.error.slice(0, 160)}</div> : null}
                {(job.status === 'queued' || job.status === 'running') && (
                  <button
                    className="btn ghost tiny"
                    type="button"
                    disabled={stopping}
                    onClick={async () => {
                      setStopping(true)
                      try {
                        await api.engineCancelJob(job.id)
                        notify('Stopped — your prompt/settings are saved.')
                        setJobs(await api.engineJobs())
                      } catch (err) {
                        notify(String((err as Error).message || err))
                      } finally {
                        setStopping(false)
                      }
                    }}
                  >
                    Stop
                  </button>
                )}
              </div>
              )
            })}
          </div>
        )}
        <div className="cta-row" style={{ marginTop: 8, flexWrap: 'wrap', gap: 6 }}>
          {active.length > 0 && (
            <button
              className="btn secondary tiny"
              type="button"
              disabled={stopping}
              onClick={async () => {
                setStopping(true)
                try {
                  const r = await api.engineCancelAll()
                  notify(`Stopped ${r.stopped} job(s) — workflow kept.`)
                  setJobs(await api.engineJobs())
                } catch (err) {
                  notify(String((err as Error).message || err))
                } finally {
                  setStopping(false)
                }
              }}
            >
              Stop all
            </button>
          )}
          {hasRestorable && (
            <button className="btn acid tiny" type="button" onClick={onRestoreWorkflow}>
              Restore workflow
            </button>
          )}
          <button className="btn ghost tiny" type="button" onClick={onOpenGenerate}>
            Video & image
          </button>
          <button className="btn ghost tiny" type="button" onClick={onOpenSampling}>
            Takes
          </button>
        </div>
      </div>
    </div>
  )
}

function AgentTab({
  project,
  text,
  setText,
  attachments,
  setAttachments,
  replaceShots,
  setReplaceShots,
  busy,
  onSend,
  notify,
}: {
  project: Project
  text: string
  setText: (v: string) => void
  attachments: AgentAttachment[]
  setAttachments: (a: AgentAttachment[] | ((prev: AgentAttachment[]) => AgentAttachment[])) => void
  replaceShots: boolean
  setReplaceShots: (v: boolean) => void
  busy: boolean
  onSend: () => void
  notify: (m: string) => void
}) {
  const [pickerOpen, setPickerOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const canSend = Boolean(text.trim() || attachments.length)

  const removeAtt = (idx: number) => {
    setAttachments(attachments.filter((_, i) => i !== idx))
  }

  const addCharacter = (c: CharacterProfile) => {
    setAttachments((prev) => {
      if (prev.some((a) => a.character_id === c.id)) return prev
      return [
        ...prev,
        {
          kind: 'character',
          character_id: c.id,
          name: c.name,
          path: c.reference_path || null,
        },
      ]
    })
    setPickerOpen(false)
  }

  const addScene = (s: SceneProfile) => {
    setAttachments((prev) => {
      if (prev.some((a) => a.scene_id === s.id)) return prev
      return [
        ...prev,
        {
          kind: 'scene',
          scene_id: s.id,
          name: s.name,
          path: s.reference_path || null,
        },
      ]
    })
    setPickerOpen(false)
  }

  const onUploadFiles = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    try {
      const next: AgentAttachment[] = []
      for (const file of Array.from(files)) {
        const up = await api.engineUpload(file, file.type.startsWith('video/') ? 'reference' : 'image')
        const isImage = file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif)$/i.test(file.name)
        next.push({
          kind: isImage ? 'image' : 'file',
          path: up.path,
          name: file.name.replace(/\.[^.]+$/, '') || file.name,
          mime: file.type || '',
        })
      }
      setAttachments((prev) => [...prev, ...next])
      notify(next.length === 1 ? 'Reference attached.' : `${next.length} references attached.`)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="chat">
      <p className="hint">
        Chat with your director — attach Characters-tab people, scenes, or upload reference images.
        Example: attach Mira’s face ref, then “rainy neon chase for TikTok”.
      </p>
      <div className="chat-log">
        {project.agent_messages.length === 0 ? (
          <div className="bubble assistant">
            Hey — I’m your StudioNels director. Attach a character or image for face lock, describe a
            film idea, or say “help”. Refs from the Characters tab stay locked into the shot list.
          </div>
        ) : null}
        {project.agent_messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.content}
            {m.attachments && m.attachments.length > 0 ? (
              <div className="att-row in-bubble">
                {m.attachments.map((a, i) => (
                  <span key={`${a.character_id || a.path || i}`} className="att-chip">
                    {mediaUrl(a.path) && a.kind !== 'file' ? (
                      <img src={mediaUrl(a.path)!} alt="" />
                    ) : null}
                    <span>
                      {a.kind === 'character'
                        ? a.name || 'Character'
                        : a.kind === 'scene'
                          ? a.name || 'Scene'
                          : a.name || a.kind}
                    </span>
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <div className="chat-compose">
        {attachments.length > 0 ? (
          <div className="att-row">
            {attachments.map((a, i) => (
              <span key={`${a.character_id || a.scene_id || a.path || i}`} className="att-chip">
                {mediaUrl(a.path) && a.kind !== 'file' ? (
                  <img src={mediaUrl(a.path)!} alt="" />
                ) : (
                  <span className="att-icon" aria-hidden>
                    {a.kind === 'character' ? '◆' : a.kind === 'scene' ? '◇' : '📎'}
                  </span>
                )}
                <span>
                  {a.name || a.kind}
                  {!a.path && a.kind === 'character' ? ' (no image yet)' : ''}
                </span>
                <button type="button" className="att-x" onClick={() => removeAtt(i)} aria-label="Remove">
                  ×
                </button>
              </span>
            ))}
          </div>
        ) : null}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Talk to the director… attach refs below"
          onKeyDown={(e) => {
            // Enter sends; Shift+Enter = new line (stay on Agent tab)
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (canSend && !busy) onSend()
            }
          }}
        />
        <div className="compose-attach-bar">
          <input
            ref={fileRef}
            type="file"
            accept="image/*,video/*,.png,.jpg,.jpeg,.webp,.gif,.mp4,.webm"
            multiple
            hidden
            onChange={(e) => void onUploadFiles(e.target.files)}
          />
          <button
            className="btn ghost"
            type="button"
            disabled={busy || uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? 'Uploading…' : 'Upload image / file'}
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={busy}
            onClick={() => setPickerOpen((v) => !v)}
          >
            From Characters
          </button>
          <label className="muted">
            <input
              type="checkbox"
              checked={replaceShots}
              onChange={(e) => setReplaceShots(e.target.checked)}
            />{' '}
            Prefer replacing shot list on big ideas
          </label>
          <span className="muted tiny">Enter to send · Shift+Enter for line break</span>
          <button
            className="btn acid"
            type="button"
            disabled={busy || !canSend}
            onClick={onSend}
          >
            {busy ? 'Thinking…' : 'Send'}
          </button>
        </div>
        {pickerOpen ? (
          <div className="agent-ref-picker">
            <div className="agent-ref-col">
              <strong>Characters</strong>
              {project.characters.length === 0 ? (
                <p className="muted tiny">None yet — add some on Characters, or upload an image here.</p>
              ) : (
                project.characters.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className="agent-ref-item"
                    onClick={() => addCharacter(c)}
                  >
                    {mediaUrl(c.reference_path) ? (
                      <img src={mediaUrl(c.reference_path)!} alt="" />
                    ) : (
                      <span className="att-icon">◆</span>
                    )}
                    <span>
                      <em>{c.name}</em>
                      <small>{c.look || c.role || (c.reference_path ? 'Has ref' : 'No image')}</small>
                    </span>
                  </button>
                ))
              )}
            </div>
            <div className="agent-ref-col">
              <strong>Scenes</strong>
              {project.scenes.length === 0 ? (
                <p className="muted tiny">No scenes yet.</p>
              ) : (
                project.scenes.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className="agent-ref-item"
                    onClick={() => addScene(s)}
                  >
                    {mediaUrl(s.reference_path) ? (
                      <img src={mediaUrl(s.reference_path)!} alt="" />
                    ) : (
                      <span className="att-icon">◇</span>
                    )}
                    <span>
                      <em>{s.name}</em>
                      <small>{s.location || s.mood || 'Scene'}</small>
                    </span>
                  </button>
                ))
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function ProfilesTab({
  project,
  setProject,
  busy,
  setBusy,
  notify,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
}) {
  const [char, setChar] = useState({
    name: '',
    role: '',
    look: '',
    personality: '',
    voice_notes: '',
  })
  const [scene, setScene] = useState({
    name: '',
    location: '',
    time_of_day: '',
    mood: '',
    visual_notes: '',
  })

  const addChar = async (e: FormEvent) => {
    e.preventDefault()
    if (!char.name.trim()) return
    setBusy(true)
    try {
      const p = await api.addCharacter(project.id, { ...char, tags: [] })
      setProject(p)
      setChar({ name: '', role: '', look: '', personality: '', voice_notes: '' })
      notify('Character added.')
    } finally {
      setBusy(false)
    }
  }

  const addScene = async (e: FormEvent) => {
    e.preventDefault()
    if (!scene.name.trim()) return
    setBusy(true)
    try {
      const p = await api.addScene(project.id, { ...scene, tags: [] })
      setProject(p)
      setScene({ name: '', location: '', time_of_day: '', mood: '', visual_notes: '' })
      notify('Scene added.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Profiles are the cast and locations the agent should reuse. Keep them simple — name, look,
        mood. You can generate picture refs later in Characters.
      </p>
      <div className="two-col">
        <div className="panel">
          <h3>Characters</h3>
          <form className="profile-form" onSubmit={addChar}>
            <div className="field">
              <label>Name</label>
              <input value={char.name} onChange={(e) => setChar({ ...char, name: e.target.value })} />
            </div>
            <div className="field">
              <label>Role</label>
              <input value={char.role} onChange={(e) => setChar({ ...char, role: e.target.value })} />
            </div>
            <div className="field">
              <label>Look</label>
              <textarea
                value={char.look}
                onChange={(e) => setChar({ ...char, look: e.target.value })}
                rows={2}
              />
            </div>
            <div className="field">
              <label>Personality</label>
              <textarea
                value={char.personality}
                onChange={(e) => setChar({ ...char, personality: e.target.value })}
                rows={2}
              />
            </div>
            <button className="btn" type="submit" disabled={busy}>
              Add character
            </button>
          </form>
          <div className="profile-list" style={{ marginTop: 16 }}>
            {project.characters.map((c) => (
              <ProfileChar key={c.id} c={c} project={project} setProject={setProject} notify={notify} />
            ))}
            {project.characters.length === 0 && <div className="empty">No characters yet.</div>}
          </div>
        </div>
        <div className="panel">
          <h3>Scenes</h3>
          <form className="profile-form" onSubmit={addScene}>
            <div className="field">
              <label>Name</label>
              <input
                value={scene.name}
                onChange={(e) => setScene({ ...scene, name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Location</label>
              <input
                value={scene.location}
                onChange={(e) => setScene({ ...scene, location: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Time of day</label>
              <input
                value={scene.time_of_day}
                onChange={(e) => setScene({ ...scene, time_of_day: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Mood</label>
              <input
                value={scene.mood}
                onChange={(e) => setScene({ ...scene, mood: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Visual notes</label>
              <textarea
                value={scene.visual_notes}
                onChange={(e) => setScene({ ...scene, visual_notes: e.target.value })}
                rows={2}
              />
            </div>
            <button className="btn" type="submit" disabled={busy}>
              Add scene
            </button>
          </form>
          <div className="profile-list" style={{ marginTop: 16 }}>
            {project.scenes.map((s) => (
              <ProfileScene key={s.id} s={s} project={project} setProject={setProject} notify={notify} />
            ))}
            {project.scenes.length === 0 && <div className="empty">No scenes yet.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}

function ProfileChar({
  c,
  project,
  setProject,
  notify,
}: {
  c: CharacterProfile
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
}) {
  const [draft, setDraft] = useState(c)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => setDraft(c), [c])

  const save = async (next: CharacterProfile = draft) => {
    setSaving(true)
    try {
      const p = await api.updateCharacter(project.id, next)
      setProject(p)
      notify('Character updated.')
      setOpen(false)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setSaving(false)
    }
  }

  const replaceRef = async (file: File) => {
    const up = await api.engineUpload(file)
    const next = { ...draft, reference_path: up.path }
    setDraft(next)
    setSaving(true)
    try {
      await api.updateCharacter(project.id, next)
      const p = await api.refreshIdentityLock(project.id, c.id)
      setProject(p)
      const updated = p.characters.find((x) => x.id === c.id)
      if (updated) setDraft(updated)
      notify('Ref saved · identity lock fingerprinted.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="profile-item">
      <header>
        <strong>{c.name}</strong>
        <div className="inline-actions">
          <button className="btn ghost tiny" type="button" onClick={() => setOpen((v) => !v)}>
            {open ? 'Close' : 'Edit'}
          </button>
          <button
            className="btn ghost tiny"
            type="button"
            onClick={async () => {
              const p = await api.deleteCharacter(project.id, c.id)
              setProject(p)
              notify('Removed character.')
            }}
          >
            Remove
          </button>
        </div>
      </header>
      {mediaUrl(c.reference_path) && (
        <img className="upload-preview" src={mediaUrl(c.reference_path)} alt={c.name} />
      )}
      <div className="muted">{c.role || 'No role'}</div>
      <div className="muted">{c.look || 'No look notes'}</div>
      {open && (
        <div className="profile-form" style={{ marginTop: 10 }}>
          <div className="field">
            <label>Name</label>
            <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </div>
          <div className="field">
            <label>Role</label>
            <input value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value })} />
          </div>
          <div className="field">
            <label>Look / ref notes</label>
            <textarea
              rows={3}
              value={draft.look}
              onChange={(e) => setDraft({ ...draft, look: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Personality</label>
            <textarea
              rows={2}
              value={draft.personality}
              onChange={(e) => setDraft({ ...draft, personality: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Voice notes</label>
            <input
              value={draft.voice_notes}
              onChange={(e) => setDraft({ ...draft, voice_notes: e.target.value })}
            />
          </div>
          <div className="lock-box">
            <label>Character lock</label>
            <textarea
              rows={3}
              value={draft.character_lock || ''}
              onChange={(e) => setDraft({ ...draft, character_lock: e.target.value })}
              placeholder="Identity details to keep the same every generation…"
            />
          </div>
          <div className="field">
            <label>Character ref image</label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => e.target.files?.[0] && replaceRef(e.target.files[0])}
            />
            <div className="inline-actions" style={{ marginTop: 8 }}>
              <button
                className="btn ghost tiny"
                type="button"
                disabled={!draft.reference_path || saving}
                onClick={() => save({ ...draft, reference_path: null })}
              >
                Clear ref
              </button>
              <button
                className="btn secondary tiny"
                type="button"
                disabled={!draft.reference_path || saving}
                onClick={async () => {
                  setSaving(true)
                  try {
                    await save(draft)
                    const p = await api.refreshIdentityLock(project.id, c.id)
                    setProject(p)
                    const updated = p.characters.find((x) => x.id === c.id)
                    if (updated) setDraft(updated)
                    notify(
                      updated?.identity_fingerprint?.length
                        ? 'Identity lock fingerprint saved from ref still.'
                        : 'Could not fingerprint — check the ref image.',
                    )
                  } catch (err) {
                    notify(String((err as Error).message || err))
                  } finally {
                    setSaving(false)
                  }
                }}
              >
                Lock identity from ref
              </button>
            </div>
            {draft.identity_fingerprint?.length ? (
              <div className="muted tiny">Identity fingerprint on — takes scored against this look.</div>
            ) : null}
          </div>
          <button className="btn acid" type="button" disabled={saving} onClick={() => save()}>
            Save character
          </button>
        </div>
      )}
    </div>
  )
}

function ProfileScene({
  s,
  project,
  setProject,
  notify,
}: {
  s: SceneProfile
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
}) {
  const [draft, setDraft] = useState(s)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => setDraft(s), [s])

  const save = async (next: SceneProfile = draft) => {
    setSaving(true)
    try {
      const p = await api.updateScene(project.id, next)
      setProject(p)
      notify('Scene updated.')
      setOpen(false)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setSaving(false)
    }
  }

  const replaceRef = async (file: File) => {
    const up = await api.engineUpload(file)
    const next = { ...draft, reference_path: up.path }
    setDraft(next)
    await save(next)
  }

  return (
    <div className="profile-item">
      <header>
        <strong>{s.name}</strong>
        <div className="inline-actions">
          <button className="btn ghost tiny" type="button" onClick={() => setOpen((v) => !v)}>
            {open ? 'Close' : 'Edit'}
          </button>
          <button
            className="btn ghost tiny"
            type="button"
            onClick={async () => {
              const p = await api.deleteScene(project.id, s.id)
              setProject(p)
              notify('Removed scene.')
            }}
          >
            Remove
          </button>
        </div>
      </header>
      {mediaUrl(s.reference_path) && (
        <img className="upload-preview" src={mediaUrl(s.reference_path)} alt={s.name} />
      )}
      <div className="muted">
        {[s.location, s.time_of_day, s.mood].filter(Boolean).join(' · ') || 'No details'}
      </div>
      {open && (
        <div className="profile-form" style={{ marginTop: 10 }}>
          <div className="field">
            <label>Name</label>
            <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
          </div>
          <div className="field">
            <label>Location</label>
            <input
              value={draft.location}
              onChange={(e) => setDraft({ ...draft, location: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Time of day</label>
            <input
              value={draft.time_of_day}
              onChange={(e) => setDraft({ ...draft, time_of_day: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Mood</label>
            <input value={draft.mood} onChange={(e) => setDraft({ ...draft, mood: e.target.value })} />
          </div>
          <div className="field">
            <label>Visual / ref notes</label>
            <textarea
              rows={3}
              value={draft.visual_notes}
              onChange={(e) => setDraft({ ...draft, visual_notes: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Scene ref image</label>
            <input
              type="file"
              accept="image/*"
              onChange={(e) => e.target.files?.[0] && replaceRef(e.target.files[0])}
            />
            <div className="inline-actions" style={{ marginTop: 8 }}>
              <button
                className="btn ghost tiny"
                type="button"
                disabled={!draft.reference_path || saving}
                onClick={() => save({ ...draft, reference_path: null })}
              >
                Clear ref
              </button>
            </div>
          </div>
          <button className="btn acid" type="button" disabled={saving} onClick={() => save()}>
            Save scene
          </button>
        </div>
      )}
    </div>
  )
}

function ShotsTab({
  project,
  setProject,
  busy,
  notify,
  onGenerate,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
  onGenerate: (id: string) => void
}) {
  const update = async (shot: Shot, patch: Record<string, unknown>) => {
    try {
      const p = await api.patchShot(project.id, shot.id, patch)
      setProject(p)
    } catch (err) {
      notify(String((err as Error).message || err))
    }
  }

  const addManualShot = async () => {
    try {
      const p = await api.addShot(project.id, {
        title: `Shot ${project.shots.length + 1}`,
        action: '',
        camera: 'medium',
        duration_sec: 3,
        storyboard_note: '',
      })
      setProject(p)
      notify('Shot added — edit the fields below (no agent needed).')
    } catch (err) {
      notify(String((err as Error).message || err))
    }
  }

  return (
    <div>
      <p className="hint">
        Build the shot list yourself or with the Agent. Every field is editable. With{' '}
        <em>continue from previous</em> on, Generate runs as i2v from the prior take’s last frame.
      </p>
      <div className="inline-actions" style={{ marginBottom: 12 }}>
        <button className="btn acid" type="button" disabled={busy} onClick={addManualShot}>
          Add shot
        </button>
      </div>
      {project.shots.length === 0 ? (
        <div className="empty">
          No shots yet. Click <strong>Add shot</strong> to build the board by hand, or ask the Agent
          to plan one.
        </div>
      ) : null}
      <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
        <input
          type="checkbox"
          checked={project.continue_from_previous !== false}
          onChange={async (e) => {
            const p = await api.putProject({
              ...project,
              continue_from_previous: e.target.checked,
            })
            setProject(p)
            notify(
              e.target.checked
                ? 'Shot chain on — next generates continue from last video frame.'
                : 'Shot chain off — each shot starts fresh (t2v).',
            )
          }}
        />
        Continue each shot from the last frame of the previous video
      </label>
      <div className="shot-list">
        {project.shots.map((shot) => (
          <div className="shot-card" key={shot.id}>
            <div className="shot-index">{shot.index + 1}</div>
            <div className="shot-editor">
              <div className="inline-actions">
                <span className={`badge ${shot.status}`}>{shot.status}</span>
                <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => onGenerate(shot.id)}>
                  {shot.index > 0 && project.continue_from_previous !== false
                    ? 'Continue'
                    : 'Generate'}
                </button>
                <button
                  className="btn ghost tiny"
                  type="button"
                  onClick={async () => {
                    const p = await api.deleteShot(project.id, shot.id)
                    setProject(p)
                    notify('Shot removed.')
                  }}
                >
                  Delete
                </button>
              </div>
              <input
                defaultValue={shot.title}
                onBlur={(e) => {
                  if (e.target.value !== shot.title) update(shot, { title: e.target.value })
                }}
              />
              <textarea
                rows={2}
                defaultValue={shot.action}
                onBlur={(e) => {
                  if (e.target.value !== shot.action) update(shot, { action: e.target.value })
                }}
                placeholder="Action"
              />
              <div className="row">
                <select
                  value={shot.camera}
                  onChange={(e) => update(shot, { camera: e.target.value })}
                >
                  {['wide', 'medium', 'close-up', 'tracking', 'pov'].map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  step={0.5}
                  defaultValue={shot.duration_sec}
                  onBlur={(e) => {
                    const v = Number(e.target.value)
                    if (v !== shot.duration_sec) update(shot, { duration_sec: v })
                  }}
                />
                <input
                  defaultValue={shot.dialogue}
                  onBlur={(e) => {
                    if (e.target.value !== shot.dialogue) update(shot, { dialogue: e.target.value })
                  }}
                  placeholder="Dialogue"
                />
              </div>
              <textarea
                rows={2}
                defaultValue={shot.prompt}
                onBlur={(e) => {
                  if (e.target.value !== shot.prompt) update(shot, { prompt: e.target.value })
                }}
                placeholder="Visual prompt for local generation"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function StoryboardTab(props: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
  onGenerate: (ids?: string[]) => void
}) {
  return <StoryboardStudio {...props} />
}

function CharactersTab({
  project,
  setProject,
  busy,
  setBusy,
  onGenerateRefs,
  notify,
  onAddCharToAgent,
  onAddSceneToAgent,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  onGenerateRefs: (kind: 'character_still' | 'scene_still') => void
  notify: (m: string) => void
  onAddCharToAgent?: (c: CharacterProfile) => void
  onAddSceneToAgent?: (s: SceneProfile) => void
}) {
  const [editingChar, setEditingChar] = useState<string | null>(null)
  const [editingScene, setEditingScene] = useState<string | null>(null)

  const saveChar = async (c: CharacterProfile) => {
    setBusy(true)
    try {
      const p = await api.updateCharacter(project.id, c)
      setProject(p)
      notify('Character ref saved.')
      setEditingChar(null)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const saveScene = async (s: SceneProfile) => {
    setBusy(true)
    try {
      const p = await api.updateScene(project.id, s)
      setProject(p)
      notify('Scene ref saved.')
      setEditingScene(null)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Generate refs, then edit anything — look notes, mood, or swap the reference image. Use{' '}
        <strong>Add to agent</strong> to drop a person or scene into Agent chat as a face/look lock.
      </p>
      <div className="inline-actions" style={{ marginBottom: 16 }}>
        <button className="btn acid" type="button" disabled={busy} onClick={() => onGenerateRefs('character_still')}>
          Generate character refs
        </button>
        <button className="btn" type="button" disabled={busy} onClick={() => onGenerateRefs('scene_still')}>
          Generate scene refs
        </button>
      </div>
      <div className="two-col">
        <div className="panel">
          <h3>Character looks</h3>
          <div className="takes-grid">
            {project.characters.map((c) => (
              <EditableRefCard
                key={c.id}
                title={c.name}
                subtitle={c.look || c.role || 'No look notes'}
                refPath={c.reference_path}
                open={editingChar === c.id}
                onToggle={() => setEditingChar(editingChar === c.id ? null : c.id)}
                busy={busy}
                onUpload={async (file) => {
                  const up = await api.engineUpload(file)
                  await saveChar({ ...c, reference_path: up.path })
                }}
                onClear={() => saveChar({ ...c, reference_path: null })}
                onAddToAgent={onAddCharToAgent ? () => onAddCharToAgent(c) : undefined}
              >
                <div className="field">
                  <label>Look / ref notes</label>
                  <textarea
                    rows={3}
                    defaultValue={c.look}
                    onBlur={(e) => {
                      if (e.target.value !== c.look) saveChar({ ...c, look: e.target.value })
                    }}
                  />
                </div>
                <div className="field">
                  <label>Role</label>
                  <input
                    defaultValue={c.role}
                    onBlur={(e) => {
                      if (e.target.value !== c.role) saveChar({ ...c, role: e.target.value })
                    }}
                  />
                </div>
                <div className="field">
                  <label>Personality</label>
                  <textarea
                    rows={2}
                    defaultValue={c.personality}
                    onBlur={(e) => {
                      if (e.target.value !== c.personality)
                        saveChar({ ...c, personality: e.target.value })
                    }}
                  />
                </div>
              </EditableRefCard>
            ))}
            {project.characters.length === 0 && <div className="empty">Add characters in Profiles first.</div>}
          </div>
        </div>
        <div className="panel">
          <h3>Scene looks</h3>
          <div className="takes-grid">
            {project.scenes.map((s) => (
              <EditableRefCard
                key={s.id}
                title={s.name}
                subtitle={s.visual_notes || s.mood || 'No notes'}
                refPath={s.reference_path}
                open={editingScene === s.id}
                onToggle={() => setEditingScene(editingScene === s.id ? null : s.id)}
                busy={busy}
                onUpload={async (file) => {
                  const up = await api.engineUpload(file)
                  await saveScene({ ...s, reference_path: up.path })
                }}
                onClear={() => saveScene({ ...s, reference_path: null })}
                onAddToAgent={onAddSceneToAgent ? () => onAddSceneToAgent(s) : undefined}
              >
                <div className="field">
                  <label>Visual / ref notes</label>
                  <textarea
                    rows={3}
                    defaultValue={s.visual_notes}
                    onBlur={(e) => {
                      if (e.target.value !== s.visual_notes)
                        saveScene({ ...s, visual_notes: e.target.value })
                    }}
                  />
                </div>
                <div className="field">
                  <label>Location</label>
                  <input
                    defaultValue={s.location}
                    onBlur={(e) => {
                      if (e.target.value !== s.location) saveScene({ ...s, location: e.target.value })
                    }}
                  />
                </div>
                <div className="field">
                  <label>Mood</label>
                  <input
                    defaultValue={s.mood}
                    onBlur={(e) => {
                      if (e.target.value !== s.mood) saveScene({ ...s, mood: e.target.value })
                    }}
                  />
                </div>
                <div className="field">
                  <label>Time of day</label>
                  <input
                    defaultValue={s.time_of_day}
                    onBlur={(e) => {
                      if (e.target.value !== s.time_of_day)
                        saveScene({ ...s, time_of_day: e.target.value })
                    }}
                  />
                </div>
              </EditableRefCard>
            ))}
            {project.scenes.length === 0 && <div className="empty">Add scenes in Profiles first.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}

function EditableRefCard({
  title,
  subtitle,
  refPath,
  open,
  onToggle,
  busy,
  onUpload,
  onClear,
  onAddToAgent,
  children,
}: {
  title: string
  subtitle: string
  refPath?: string | null
  open: boolean
  onToggle: () => void
  busy: boolean
  onUpload: (file: File) => Promise<void>
  onClear: () => void
  onAddToAgent?: () => void
  children: ReactNode
}) {
  return (
    <div className="take-card">
      {mediaUrl(refPath) ? (
        <img src={mediaUrl(refPath)} alt={title} />
      ) : (
        <div className="board-thumb">{title}</div>
      )}
      <div className="body">
        <strong>{title}</strong>
        <div className="muted">{subtitle}</div>
        <div className="inline-actions">
          <button className="btn acid tiny" type="button" onClick={onToggle}>
            {open ? 'Done' : 'Edit ref'}
          </button>
          {onAddToAgent ? (
            <button className="btn ghost tiny" type="button" disabled={busy} onClick={onAddToAgent}>
              Add to agent
            </button>
          ) : null}
        </div>
        {open && (
          <div className="profile-form" style={{ marginTop: 8 }}>
            {children}
            <div className="field">
              <label>Replace ref image</label>
              <input
                type="file"
                accept="image/*"
                disabled={busy}
                onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
              />
            </div>
            <button className="btn ghost tiny" type="button" disabled={busy || !refPath} onClick={onClear}>
              Clear ref image
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// Models that change something other than the size (RIFE adds frames) are
// tools you choose on purpose, never the default for Upsample.
const NEVER_DEFAULT = new Set(['rife-smooth-2x'])

function defaultModelFor(models: EngineModel[], activeId?: string | null): EngineModel | undefined {
  const ok = models.filter((m) => !NEVER_DEFAULT.has(m.id))
  return (
    ok.find((m) => m.installed && (m.id === activeId || m.active)) ||
    ok.find((m) => m.installed) ||
    ok[0] ||
    models[0]
  )
}

function GenerateTab({
  project,
  setProject,
  notify,
  health,
  seed,
  onSeedConsumed,
  onOpenSpeedGuide,
}: {
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
  health: Health | null
  seed?: InspirationSeed | null
  onSeedConsumed?: () => void
  onOpenSpeedGuide?: () => void
}) {
  const [engine, setEngine] = useState<EngineStatus | null>(null)
  const [jobs, setJobs] = useState<EngineJob[]>([])
  const [mode, setMode] = useState<GenMode>('t2v')
  const [modelId, setModelId] = useState('')
  const [prompt, setPrompt] = useState('')
  const [negative, setNegative] = useState('')
  const [shotId, setShotId] = useState('')
  const [imagePath, setImagePath] = useState<string | null>(null)
  const [refPath, setRefPath] = useState<string | null>(null)
  const [videoPath, setVideoPath] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [refUrl, setRefUrl] = useState<string | null>(null)
  const [videoUrl, setVideoUrl] = useState<string | null>(null)
  const [videoLabel, setVideoLabel] = useState('')
  const [width, setWidth] = useState(project.width || 768)
  const [height, setHeight] = useState(project.height || 432)
  const [quality, setQuality] = useState('balanced')
  const [durationSec, setDurationSec] = useState(3)
  const [fps, setFps] = useState(24)
  const [frames, setFrames] = useState(0) // 0 = auto from duration × fps
  const [renderSeed, setRenderSeed] = useState<number>(() => Math.floor(Math.random() * 1_000_000_000))
  const [seedLocked, setSeedLocked] = useState(false)
  const [steps, setSteps] = useState(0) // 0 = model/quality default
  const [guidance, setGuidance] = useState(-1) // -1 = model default
  const [strength, setStrength] = useState(0.85)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [textEncoder, setTextEncoder] = useState('auto')
  const [audioPath, setAudioPath] = useState<string | null>(null)
  const [audioLabel, setAudioLabel] = useState('')
  const [loraPath, setLoraPath] = useState('')
  const [loraScale, setLoraScale] = useState(0.8)
  const [loras, setLoras] = useState<LoraFile[]>([])
  const [lorasPath, setLorasPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [estimate, setEstimate] = useState<GpuEstimate | null>(null)
  const [estimating, setEstimating] = useState(false)
  const [continuePrev, setContinuePrev] = useState(project.continue_from_previous !== false)
  const [continueInfo, setContinueInfo] = useState<string | null>(null)
  const [restorable, setRestorable] = useState<EngineJob[]>([])
  const [showSpeedTips, setShowSpeedTips] = useState(false)
  const [enhancing, setEnhancing] = useState(false)
  const [promptBeforeEnhance, setPromptBeforeEnhance] = useState<{
    prompt: string
    negative: string
  } | null>(null)
  const [enhanceNote, setEnhanceNote] = useState<string | null>(null)

  const effectiveFrames =
    frames > 0 ? frames : Math.max(8, Math.round(Math.max(0.5, durationSec) * Math.max(1, fps)))

  const applyWorkflow = (wf: Record<string, unknown>) => {
    if (typeof wf.mode === 'string') setMode(wf.mode as GenMode)
    if (typeof wf.model_id === 'string') setModelId(wf.model_id)
    if (typeof wf.prompt === 'string') setPrompt(wf.prompt)
    if (typeof wf.negative_prompt === 'string') setNegative(wf.negative_prompt)
    if (typeof wf.width === 'number') setWidth(wf.width)
    if (typeof wf.height === 'number') setHeight(wf.height)
    if (typeof wf.quality === 'string') setQuality(wf.quality)
    if (typeof wf.duration_sec === 'number') setDurationSec(wf.duration_sec)
    if (typeof wf.fps === 'number') setFps(wf.fps)
    if (typeof wf.frames === 'number') setFrames(wf.frames)
    if (typeof wf.seed === 'number') {
      setRenderSeed(wf.seed)
      setSeedLocked(true)
    }
    if (typeof wf.steps === 'number') setSteps(wf.steps)
    if (typeof wf.guidance === 'number') setGuidance(wf.guidance)
    if (typeof wf.strength === 'number') setStrength(wf.strength)
    if (typeof wf.text_encoder === 'string') setTextEncoder(wf.text_encoder)
    if (typeof wf.audio_path === 'string') {
      setAudioPath(wf.audio_path)
      setAudioLabel(wf.audio_path.split(/[/\\]/).pop() || 'audio')
    }
    if (typeof wf.image_path === 'string') {
      setImagePath(wf.image_path)
      setImageUrl(mediaUrl(wf.image_path) || null)
    }
    if (typeof wf.reference_path === 'string') {
      setRefPath(wf.reference_path)
      setRefUrl(mediaUrl(wf.reference_path) || null)
    }
    if (typeof wf.video_path === 'string') {
      setVideoPath(wf.video_path)
      setVideoUrl(mediaUrl(wf.video_path) || null)
      setVideoLabel(wf.video_path.split(/[/\\]/).pop() || 'video')
    }
    if (typeof wf.lora_path === 'string') setLoraPath(wf.lora_path)
    if (typeof wf.shot_id === 'string') setShotId(wf.shot_id)
    setShowAdvanced(true)
    notify('Workflow restored — review settings, then Generate again.')
  }

  useEffect(() => {
    if (!seed) return
    setMode(seed.mode)
    setPrompt(seed.prompt)
    onSeedConsumed?.()
  }, [seed])

  useEffect(() => {
    if (project.width) setWidth(project.width)
    if (project.height) setHeight(project.height)
  }, [project.width, project.height, project.frame_size_id])

  const refresh = async () => {
    const [e, j, wf] = await Promise.all([
      api.engine(),
      api.engineJobs(),
      api.engineWorkflows().catch(() => ({ jobs: [] as EngineJob[] })),
    ])
    setEngine(e)
    setJobs(j)
    setRestorable(wf.jobs || [])
    setLoras(e.loras || [])
    setLorasPath(e.loras_path || '')
    if (!modelId) {
      const pick = defaultModelFor(e.models.filter((m) => m.modes.includes(mode)), e.active_model_id)
      if (pick) setModelId(pick.id)
    }
  }

  useEffect(() => {
    refresh()
      .then(() => {
        try {
          if (window.sessionStorage.getItem('studionels_restore_workflow') === '1') {
            window.sessionStorage.removeItem('studionels_restore_workflow')
            api.engineWorkflows().then((pack) => {
              const hit = pack.jobs.find((j) => j.workflow)
              if (hit?.workflow) applyWorkflow(hit.workflow)
            })
          }
        } catch {
          /* ignore */
        }
      })
      .catch((err) => notify(String(err.message || err)))
    const t = window.setInterval(() => {
      api
        .engineJobs()
        .then((j) => setJobs(j))
        .catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    if (!engine) return
    const models = engine.models.filter((m) => m.modes.includes(mode))
    if (!models.find((m) => m.id === modelId)) {
      setModelId(defaultModelFor(models, engine.active_model_id)?.id || '')
    }
  }, [mode, engine])

  const estimatePayload = () => ({
    mode,
    model_id: modelId || undefined,
    width,
    height,
    quality,
    duration_sec: durationSec,
    fps,
    frames: frames > 0 ? frames : effectiveFrames,
    steps: steps > 0 ? steps : undefined,
    preset_id: project.preset_id,
  })

  useEffect(() => {
    let cancelled = false
    setEstimating(true)
    const payload = estimatePayload()
    if (continuePrev && (mode === 't2v' || mode === 'i2v')) {
      payload.mode = 'i2v'
    }
    const timer = window.setTimeout(() => {
      api
        .engineEstimate(payload)
        .then((e) => {
          if (!cancelled) setEstimate(e)
        })
        .catch(() => undefined)
        .finally(() => {
          if (!cancelled) setEstimating(false)
        })
    }, 450)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [
    mode,
    modelId,
    width,
    height,
    quality,
    durationSec,
    fps,
    frames,
    steps,
    effectiveFrames,
    project.preset_id,
    continuePrev,
  ])

  useEffect(() => {
    if (!continuePrev || !shotId) {
      setContinueInfo(null)
      return
    }
    api
      .continueSource(project.id, shotId)
      .then((s) => {
        if (s.ok) {
          setContinueInfo(`From “${s.from_shot_title}” last frame`)
          setImagePath(s.image_path || null)
          if (s.thumb_path) setImageUrl(mediaUrl(s.thumb_path) || null)
          setMode('i2v')
        } else {
          setContinueInfo(s.detail || 'No previous take yet')
        }
      })
      .catch(() => setContinueInfo(null))
  }, [continuePrev, shotId, project.id, project.takes.length])

  const modeMeta = engine?.modes.find((m) => m.id === mode)
  const models = engine?.models.filter((m) => m.modes.includes(mode)) || []
  const selectedModel = models.find((m) => m.id === modelId)
  // What "Auto" resolves to: the model's steps scaled by Quality (as the engine does)
  const QUALITY_STEP_SCALE: Record<string, number> = { draft: 0.4, balanced: 1, high: 1.4, max: 1.8 }
  const autoSteps = Math.max(1, Math.floor((selectedModel?.default_steps || 0) * (QUALITY_STEP_SCALE[quality] ?? 1)))
  const style = VISUAL_STYLES.find((s) => s.id === project.visual_style)

  const upload = async (file: File, kind: 'image' | 'reference' | 'video') => {
    const res = await api.engineUpload(file, kind)
    if (kind === 'image') {
      setImagePath(res.path)
      setImageUrl(res.url)
    } else if (kind === 'reference') {
      setRefPath(res.path)
      setRefUrl(res.url)
    } else {
      setVideoPath(res.path)
      setVideoUrl(res.url)
      setVideoLabel(file.name)
    }
  }

  const showStartImage =
    !!modeMeta?.needs_image ||
    !!modeMeta?.accepts_start_image ||
    mode === 'i2v' ||
    mode === 'upsample_image' ||
    (continuePrev && mode === 't2v')
  const showRefImage = !!modeMeta?.needs_reference || mode === 'ref2i' || mode === 'ref2v'
  const showRefVideo =
    !!modeMeta?.needs_video ||
    !!modeMeta?.accepts_ref_video ||
    mode === 'upsample_video' ||
    mode === 'ref2v'

  const run = async () => {
    if (!prompt.trim() && mode.startsWith('t')) {
      notify('Add a prompt first.')
      return
    }
    if ((mode === 'i2v' || mode === 'upsample_image') && !imagePath) {
      notify('Add a photo / still first — use the Image box below.')
      return
    }
    if ((mode === 'ref2i' || mode === 'ref2v') && !refPath && !videoPath) {
      notify('Add a reference photo or reference video first.')
      return
    }
    if (mode === 'upsample_video' && !videoPath) {
      notify('Add a video / clip to upsample first.')
      return
    }
    if (estimate && !estimate.can_queue) {
      notify(estimate.warnings[0] || 'This job will not fit on your GPU. Lower settings first.')
      return
    }
    const selected = models.find((m) => m.id === modelId)
    const dl = selected?.download_status || (selected?.installed ? 'installed' : 'not_downloaded')
    if (selected?.hf_id && dl !== 'installed') {
      notify(
        dl === 'downloading'
          ? `Still downloading ${selected.label} — wait for the progress bar to hit Ready.`
          : `${selected.label} is not Ready. Tap Download model and wait for the bar to finish first.`,
      )
      return
    }
    setBusy(true)
    try {
      const styled =
        style && !prompt.toLowerCase().includes(style.label.toLowerCase())
          ? `${prompt.trim()}, ${style.prompt_suffix}`
          : prompt
      const useContinue = continuePrev && !!imagePath && (mode === 'i2v' || mode === 't2v')
      const job = await api.engineGenerate({
        mode: useContinue ? 'i2v' : mode,
        model_id: modelId || undefined,
        prompt: useContinue
          ? `seamless continuation from previous shot, same camera world, continuous motion, ${styled}`
          : styled,
        negative_prompt: negative || (useContinue ? 'cut, hard edit, flash, jump cut' : ''),
        image_path: imagePath,
        reference_path: refPath,
        video_path: videoPath,
        project_id: project.id,
        shot_id: shotId || undefined,
        width,
        height,
        quality,
        duration_sec: durationSec,
        fps,
        frames: frames > 0 ? frames : undefined,
        seed: renderSeed,
        steps: steps > 0 ? steps : undefined,
        guidance: guidance >= 0 ? guidance : undefined,
        strength:
          mode === 'ref2i' ? strength : undefined,
        text_encoder: textEncoder || 'auto',
        audio_path: audioPath || undefined,
        lora_path: loraPath || undefined,
        lora_scale: loraPath ? loraScale : undefined,
        image_format: project.image_format,
        video_format: project.video_format,
        audio_format: project.audio_format,
        visual_style: project.visual_style,
        inject_continuity: true,
        continue_from_previous: useContinue,
      })
      const eta = estimate?.eta_label ? ` · ETA ${estimate.eta_label}` : ''
      notify(
        useContinue
          ? `Queued continuation i2v · ${job.model_label} · seed ${renderSeed}${eta}`
          : `Queued ${job.mode.toUpperCase()} · ${job.model_label} · seed ${renderSeed}${eta}`,
      )
      if (!seedLocked) {
        setRenderSeed(Math.floor(Math.random() * 1_000_000_000))
      }
      await refresh()
      if (shotId) {
        const p = await api.getProject(project.id)
        setProject(p)
      }
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  // Job shown on the stage: what the user clicked, else the live job, else the latest result.
  const [stageId, setStageId] = useState<string | null>(null)
  const liveJob =
    jobs.find((j) => j.status === 'running') || jobs.find((j) => j.status === 'queued') || null
  const stageJob =
    (stageId ? jobs.find((j) => j.id === stageId) : undefined) ||
    liveJob ||
    jobs.find((j) => j.status === 'done') ||
    jobs[0] ||
    null
  const modeGroups: Array<{ label: string; ids: string[] }> = [
    { label: 'Video', ids: [] },
    { label: 'Image', ids: [] },
    { label: 'Audio', ids: [] },
  ]
  for (const m of engine?.modes || []) {
    const group = m.id === 't2a' ? 2 : /v$|video/.test(m.id) ? 0 : 1
    modeGroups[group].ids.push(m.id)
  }
  const isVideoMode = mode === 't2v' || mode === 'i2v' || mode === 'ref2v'
  // Modes that cannot run without an input file show the slots open.
  const inputsRequired =
    !!modeMeta?.needs_image ||
    !!modeMeta?.needs_reference ||
    !!modeMeta?.needs_video ||
    ['i2v', 'ref2i', 'ref2v', 'upsample_image', 'upsample_video'].includes(mode)
  const downloadsActive = (engine?.models || []).filter(
    (m) =>
      m.download_status === 'downloading' ||
      m.download_status === 'stalled' ||
      m.download_status === 'failed' ||
      m.download_status === 'cancelled',
  )

  return (
    <div className="make-studio">
      <section className="panel gen-panel composer" aria-label="Composer">
        <div className="composer-scroll">
          <div className="composer-block">
            <div className="composer-label">Mode</div>
            {modeGroups
              .filter((g) => g.ids.length > 0)
              .map((g) => (
                <div className="mode-group" key={g.label}>
                  <span className="mode-group-label">{g.label}</span>
                  <div className="mode-chips">
                    {g.ids.map((id) => {
                      const m = (engine?.modes || []).find((x) => x.id === id)
                      if (!m) return null
                      return (
                        <button
                          key={m.id}
                          type="button"
                          title={m.blurb}
                          className={`mode-pill ${mode === m.id ? 'active' : ''}`}
                          onClick={() => setMode(m.id)}
                        >
                          {m.label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            <div className="muted tiny mode-blurb">
              {(engine?.modes || []).find((x) => x.id === mode)?.blurb}
            </div>
          </div>

          {(showStartImage || showRefImage || showRefVideo) && (
            <details
              key={`inputs-${mode}`}
              className="fold section media-slots"
              open={inputsRequired || !!imagePath || !!refPath || !!videoPath}
            >
              <summary>
                {inputsRequired ? 'Inputs' : 'Start photo / reference (optional)'}
                {imagePath || refPath || videoPath ? ' · added' : ''}
              </summary>
              {showStartImage && (
                <div className="field media-slot">
                  <label>
                    {mode === 'upsample_image'
                      ? 'Image to upsample'
                      : mode === 'i2v' || continuePrev
                        ? 'Start photo / still (Image → Video)'
                        : mode === 'ref2v'
                          ? 'Optional start frame (photo)'
                          : 'Input image'}
                    {(mode === 'i2v' || mode === 'upsample_image') && (
                      <span className="tiny"> · required</span>
                    )}
                  </label>
                  <input
                    type="file"
                    accept="image/*,.png,.jpg,.jpeg,.webp,.bmp"
                    onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], 'image')}
                  />
                  {imageUrl && (
                    <div className="slot-preview">
                      <img className="upload-preview" src={imageUrl} alt="start" />
                      <button
                        type="button"
                        className="btn ghost tiny"
                        onClick={() => {
                          setImagePath(null)
                          setImageUrl(null)
                        }}
                      >
                        Remove photo
                      </button>
                    </div>
                  )}
                </div>
              )}
              {showRefImage && (
                <div className="field media-slot">
                  <label>
                    {mode === 'ref2i' ? 'Reference photo (look / identity)' : 'Reference photo'}
                    {(mode === 'ref2i' || mode === 'ref2v') && !videoPath && (
                      <span className="tiny"> · required unless you add a ref video</span>
                    )}
                  </label>
                  <input
                    type="file"
                    accept="image/*,.png,.jpg,.jpeg,.webp,.bmp"
                    onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], 'reference')}
                  />
                  {refUrl && (
                    <div className="slot-preview">
                      <img className="upload-preview" src={refUrl} alt="reference" />
                      <button
                        type="button"
                        className="btn ghost tiny"
                        onClick={() => {
                          setRefPath(null)
                          setRefUrl(null)
                        }}
                      >
                        Remove reference
                      </button>
                    </div>
                  )}
                </div>
              )}
              {showRefVideo && (
                <div className="field media-slot">
                  <label>
                    {mode === 'upsample_video' ? 'Video / clip to upsample' : 'Reference video / clip'}
                    {mode === 'upsample_video' && <span className="tiny"> · required</span>}
                  </label>
                  <input
                    type="file"
                    accept="video/*,.mp4,.webm,.mov,.mkv,.avi"
                    onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], 'video')}
                  />
                  {videoPath && (
                    <div className="slot-preview">
                      {videoUrl && (
                        <video className="upload-preview" src={videoUrl} controls muted playsInline />
                      )}
                      <div className="muted tiny">{videoLabel || videoPath}</div>
                      <button
                        type="button"
                        className="btn ghost tiny"
                        onClick={() => {
                          setVideoPath(null)
                          setVideoUrl(null)
                          setVideoLabel('')
                        }}
                      >
                        Remove video
                      </button>
                    </div>
                  )}
                </div>
              )}
            </details>
          )}

          <div className="composer-block">
            <div className="composer-label-row">
              <div className="composer-label">Prompt</div>
              <div className="inline-actions" style={{ gap: 6 }}>
                {promptBeforeEnhance && (
                  <button
                    type="button"
                    className="btn ghost tiny"
                    onClick={() => {
                      setPrompt(promptBeforeEnhance.prompt)
                      setNegative(promptBeforeEnhance.negative)
                      setPromptBeforeEnhance(null)
                      setEnhanceNote('Restored previous prompt.')
                    }}
                  >
                    Undo enhance
                  </button>
                )}
                <button
                  type="button"
                  className="btn acid tiny"
                  disabled={enhancing || !prompt.trim()}
                  title="Expand a short idea with the Agent LLM (Ollama when set, else offline rules)"
                  onClick={async () => {
                    setEnhancing(true)
                    setEnhanceNote(null)
                    try {
                      setPromptBeforeEnhance({ prompt, negative })
                      const r = await api.engineEnhancePrompt({
                        prompt,
                        negative_prompt: negative,
                        mode,
                        style: style?.label || project.visual_style || null,
                      })
                      setPrompt(r.prompt)
                      if (r.negative_prompt) setNegative(r.negative_prompt)
                      setEnhanceNote(`${r.notes}${r.source ? ` · via ${r.source}` : ''}`)
                      notify('Prompt enhanced')
                    } catch (err) {
                      setPromptBeforeEnhance(null)
                      notify(String((err as Error).message || err))
                    } finally {
                      setEnhancing(false)
                    }
                  }}
                >
                  {enhancing ? 'Enhancing…' : 'Enhance'}
                </button>
              </div>
            </div>
            <textarea
              className="prompt-box"
              rows={5}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the shot: subject, action, setting, light, camera…"
            />
            <div className="muted tiny">
              Style <strong>{style?.label || project.visual_style}</strong> · saves as {project.image_format} /{' '}
              {project.video_format} / {project.audio_format}
              {enhanceNote ? ` · ${enhanceNote}` : ''}
            </div>
            <details className="fold" open={!!negative}>
              <summary>Negative prompt{negative ? ' · set' : ''}</summary>
              <input
                value={negative}
                onChange={(e) => setNegative(e.target.value)}
                placeholder="What to avoid: blur, flicker, extra limbs…"
              />
              {selectedModel?.distilled && (
                <div className="muted tiny" style={{ marginTop: 4 }}>
                  {selectedModel.label} runs without guidance, so the negative prompt has no effect — describe what
                  you want instead.
                </div>
              )}
            </details>
          </div>

          <div className="composer-block">
            <div className="composer-label">Model &amp; shot</div>
          {models.length === 0 && !mode.startsWith('upsample') && (
            <div className="fit-warn">
              No model for {(engine?.modes || []).find((x) => x.id === mode)?.label || mode} is set up yet. Open{' '}
              <strong>Make → Models</strong> to download one, then come back here.
            </div>
          )}
          {models.length === 0 && mode.startsWith('upsample') && (
            <div className="muted tiny">
              {mode === 'upsample_video'
                ? 'Draft / Balanced: instant 2× resize (no new detail). High / Max: AI upscale with LTX-2.3 — adds real detail, takes a few minutes.'
                : 'Instant 2× resize — sharper edges, no new detail.'}
            </div>
          )}
          <div className="field" hidden={models.length === 0}>
            <label>Model</label>
            <select
              value={modelId}
              onChange={async (e) => {
                const id = e.target.value
                setModelId(id)
                try {
                  await api.engineModelActivate(id)
                  notify(`Using ${models.find((m) => m.id === id)?.label || id}`)
                  await refresh()
                } catch (err) {
                  notify(String((err as Error).message || err))
                }
              }}
            >
              {models.map((m) => {
                const st = modelStatus(m)
                const pct = Math.round((m.download_progress || 0) * 100)
                return (
                  <option key={m.id} value={m.id}>
                    {m.label} · {modelDownloadLabel(st, pct)} (≥{m.min_vram_gb} GB)
                  </option>
                )
              })}
            </select>
            {(() => {
              const cur = models.find((m) => m.id === modelId)
              if (!cur) return null
              const st = cur.download_status || (cur.installed ? 'installed' : 'not_downloaded')
              return (
                <div className="inline-actions" style={{ marginTop: 8, flexWrap: 'wrap', gap: 8 }}>
                  {(st === 'not_downloaded' || st === 'cancelled' || st === 'failed' || st === 'stalled') && (
                    <button
                      className="btn acid tiny"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true)
                        try {
                          await api.engineModelDownload(cur.id, st === 'stalled' || st === 'failed')
                          notify(`Downloading ${cur.label}…`)
                          await refresh()
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      {st === 'stalled' ? 'Retry download' : 'Download model'}
                    </button>
                  )}
                  {(st === 'downloading' || st === 'stalled') && (
                    <button
                      className="btn ghost tiny"
                      type="button"
                      onClick={async () => {
                        try {
                          await api.engineModelCancel(cur.id)
                          notify('Download cancelled')
                          await refresh()
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        }
                      }}
                    >
                      Cancel download
                    </button>
                  )}
                  {(st === 'stalled' || st === 'cancelled' || st === 'failed' || st === 'downloading') && (
                    <button
                      className="btn ghost tiny"
                      type="button"
                      onClick={async () => {
                        try {
                          await api.engineModelClear(cur.id, false)
                          notify('Cleared stuck download status')
                          await refresh()
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        }
                      }}
                    >
                      Clear stuck
                    </button>
                  )}
                  {st === 'installed' && (
                    <span className="muted tiny">Downloaded — selected for this mode.</span>
                  )}
                  {cur.notes && <span className="muted tiny">{cur.notes}</span>}
                </div>
              )
            })()}
            {(() => {
              const cur = models.find((m) => m.id === modelId)
              if (!cur) return null
              const st = cur.download_status || (cur.installed ? 'installed' : 'not_downloaded')
              if (
                st !== 'downloading' &&
                st !== 'stalled' &&
                st !== 'failed' &&
                st !== 'cancelled'
              ) {
                return null
              }
              return (
                <ModelDownloadProgress
                  model={cur}
                  onCancel={async () => {
                    try {
                      await api.engineModelCancel(cur.id)
                      notify('Download cancelled')
                      await refresh()
                    } catch (err) {
                      notify(String((err as Error).message || err))
                    }
                  }}
                  onRetry={async () => {
                    setBusy(true)
                    try {
                      await api.engineModelDownload(cur.id, true)
                      notify(`Downloading ${cur.label}…`)
                      await refresh()
                    } catch (err) {
                      notify(String((err as Error).message || err))
                    } finally {
                      setBusy(false)
                    }
                  }}
                />
              )
            })()}
          </div>

          <div className="field">
            <label>Frame size</label>
            <select
              value={FRAME_SIZES.find((f) => f.width === width && f.height === height)?.id || ''}
              onChange={async (e) => {
                const f = frameById(e.target.value)
                setWidth(f.width)
                setHeight(f.height)
                try {
                  const p = await api.setFrameSize(project.id, f.id)
                  setProject(p)
                } catch {
                  /* local only if save fails */
                }
              }}
            >
              {!FRAME_SIZES.some((f) => f.width === width && f.height === height) && (
                <option value="">
                  Custom · {width}×{height}
                </option>
              )}
              {(['landscape', 'square', 'portrait'] as const).map((ori) => (
                <optgroup key={ori} label={ori}>
                  {framesByOrientation(ori).map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.label} · {f.width}×{f.height}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Quality</label>
            {selectedModel?.distilled && /ltx/i.test(selectedModel.id) && (
              <div className="muted tiny" style={{ marginBottom: 6 }}>
                {selectedModel.label} always runs its fixed 8 steps, so Draft and Balanced take the same time. High and
                Max add a 2× upscale pass (1536-wide, sharper faces, about 4× slower).
              </div>
            )}
            <div className="seg" role="radiogroup" aria-label="Quality">
              {(['draft', 'balanced', 'high', 'max'] as const).map((q) => (
                <button
                  key={q}
                  type="button"
                  role="radio"
                  aria-checked={quality === q}
                  className={quality === q ? 'active' : ''}
                  onClick={() => setQuality(q)}
                >
                  {q[0].toUpperCase() + q.slice(1)}
                </button>
              ))}
            </div>
          </div>
          {selectedModel?.default_steps ? (
            <div className="field">
              <label>
                Steps · {steps > 0 ? steps : `Auto (${autoSteps})`}
                {steps > 0 && (
                  <button type="button" className="btn ghost tiny" style={{ marginLeft: 8 }} onClick={() => setSteps(0)}>
                    Auto
                  </button>
                )}
              </label>
              <input
                type="range"
                min={Math.max(1, Math.round((selectedModel.default_steps || 8) / 4))}
                max={Math.max(12, (selectedModel.default_steps || 8) * 2)}
                step={1}
                value={steps > 0 ? steps : autoSteps}
                onChange={(e) => setSteps(Number(e.target.value))}
                aria-label="Denoising steps"
              />
              <div className="muted tiny">
                More steps: more detail and cleaner motion, but slower (time grows with steps). Auto follows Quality.
              </div>
            </div>
          ) : null}
          {isVideoMode ? (
            <div className="field">
              <label>Clip length</label>
              <div className="seg-row">
                <div className="seg" role="radiogroup" aria-label="Clip length">
                  {[1, 2, 3, 5].map((s) => (
                    <button
                      key={s}
                      type="button"
                      role="radio"
                      aria-checked={durationSec === s}
                      className={durationSec === s ? 'active' : ''}
                      onClick={() => {
                        setDurationSec(s)
                        setFrames(0)
                      }}
                    >
                      {s}s
                    </button>
                  ))}
                </div>
                <input
                  className="seg-input"
                  type="number"
                  min={1}
                  step={0.5}
                  value={durationSec}
                  aria-label="Clip length in seconds"
                  onChange={(e) => {
                    const n = Number(e.target.value)
                    if (!Number.isFinite(n)) return
                    setDurationSec(Math.max(1, n))
                    setFrames(0)
                  }}
                />
              </div>
            </div>
          ) : null}
          </div>

          <div className={`gpu-fit fit-${estimate?.fit || 'unknown'} loud-coach`}>
            <header>
              <strong>{estimate?.coach_headline || 'Can my GPU do this?'}</strong>
              <span>{estimating ? '…' : estimate?.eta_label || '—'}</span>
            </header>
            {estimate ? (
              <>
                <div className="muted tiny">
                  {estimate.device_name}
                  {estimate.vram_available_gb != null ? ` · ${estimate.vram_available_gb} GB free` : ''} · needs ~
                  {estimate.vram_estimate_gb} GB · {estimate.width}×{estimate.height} · {estimate.frames} frames
                  {project.aspect_ratio ? ` · ${project.aspect_ratio}` : ''}
                </div>
                {estimate.warnings.map((w: string) => (
                  <div className="fit-warn" key={w}>
                    {w}
                  </div>
                ))}
                {estimate.advice.length > 0 && (
                  <details className="fold">
                    <summary>Tips ({estimate.advice.length})</summary>
                    {estimate.advice.map((a: string) => (
                      <div className="muted tiny" key={a}>
                        {a}
                      </div>
                    ))}
                  </details>
                )}
                {estimate.will_preview && (
                  <div className="fit-warn">PREVIEW — placeholders until ROCm + Diffusers are ready.</div>
                )}
              </>
            ) : (
              <div className="muted tiny">Checking VRAM fit…</div>
            )}
          </div>

          <details className="fold section" open={showAdvanced} onToggle={(e) => setShowAdvanced((e.target as HTMLDetailsElement).open)}>
            <summary>Advanced</summary>
            {showAdvanced && (
              <>
                <div className="controls-grid">
                  <div className="field">
                    <label>Width</label>
                    <input type="number" min={256} step={64} value={width} onChange={(e) => setWidth(Number(e.target.value))} />
                  </div>
                  <div className="field">
                    <label>Height</label>
                    <input type="number" min={256} step={64} value={height} onChange={(e) => setHeight(Number(e.target.value))} />
                  </div>
                  <div className="field">
                    <label>FPS</label>
                    <select value={fps} onChange={(e) => setFps(Number(e.target.value))}>
                      {[8, 12, 16, 24, 25, 30].map((n) => (
                        <option key={n} value={n}>
                          {n} fps
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label>Frames {frames <= 0 ? `(auto ${effectiveFrames})` : ''}</label>
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={frames}
                      onChange={(e) => {
                        const n = Math.max(0, Number(e.target.value) || 0)
                        setFrames(n)
                        if (n > 0) setDurationSec(Math.max(1, Math.round((n / Math.max(1, fps)) * 10) / 10))
                      }}
                      title="0 = duration × fps"
                    />
                  </div>
                  <div className="field">
                    <label>Seed</label>
                    <div className="inline-actions" style={{ gap: 6 }}>
                      <input
                        type="number"
                        min={0}
                        value={renderSeed}
                        onChange={(e) => {
                          setRenderSeed(Math.max(0, Number(e.target.value) || 0))
                          setSeedLocked(true)
                        }}
                        style={{ flex: 1, minWidth: 0 }}
                      />
                      <button
                        className="btn ghost tiny"
                        type="button"
                        title="New random seed"
                        onClick={() => {
                          setRenderSeed(Math.floor(Math.random() * 1_000_000_000))
                          setSeedLocked(true)
                        }}
                      >
                        Random
                      </button>
                    </div>
                    <label className="muted tiny" style={{ display: 'flex', gap: 6, marginTop: 6, alignItems: 'center' }}>
                      <input
                        type="checkbox"
                        checked={seedLocked}
                        onChange={(e) => setSeedLocked(e.target.checked)}
                      />
                      Lock seed (reuse across runs)
                    </label>
                  </div>
                  <div className="field">
                    <label>Steps {steps <= 0 ? '(auto)' : ''}</label>
                    <input
                      type="number"
                      min={0}
                      max={80}
                      step={1}
                      value={steps}
                      onChange={(e) => setSteps(Math.max(0, Number(e.target.value) || 0))}
                      title="0 = model + quality default"
                    />
                  </div>
                  <div className="field">
                    <label>Guidance {guidance < 0 ? '(auto)' : guidance.toFixed(1)}</label>
                    <input
                      type="number"
                      min={-1}
                      max={20}
                      step={0.5}
                      value={guidance}
                      onChange={(e) => setGuidance(Number(e.target.value))}
                      title="-1 = model default"
                    />
                  </div>
                  {mode === 'ref2i' && (
                    <div className="field">
                      <label title="Low keeps the reference; high follows the prompt more">
                        Change from reference {strength.toFixed(2)}
                      </label>
                      <input
                        type="range"
                        min={0.2}
                        max={1}
                        step={0.05}
                        value={strength}
                        onChange={(e) => setStrength(Number(e.target.value))}
                      />
                    </div>
                  )}
                  <div className="field">
                    <label>Text encoder</label>
                    <select value={textEncoder} onChange={(e) => setTextEncoder(e.target.value)}>
                      {(engine?.text_encoders || [
                        { id: 'auto', label: 'Auto (model default)' },
                      ]).map((te) => (
                        <option key={te.id} value={te.id}>
                          {te.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="field" style={{ marginTop: 10 }}>
                  <label>Add audio to video (optional)</label>
                  <input
                    type="file"
                    accept="audio/*,.wav,.mp3,.m4a"
                    onChange={async (e) => {
                      const file = e.target.files?.[0]
                      if (!file) return
                      try {
                        const up = await api.engineUpload(file, 'audio')
                        setAudioPath(up.path)
                        setAudioLabel(file.name)
                        notify(`Audio attached: ${file.name}`)
                      } catch (err) {
                        notify(String((err as Error).message || err))
                      }
                    }}
                  />
                  {audioPath ? (
                    <div className="inline-actions" style={{ marginTop: 6 }}>
                      <span className="muted tiny">{audioLabel || audioPath}</span>
                      <button
                        className="btn ghost tiny"
                        type="button"
                        onClick={() => {
                          setAudioPath(null)
                          setAudioLabel('')
                        }}
                      >
                        Clear audio
                      </button>
                    </div>
                  ) : (
                    <p className="muted tiny">Muxed onto the clip after video finishes (needs ffmpeg).</p>
                  )}
                </div>
                <p className="muted tiny" style={{ marginTop: 8 }}>
                  ≈ {effectiveFrames} frames @ {fps} fps · {durationSec}s
                  {frames > 0 ? ' (manual frame count)' : ' (from length × fps)'}
                  {' · '}seed {renderSeed}
                  {seedLocked ? ' locked' : ' (rolls after each run)'}
                  {' · '}TE {textEncoder}
                </p>
              </>
            )}
          </details>

          {restorable.length > 0 && (
            <details className="fold section">
              <summary>Restore a stopped workflow ({Math.min(5, restorable.length)})</summary>
              <p className="muted tiny">
                Stop keeps your prompt and settings. Pick a cancelled/failed job to load it back.
              </p>
              <div className="job-list">
                {restorable.slice(0, 5).map((j) => (
                  <div className="job-item" key={j.id}>
                    <header>
                      <strong>
                        {j.mode?.toUpperCase()} · {j.status}
                      </strong>
                      <button
                        className="btn acid tiny"
                        type="button"
                        onClick={() => j.workflow && applyWorkflow(j.workflow)}
                      >
                        Restore
                      </button>
                    </header>
                    <div className="muted tiny truncate">{j.prompt || j.message}</div>
                  </div>
                ))}
              </div>
            </details>
          )}

          <details className="fold section" open={!!loraPath}>
            <summary>LoRA{loraPath ? ` · ${loras.find((l) => l.path === loraPath)?.name || 'on'}` : ''}</summary>
          <div className="lora-box">
            <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
              <strong>Optional LoRA</strong>
              <button
                className="btn ghost tiny"
                type="button"
                onClick={async () => {
                  try {
                    const pack = await api.engineLoras()
                    setLoras(pack.loras)
                    setLorasPath(pack.path)
                    if (loraPath && !pack.loras.some((l) => l.path === loraPath)) {
                      setLoraPath('')
                    }
                    notify(
                      pack.count
                        ? `Found ${pack.count} LoRA${pack.count === 1 ? '' : 's'} in folder.`
                        : 'No LoRAs yet — drop .safetensors into loras/.',
                    )
                  } catch (err) {
                    notify(String((err as Error).message || err))
                  }
                }}
              >
                Refresh folder
              </button>
            </div>
            <div className="muted tiny" style={{ marginBottom: 8 }}>
              Auto-scans <code>loras/</code>
              {lorasPath ? ` (${lorasPath})` : ''} — drop .safetensors / .pt files, then pick below.
            </div>
            <select
              value={loraPath}
              onChange={(e) => setLoraPath(e.target.value)}
              aria-label="LoRA from folder"
            >
              <option value="">— none —</option>
              {loras.map((l) => (
                <option key={l.path} value={l.path}>
                  {l.name} ({l.size_mb} MB)
                </option>
              ))}
            </select>
            {loras.length === 0 && (
              <div className="muted tiny" style={{ marginTop: 6 }}>
                Folder empty. Add files to <code>loras/</code> and hit Refresh.
              </div>
            )}
            <div className="field" style={{ marginTop: 10 }}>
              <label>
                LoRA strength {loraScale.toFixed(2)}
                {!loraPath ? ' (pick a LoRA above to apply)' : ''}
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={loraScale}
                disabled={!loraPath}
                onChange={(e) => setLoraScale(Number(e.target.value))}
              />
              <div className="muted tiny" style={{ marginTop: 4 }}>
                0 = off · 0.8 typical · above 1.0 is strong
              </div>
            </div>
          </div>
          </details>

          <details className="fold section" open={!!shotId || continuePrev}>
            <summary>
              Shot &amp; continuity
              {shotId ? ` · shot ${(project.shots.find((s) => s.id === shotId)?.index ?? 0) + 1}` : ''}
              {continuePrev ? ' · continues previous' : ''}
            </summary>
            <div className="field">
              <label>Attach to shot (optional)</label>
              <select value={shotId} onChange={(e) => setShotId(e.target.value)}>
                <option value="">— standalone —</option>
                {project.shots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.index + 1}. {s.title}
                  </option>
                ))}
              </select>
            </div>
            <label className="muted check-row">
              <input type="checkbox" checked={continuePrev} onChange={(e) => setContinuePrev(e.target.checked)} />
              <span>
                Continue from previous video’s last frame (i2v chain)
                {continueInfo ? <span className="tiny"> — {continueInfo}</span> : null}
              </span>
            </label>
          </details>
        </div>

        <div className="composer-foot">
          <button
            className="btn acid generate-btn"
            type="button"
            disabled={busy || (estimate != null && !estimate.can_queue)}
            onClick={() => {
              setStageId(null)
              void run()
            }}
          >
            Generate {(engine?.modes || []).find((x) => x.id === mode)?.label || mode.toUpperCase()}
            {estimate?.eta_label ? <span className="generate-eta">{estimate.eta_label}</span> : null}
          </button>
        </div>
      </section>

      <section className="stage-col" aria-label="Stage">
        <div className="panel stage-panel">
          <div className="stage-head">
            <h3>{stageJob ? describeJobActivity(stageJob).phase : 'Stage'}</h3>
            <div className="inline-actions" style={{ gap: 6 }}>
              <button className="btn ghost tiny" type="button" onClick={() => setShowSpeedTips((v) => !v)}>
                {showSpeedTips ? 'Hide tips' : 'Speed tips'}
              </button>
            </div>
          </div>
          <SpeedTipsPanel open={showSpeedTips} onClose={() => setShowSpeedTips(false)} onOpenLearning={onOpenSpeedGuide} />
          <StageView
            job={stageJob}
            deviceNote={
              health?.gpu
                ? `GPU stays idle until you press Generate · ${health.device_name}`
                : 'Preview mode until the AMD engine is installed.'
            }
          />
          {stageJob && (stageJob.status === 'running' || stageJob.status === 'queued') && (
            <div className="stage-progress">
              <GenerationStageBar job={stageJob} showTipsLink onOpenTips={() => setShowSpeedTips(true)} />
              <button
                className="btn ghost tiny"
                type="button"
                onClick={async () => {
                  try {
                    await api.engineCancelJob(stageJob.id)
                    notify('Stopped — your prompt and settings are saved.')
                    setJobs(await api.engineJobs())
                  } catch (err) {
                    notify(String((err as Error).message || err))
                  }
                }}
              >
                Stop
              </button>
            </div>
          )}
          {stageJob && (
            <div className="stage-caption">
              <span className="muted tiny">
                {stageJob.mode.toUpperCase()} · {stageJob.model_label}
                {stageJob.preview ? ' · preview output' : ''}
              </span>
              <span className="stage-prompt">{stageJob.prompt || '(no prompt)'}</span>
              {stageJob.error && stageJob.status !== 'done' ? <div className="fit-warn tiny">{stageJob.error.slice(0, 300)}</div> : null}
              {stageJob.status === 'done' && isVideoPath(stageJob.media_path) ? (
                <button
                  className="btn acid tiny"
                  type="button"
                  title="Add this clip to the end of the Director timeline"
                  onClick={async () => {
                    try {
                      const r = await api.addVideoToDirector(
                        project.id,
                        stageJob.media_path as string,
                        (stageJob.prompt || 'Clip').slice(0, 40),
                      )
                      setProject(r.project)
                      notify('Added to the Director timeline.')
                    } catch (err) {
                      notify(String((err as Error).message || err))
                    }
                  }}
                >
                  Add to Director
                </button>
              ) : null}
              {stageJob.workflow && stageJob.status !== 'running' && stageJob.status !== 'queued' ? (
                <button
                  className="btn ghost tiny"
                  type="button"
                  onClick={() => stageJob.workflow && applyWorkflow(stageJob.workflow)}
                  title="Load this take's prompt and settings into the composer"
                >
                  Reuse settings
                </button>
              ) : null}
            </div>
          )}
          <EngineWarmLine />
        </div>

        <div className="panel recent-panel">
          <div className="stage-head">
            <h3>Recent</h3>
            {jobs.some((j) => j.status === 'done' || j.status === 'failed' || j.status === 'cancelled') && (
              <button
                className="btn ghost tiny"
                type="button"
                onClick={async () => {
                  try {
                    const r = await api.engineClearFinishedJobs()
                    notify(`Removed ${r.removed} finished job(s) from the list (takes stay in Takes)`)
                    setJobs(await api.engineJobs())
                  } catch (err) {
                    notify(String((err as Error).message || err))
                  }
                }}
              >
                Clear finished
              </button>
            )}
          </div>
          {downloadsActive.length > 0 && (
            <div className="job-list" style={{ marginBottom: 10 }}>
              {downloadsActive.map((m) => {
                const act = describeDownloadActivity(m)
                return (
                  <div className={`job-item activity-${act.tone}`} key={`dl-${m.id}`}>
                    <ModelDownloadProgress model={m} compact />
                  </div>
                )
              })}
            </div>
          )}
          {jobs.length === 0 ? (
            <div className="empty">Nothing yet — your takes collect here.</div>
          ) : (
            <div className="recent-grid">
              {jobs.map((job) => {
                const act = describeJobActivity(job)
                const selected = stageJob?.id === job.id
                return (
                  <div
                    key={job.id}
                    role="button"
                    tabIndex={0}
                    className={`recent-card activity-${act.tone} ${selected ? 'active' : ''}`}
                    onClick={() => setStageId(job.id)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setStageId(job.id)
                      }
                    }}
                    title={job.prompt}
                  >
                    <RecentThumb job={job} />
                    <div className="recent-meta">
                      <span className={`job-phase tone-${act.tone}`}>{act.phase}</span>
                      <span className="muted tiny truncate">{job.prompt || '(no prompt)'}</span>
                    </div>
                    <button
                      type="button"
                      className="recent-x"
                      title="Remove from list (the take stays in Takes)"
                      aria-label="Remove from list"
                      onClick={async (e) => {
                        e.stopPropagation()
                        try {
                          await api.engineDismissJob(job.id)
                          if (stageId === job.id) setStageId(null)
                          setJobs(await api.engineJobs())
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        }
                      }}
                    >
                      ×
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function isAudioPath(path: string | null | undefined) {
  return !!path && /\.(wav|mp3|m4a|flac|ogg|aac)$/i.test(path)
}

function isVideoPath(path: string | null | undefined) {
  return !!path && /\.(mp4|webm|mov|mkv|avi)$/i.test(path)
}

/** The big viewer: live preview while running, the playable result when done. */
function StageView({ job, deviceNote }: { job: EngineJob | null; deviceNote?: string }) {
  if (!job) {
    return (
      <div className="stage-view stage-empty">
        <strong>Your shot appears here</strong>
        <span>Write a prompt and press Generate. A 1–3 second clip is the right first test.</span>
        {deviceNote ? <span className="tiny">{deviceNote}</span> : null}
      </div>
    )
  }
  if (job.status === 'done' && job.media_path) {
    const src = mediaUrl(job.media_path)
    if (src && isVideoPath(job.media_path)) {
      return (
        <div className="stage-view">
          <video key={src} src={src} controls autoPlay muted loop playsInline />
        </div>
      )
    }
    if (src && isAudioPath(job.media_path)) {
      return (
        <div className="stage-view stage-empty">
          <strong>Audio ready</strong>
          <audio src={src} controls preload="metadata" />
        </div>
      )
    }
    if (src) {
      return (
        <div className="stage-view">
          <img src={src} alt="Result" />
        </div>
      )
    }
  }
  if ((job.status === 'running' || job.status === 'queued') && job.live_preview_path) {
    const base = mediaUrl(job.live_preview_path)
    if (base) {
      const src = `${base}${base.includes('?') ? '&' : '?'}t=${job.live_preview_ts || 0}`
      return (
        <div className="stage-view live">
          <img src={src} alt="Live preview" />
          <span className="stage-badge">
            Live preview{job.step && job.steps_total ? ` · step ${job.step}/${job.steps_total}` : ''}
          </span>
        </div>
      )
    }
  }
  if (job.status === 'running' || job.status === 'queued') {
    const act = describeJobActivity(job)
    return (
      <div className="stage-view stage-empty working">
        <span className="stage-pulse" aria-hidden />
        <strong>{act.phase}</strong>
        <span>The preview appears once the first steps finish.</span>
      </div>
    )
  }
  return (
    <div className="stage-view stage-empty">
      <strong>{job.status === 'cancelled' ? 'Stopped' : job.status === 'failed' ? 'This take failed' : 'No media'}</strong>
      <span>{job.status === 'failed' ? 'See the reason below. Reuse settings to try again.' : 'Reuse settings to run it again.'}</span>
    </div>
  )
}

/** Small square for the Recent grid. */
function RecentThumb({ job }: { job: EngineJob }) {
  if (job.status === 'done' && job.media_path) {
    const src = mediaUrl(job.media_path)
    if (src && isVideoPath(job.media_path)) {
      const poster = job.thumb_path && !isVideoPath(job.thumb_path) ? mediaUrl(job.thumb_path) : undefined
      return (
        <div className="recent-thumb">
          <video src={`${src}#t=0.5`} poster={poster} muted preload="metadata" playsInline />
          <span className="recent-play" aria-hidden>
            ▶
          </span>
        </div>
      )
    }
    if (src && !isAudioPath(job.media_path)) {
      return (
        <div className="recent-thumb">
          <img src={src} alt="" />
        </div>
      )
    }
    return <div className="recent-thumb glyph">♪</div>
  }
  if (job.live_preview_path) {
    const base = mediaUrl(job.live_preview_path)
    return (
      <div className="recent-thumb">
        <img src={`${base}${base?.includes('?') ? '&' : '?'}t=${job.live_preview_ts || 0}`} alt="" />
      </div>
    )
  }
  const glyph = job.status === 'failed' ? '!' : job.status === 'cancelled' ? '■' : '…'
  return <div className={`recent-thumb glyph status-${job.status}`}>{glyph}</div>
}

/** Running: live preview frame. Done: the result itself, playable right here. */
function JobMedia({ job, compact = false }: { job: EngineJob; compact?: boolean }) {
  const cls = compact ? 'job-media compact' : 'job-media'
  if (job.status === 'done' && job.media_path) {
    const src = mediaUrl(job.media_path)
    if (!src) return null
    if (isVideoPath(job.media_path)) {
      return (
        <video
          key={src}
          className={cls}
          src={src}
          poster={job.thumb_path && !isVideoPath(job.thumb_path) ? mediaUrl(job.thumb_path) : undefined}
          controls
          autoPlay
          muted
          loop
          playsInline
          preload="metadata"
        />
      )
    }
    if (isAudioPath(job.media_path)) {
      return <audio className="job-media-audio" src={src} controls preload="metadata" />
    }
    return <img className={cls} src={src} alt="Result" />
  }
  if ((job.status === 'running' || job.status === 'queued') && job.live_preview_path) {
    const base = mediaUrl(job.live_preview_path)
    if (!base) return null
    const src = `${base}${base.includes('?') ? '&' : '?'}t=${job.live_preview_ts || 0}`
    return (
      <figure className={`${cls} live`}>
        <img src={src} alt="Live preview" />
        <figcaption>
          Live preview{job.step && job.steps_total ? ` · step ${job.step}/${job.steps_total}` : ''}
        </figcaption>
      </figure>
    )
  }
  return null
}

function TakeMediaPreview({ path, label }: { path: string | null | undefined; label?: string }) {
  const src = mediaUrl(path)
  if (!src || !path) return null
  if (isAudioPath(path)) {
    return (
      <div className="take-audio-wrap">
        <div className="take-audio-badge">Audio</div>
        <audio controls src={src} preload="metadata" style={{ width: '100%' }} />
        <a className="btn ghost tiny" href={src} download style={{ marginTop: 6 }}>
          Download {label || path.split(/[/\\]/).pop()}
        </a>
      </div>
    )
  }
  if (isVideoPath(path)) {
    return <video className="take-video" src={src} controls playsInline preload="metadata" />
  }
  return <img src={src} alt={label || ''} />
}

function SamplingTab({
  project,
  setProject,
  busy,
  setBusy,
  notify,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
}) {
  const previewCount = project.takes.filter((t) => t.is_placeholder).length
  const shotIds = new Set(project.shots.map((s) => s.id))
  const libraryTakes = project.takes.filter(
    (t) => t.shot_id === '__library__' || !shotIds.has(t.shot_id),
  )

  if (project.takes.length === 0) {
    return (
      <div className="empty">
        No generations yet. Run Generate or Audio — finished clips (including standalone audio) show
        up here.
      </div>
    )
  }

  const byShot = project.shots.map((shot) => ({
    shot,
    takes: project.takes.filter((t) => t.shot_id === shot.id),
  }))

  return (
    <div>
      <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <p className="hint" style={{ margin: 0 }}>
          Compare takes (video, image, and audio). Pin shot takes for Director. Standalone audio
          lands under Library below.
        </p>
        {previewCount > 0 && (
          <button
            className="btn ghost tiny"
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              try {
                const p = await api.clearPreviewTakes(project.id, true)
                setProject(p)
                notify(`Deleted ${previewCount} preview take(s).`)
              } catch (err) {
                notify(String((err as Error).message || err))
              } finally {
                setBusy(false)
              }
            }}
          >
            Delete all previews ({previewCount})
          </button>
        )}
      </div>
      {libraryTakes.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h3 style={{ fontFamily: 'var(--font-display)' }}>Library / standalone generations</h3>
          <p className="muted tiny">
            Audio and Generate runs without a shot attach here — play or download below.
          </p>
          <div className="takes-grid">
            {libraryTakes.map((take) => (
              <div className="take-card" key={take.id}>
                <TakeMediaPreview path={take.media_path} label={take.label} />
                <div className="body">
                  <strong>{take.label}</strong>
                  <div className="muted tiny">
                    seed {take.seed}
                    {take.is_placeholder ? ' · preview' : ''}
                    {isAudioPath(take.media_path) ? ' · audio' : ''}
                  </div>
                  {take.prompt_used ? (
                    <div className="muted tiny truncate">{take.prompt_used}</div>
                  ) : null}
                  <div className="inline-actions">
                    {isVideoPath(take.media_path) && (
                      <button
                        className="btn acid tiny"
                        type="button"
                        disabled={busy}
                        title="Add this clip to the end of the Director timeline"
                        onClick={async () => {
                          setBusy(true)
                          try {
                            const r = await api.addVideoToDirector(
                              project.id,
                              take.media_path as string,
                              (take.prompt_used || take.label || 'Clip').slice(0, 40),
                            )
                            setProject(r.project)
                            notify('Added to the Director timeline.')
                          } catch (err) {
                            notify(String((err as Error).message || err))
                          } finally {
                            setBusy(false)
                          }
                        }}
                      >
                        Add to Director
                      </button>
                    )}
                    <button
                      className="btn ghost tiny"
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        if (!window.confirm(`Delete “${take.label}” and its file? This cannot be undone.`)) return
                        setBusy(true)
                        try {
                          const p = await api.deleteTake(project.id, take.id, true)
                          setProject(p)
                          notify(`Deleted ${take.label}.`)
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        } finally {
                          setBusy(false)
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {byShot.map(({ shot, takes }) =>
        takes.length ? (
          <div key={shot.id} style={{ marginBottom: 24 }}>
            <h3 style={{ fontFamily: 'var(--font-display)' }}>
              {shot.index + 1}. {shot.title}
            </h3>
            <div className="takes-grid">
              {takes.map((take) => (
                <div className="take-card" key={take.id}>
                  <TakeMediaPreview path={take.media_path} label={take.label} />
                  <div className="body">
                    <strong>{take.label}</strong>
                    <div className="muted tiny">
                      seed {take.seed}
                      {take.is_placeholder ? ' · preview placeholder' : ''}
                      {take.is_rehearsal ? ' · rehearsal' : ''}
                      {take.rejected ? ' · rejected' : ''}
                      {isAudioPath(take.media_path) ? ' · audio' : ''}
                    </div>
                    {take.continuity_score != null && (
                      <div className={`cont-score ${take.rejected ? 'bad' : 'ok'}`}>
                        Continuity {Math.round(take.continuity_score * 100)}%
                      </div>
                    )}
                    {(take.continuity_flags || []).slice(0, 2).map((f) => (
                      <div className="muted tiny" key={f}>
                        {f}
                      </div>
                    ))}
                    <div className="inline-actions">
                      {!isAudioPath(take.media_path) && (
                        <button
                          className="btn acid"
                          type="button"
                          disabled={busy || shot.pinned_take_id === take.id}
                          onClick={async () => {
                            setBusy(true)
                            try {
                              const p = await api.pinTake(project.id, take.id)
                              setProject(p)
                              notify(`Pinned ${take.label} for Director.`)
                            } finally {
                              setBusy(false)
                            }
                          }}
                        >
                          {shot.pinned_take_id === take.id ? 'Pinned' : 'Pin take'}
                        </button>
                      )}
                      {take.is_rehearsal && (
                        <button
                          className="btn ghost"
                          type="button"
                          disabled={busy}
                          onClick={async () => {
                            setBusy(true)
                            try {
                              const p = await api.promoteTake(project.id, take.id)
                              setProject(p)
                              notify('Promoted rehearsal take to final pin.')
                            } finally {
                              setBusy(false)
                            }
                          }}
                        >
                          Promote
                        </button>
                      )}
                      {take.media_path && isVideoPath(take.media_path) && (
                          <label className="btn ghost tiny" style={{ cursor: busy ? 'default' : 'pointer' }}>
                            Add audio
                            <input
                              type="file"
                              accept="audio/*,.wav,.mp3,.m4a"
                              hidden
                              disabled={busy}
                              onChange={async (e) => {
                                const file = e.target.files?.[0]
                                e.target.value = ''
                                if (!file) return
                                setBusy(true)
                                try {
                                  const res = await api.takeAddAudio(project.id, take.id, file)
                                  setProject(res.project)
                                  notify(res.message || 'Audio added as new take.')
                                } catch (err) {
                                  notify(String((err as Error).message || err))
                                } finally {
                                  setBusy(false)
                                }
                              }}
                            />
                          </label>
                        )}
                      <button
                        className="btn ghost tiny"
                        type="button"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true)
                          try {
                            const p = await api.deleteTake(project.id, take.id, true)
                            setProject(p)
                            notify(
                              take.is_placeholder
                                ? 'Deleted preview take.'
                                : `Deleted ${take.label}.`,
                            )
                          } catch (err) {
                            notify(String((err as Error).message || err))
                          } finally {
                            setBusy(false)
                          }
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null,
      )}
    </div>
  )
}

function SettingsTab({
  project,
  setProject,
  settings,
  setSettings,
  presets,
  health,
  notify,
  onHealthRefresh,
}: {
  project: Project
  setProject: (p: Project) => void
  settings: Settings
  setSettings: (s: Settings) => void
  presets: Preset[]
  health: Health | null
  notify: (m: string) => void
  onHealthRefresh?: () => void
}) {
  const [draft, setDraft] = useState(settings)
  const [providers, setProviders] = useState<AgentProviderInfo[]>([])
  const [keyDraft, setKeyDraft] = useState('')
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => setDraft(settings), [settings])
  useEffect(() => {
    api
      .agentProviders()
      .then((r) => {
        setProviders(r.providers)
        setAgentStatus(r.status)
      })
      .catch(() => undefined)
  }, [settings.agent_provider, settings.ollama_url, settings.agent_model, settings.ollama_model])

  const selected = providers.find((p) => p.id === draft.agent_provider)

  const refreshStatus = async () => {
    try {
      const r = await api.agentProviders()
      setProviders(r.providers)
      setAgentStatus(r.status)
    } catch {
      /* ignore */
    }
  }

  const save = async () => {
    const body = {
      ...draft,
      agent_api_key: keyDraft.trim() || (draft.agent_api_key_set ? '(unchanged)' : ''),
    }
    const s = await api.putSettings(body)
    setSettings(s)
    setKeyDraft('')
    const updated = { ...project, preset_id: draft.preset_id }
    const p = await api.putProject(updated)
    setProject(p)
    notify('Settings saved.')
    await refreshStatus()
  }

  const testConnection = async () => {
    setTesting(true)
    try {
      // Save draft first so the test uses the URL/model you typed
      const body = {
        ...draft,
        agent_api_key: keyDraft.trim() || (draft.agent_api_key_set ? '(unchanged)' : ''),
      }
      const s = await api.putSettings(body)
      setSettings(s)
      setKeyDraft('')
      const status = await api.agentTest()
      setAgentStatus(status)
      onHealthRefresh?.()
      notify(
        status.ping_detail ||
          status.detail ||
          (status.ok ? 'Connected to Ollama.' : 'Not connected — is Ollama running?'),
      )
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Test failed'
      notify(
        /not found/i.test(msg)
          ? 'Update StudioNels in Pinokio, then Stop and Start, then Test again.'
          : msg,
      )
    } finally {
      setTesting(false)
    }
  }

  const onProviderChange = (id: AgentProvider) => {
    const meta = providers.find((p) => p.id === id)
    setDraft({
      ...draft,
      agent_provider: id,
      agent_model: draft.agent_model || meta?.default_model || '',
      agent_api_base:
        id === 'ollama'
          ? draft.ollama_url || meta?.default_base || ''
          : draft.agent_api_base || meta?.default_base || '',
      ollama_model: id === 'ollama' ? draft.agent_model || draft.ollama_model : draft.ollama_model,
    })
  }

  const statusTone = agentStatus?.ok
    ? 'ok'
    : agentStatus?.reachable
      ? 'warn'
      : agentStatus
        ? 'bad'
        : ''

  return (
    <div>
      <p className="hint">
        On a 32GB Radeon, choose the R9700 preset. Keep model loaded stays off so the GPU is quiet
        until you generate. Agent can use Ollama on this PC, or a cloud model if you add a key.
      </p>
      <div className="settings-grid panel">
        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <label>Memory profile (where models sit)</label>
          <p className="muted tiny" style={{ marginTop: 4 }}>
            Pick low→high VRAM. Low profiles keep weights in system RAM and stream layers to the GPU;
            high profiles keep the whole model in VRAM for speed.
          </p>
          <div className="mode-grid" style={{ marginTop: 10 }}>
            {presets.map((p) => {
              const mem = (p as Preset & { memory?: { placement_label?: string; blurb?: string } }).memory
              const active = draft.preset_id === p.id
              return (
                <button
                  key={p.id}
                  type="button"
                  className={`mode-chip ${active ? 'active' : ''}`}
                  onClick={() =>
                    setDraft({
                      ...draft,
                      preset_id: p.id,
                      cpu_offload: p.generation?.cpu_offload ?? p.target_vram_gb < 20,
                    })
                  }
                >
                  <strong>{p.label}</strong>
                  <span>
                    ~{p.target_vram_gb} GB
                    {mem?.placement_label ? ` · ${mem.placement_label}` : ''}
                  </span>
                </button>
              )
            })}
          </div>
          {presets.find((p) => p.id === draft.preset_id)?.notes && (
            <p className="muted tiny" style={{ marginTop: 8 }}>
              {presets.find((p) => p.id === draft.preset_id)?.notes}
            </p>
          )}
        </div>

        <h3 style={{ gridColumn: '1 / -1', margin: '8px 0 0' }}>Agent LLM</h3>

        <div
          className={`agent-status-banner ${statusTone}`}
          style={{ gridColumn: '1 / -1' }}
        >
          <div className="agent-status-row">
            <span className={`agent-dot ${statusTone || 'bad'}`} aria-hidden />
            <div>
              <strong>
                {agentStatus?.ok
                  ? 'Connected'
                  : agentStatus?.reachable
                    ? 'Partly connected'
                    : agentStatus
                      ? 'Not connected'
                      : 'Checking…'}
              </strong>
              <p className="muted tiny" style={{ margin: '4px 0 0' }}>
                {agentStatus?.ping_detail ||
                  agentStatus?.detail ||
                  health?.agent_detail ||
                  'Open Settings → Agent LLM, pick Ollama, then Test connection.'}
              </p>
              {agentStatus?.models && agentStatus.models.length > 0 ? (
                <p className="muted tiny" style={{ margin: '6px 0 0' }}>
                  Installed models: {agentStatus.models.join(', ')}
                </p>
              ) : null}
            </div>
          </div>
          <button
            className="btn ghost"
            type="button"
            disabled={testing}
            onClick={() => void testConnection()}
          >
            {testing ? 'Testing…' : 'Test connection'}
          </button>
        </div>

        <div className="field" style={{ gridColumn: '1 / -1' }}>
          <label>Provider</label>
          <div className="provider-grid">
            {(providers.length
              ? providers
              : [
                  { id: 'builtin' as const, label: 'Built-in', blurb: '', needs_key: false, default_model: '', default_base: '' },
                  { id: 'ollama' as const, label: 'Ollama', blurb: '', needs_key: false, default_model: '', default_base: '' },
                  { id: 'openai' as const, label: 'OpenAI', blurb: '', needs_key: true, default_model: '', default_base: '' },
                  { id: 'anthropic' as const, label: 'Anthropic', blurb: '', needs_key: true, default_model: '', default_base: '' },
                  { id: 'openrouter' as const, label: 'OpenRouter', blurb: '', needs_key: true, default_model: '', default_base: '' },
                  { id: 'custom' as const, label: 'Custom', blurb: '', needs_key: true, default_model: '', default_base: '' },
                ]
            ).map((p) => (
              <button
                key={p.id}
                type="button"
                className={`mode-chip ${draft.agent_provider === p.id ? 'active' : ''}`}
                onClick={() => onProviderChange(p.id)}
              >
                <strong>{p.label}</strong>
                <span>{p.blurb || (p.needs_key ? 'Paid API' : 'Free / local')}</span>
              </button>
            ))}
          </div>
        </div>

        {(draft.agent_provider === 'ollama' || draft.agent_provider === 'builtin') && (
          <>
            <div className="field">
              <label>Ollama URL</label>
              <input
                value={draft.ollama_url}
                onChange={(e) =>
                  setDraft({ ...draft, ollama_url: e.target.value, agent_api_base: e.target.value })
                }
                disabled={draft.agent_provider === 'builtin'}
              />
            </div>
            <div className="field">
              <label>Ollama / agent model</label>
              {agentStatus?.models && agentStatus.models.length > 0 && draft.agent_provider === 'ollama' ? (
                <select
                  value={
                    agentStatus.models.includes(draft.agent_model || draft.ollama_model)
                      ? draft.agent_model || draft.ollama_model
                      : agentStatus.models[0]
                  }
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      agent_model: e.target.value,
                      ollama_model: e.target.value,
                    })
                  }
                >
                  {agentStatus.models.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  value={draft.agent_model || draft.ollama_model}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      agent_model: e.target.value,
                      ollama_model: e.target.value,
                    })
                  }
                  disabled={draft.agent_provider === 'builtin'}
                  placeholder="llama3.2:3b"
                />
              )}
            </div>
          </>
        )}

        {selected?.needs_key ||
        ['openai', 'anthropic', 'openrouter', 'custom'].includes(draft.agent_provider) ? (
          <>
            <div className="field">
              <label>Model</label>
              <input
                value={draft.agent_model}
                onChange={(e) => setDraft({ ...draft, agent_model: e.target.value })}
                placeholder={selected?.default_model || 'model id'}
              />
            </div>
            <div className="field">
              <label>API base URL</label>
              <input
                value={draft.agent_api_base || selected?.default_base || ''}
                onChange={(e) => setDraft({ ...draft, agent_api_base: e.target.value })}
                placeholder={selected?.default_base || 'https://…'}
              />
            </div>
            <div className="field" style={{ gridColumn: '1 / -1' }}>
              <label>
                API key {draft.agent_api_key_set ? '(saved — leave blank to keep)' : ''}
              </label>
              <input
                type="password"
                autoComplete="off"
                value={keyDraft}
                onChange={(e) => setKeyDraft(e.target.value)}
                placeholder={draft.agent_api_key_set ? '••••••••' : 'sk-…'}
              />
              <div className="muted tiny">
                Stored only in your local StudioNels settings file — never sent to StudioNels
                cloud. Falls back to built-in planner if the call fails.
              </div>
            </div>
          </>
        ) : null}

        <div className="field">
          <label>Default generate mode</label>
          <select
            value={draft.default_gen_mode}
            onChange={(e) => setDraft({ ...draft, default_gen_mode: e.target.value })}
          >
            {['t2i', 't2v', 'i2v', 'ref2i', 'ref2v'].map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <label className="muted">
          <input
            type="checkbox"
            checked={draft.cpu_offload}
            onChange={(e) => setDraft({ ...draft, cpu_offload: e.target.checked })}
          />{' '}
          Keep the text encoder in RAM (saves GPU)
        </label>
        <label className="muted">
          <input
            type="checkbox"
            checked={draft.keep_model_loaded === true}
            onChange={(e) => setDraft({ ...draft, keep_model_loaded: e.target.checked })}
          />{' '}
          Keep the last model loaded after Generate
        </label>
        <div className="muted tiny" style={{ gridColumn: '1 / -1' }}>
          The engine stays open like Wan2GP, so the next clip skips the long load. Opening the app
          does not put a model on the GPU. Uncheck this to drop the weights after a clip.
        </div>
        <div className="muted" style={{ gridColumn: '1 / -1' }}>
          Engine: built-in · Torch: {health?.torch ? 'yes' : 'no'} · GPU:{' '}
          {health?.gpu ? health.device_name : 'not ready'} · Agent:{' '}
          {agentStatus?.detail || health?.agent_detail || health?.agent_label || '—'} · Data:{' '}
          {health?.data_dir}
        </div>
        <div className="cta-row" style={{ gridColumn: '1 / -1' }}>
          <button className="btn acid" type="button" onClick={() => void save()}>
            Save settings
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={testing}
            onClick={() => void testConnection()}
          >
            {testing ? 'Testing…' : 'Test connection'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ContinuityTab({
  project,
  setProject,
  busy,
  setBusy,
  notify,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
}) {
  const [data, setData] = useState<ContinuityData | null>(null)
  const [rulesText, setRulesText] = useState('')
  const [threshold, setThreshold] = useState(0.55)

  const refresh = async () => {
    const c = await api.getContinuity(project.id)
    setData(c)
    setRulesText((c.rules || []).join('\n'))
    setThreshold(c.auto_reject_below ?? 0.55)
  }

  useEffect(() => {
    refresh().catch((e) => notify(String(e.message || e)))
  }, [project.id, project.takes.length, project.characters.length])

  const save = async () => {
    setBusy(true)
    try {
      const p = await api.putContinuity(project.id, {
        rules: rulesText
          .split('\n')
          .map((r) => r.trim())
          .filter(Boolean),
        auto_reject_below: threshold,
        rebuild_bible: true,
      })
      setProject(p)
      await refresh()
      notify('Continuity bible updated + takes rescored.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Continuity brain keeps cast locks and scene rules glued across takes. Scores are prompt-lock
        heuristics offline; vision scoring can plug in later.
      </p>
      <div className="gen-layout">
        <div className="panel">
          <h3>World bible</h3>
          <pre className="bible">{data?.world_bible || data?.bible?.text || 'Building…'}</pre>
          <div className="field">
            <label>Extra rules (one per line)</label>
            <textarea rows={5} value={rulesText} onChange={(e) => setRulesText(e.target.value)} />
          </div>
          <div className="field">
            <label>Auto-reject below {Math.round(threshold * 100)}%</label>
            <input
              type="range"
              min={0.2}
              max={0.9}
              step={0.05}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
            />
          </div>
          <div className="inline-actions">
            <button className="btn acid" type="button" disabled={busy} onClick={save}>
              Save & rescore
            </button>
            <button
              className="btn ghost"
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true)
                try {
                  const p = await api.rescoreContinuity(project.id)
                  setProject(p)
                  await refresh()
                  notify('Rescored all takes.')
                } finally {
                  setBusy(false)
                }
              }}
            >
              Rescore only
            </button>
          </div>
        </div>
        <div className="panel">
          <h3>Take scores</h3>
          <div className="job-list">
            {(data?.takes || []).length === 0 && <div className="empty">No takes yet.</div>}
            {(data?.takes || []).map((t) => (
              <div className={`job-item ${t.rejected ? 'rejected' : ''}`} key={t.id}>
                <header>
                  <strong>{t.label}</strong>
                  <span className={`badge ${t.rejected ? 'failed' : 'done'}`}>
                    {t.continuity_score != null
                      ? `${Math.round(t.continuity_score * 100)}%`
                      : '—'}
                  </span>
                </header>
                {(t.continuity_flags || []).map((f) => (
                  <div className="muted tiny" key={f}>
                    {f}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function RehearsalTab({
  project,
  setProject,
  busy,
  setBusy,
  notify,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
}) {
  const [takesPer, setTakesPer] = useState(2)
  const rehearsals = project.takes.filter((t) => t.is_rehearsal)

  const run = async () => {
    if (!project.shots.length) {
      notify('Add shots first (Agent or Shots tab).')
      return
    }
    setBusy(true)
    try {
      const p = await api.rehearsal(project.id, {
        takes_per_shot: takesPer,
        quality: 'draft',
      })
      setProject(p)
      notify(`Rehearsal queued · ${takesPer} draft take(s) per shot.`)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Greybox pass — cheap draft takes for blocking and timing before you spend VRAM on finals.
        Promote winners, then finish them in Video & image or Film → Takes.
      </p>
      <div className="panel">
        <div className="controls-grid">
          <div className="field">
            <label>Takes per shot</label>
            <input
              type="number"
              min={1}
              max={4}
              value={takesPer}
              onChange={(e) => setTakesPer(Number(e.target.value))}
            />
          </div>
        </div>
        <div className="inline-actions" style={{ flexWrap: 'wrap', gap: 8 }}>
          <button className="btn acid" type="button" disabled={busy} onClick={run}>
            Run rehearsal pass ({project.shots.length} shots)
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true)
              try {
                const res = await api.filmNight(project.id, 'full')
                if (res.project) setProject(res.project as Project)
                else {
                  const p = await api.getProject(project.id)
                  setProject(p)
                }
                notify(res.message || 'Film night running.')
              } catch (err) {
                notify(String((err as Error).message || err))
              } finally {
                setBusy(false)
              }
            }}
          >
            Film night (rehearse → finals → stitch)
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={busy || rehearsals.length === 0}
            onClick={async () => {
              setBusy(true)
              try {
                const res = await api.filmNight(project.id, 'promote')
                if (res.project) setProject(res.project as Project)
                notify(res.message || 'Promoted winners.')
              } catch (err) {
                notify(String((err as Error).message || err))
              } finally {
                setBusy(false)
              }
            }}
          >
            Promote winners → queue finals
          </button>
        </div>
      </div>
      <div className="takes-grid" style={{ marginTop: 20 }}>
        {rehearsals.length === 0 && <div className="empty">No rehearsal takes yet.</div>}
        {rehearsals.map((take) => {
          const shot = project.shots.find((s) => s.id === take.shot_id)
          return (
            <div className="take-card" key={take.id}>
              {mediaUrl(take.media_path) && (
                <img src={mediaUrl(take.media_path)} alt={take.label} />
              )}
              <div className="body">
                <strong>
                  {shot ? `${shot.index + 1}. ${shot.title}` : take.label}
                </strong>
                <div className="muted tiny">{take.score_note}</div>
                <button
                  className="btn acid"
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true)
                    try {
                      const p = await api.promoteTake(project.id, take.id)
                      setProject(p)
                      notify('Promoted to Director pin.')
                    } finally {
                      setBusy(false)
                    }
                  }}
                >
                  Promote winner
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function InspirationTab({
  onTry,
  busy,
}: {
  onTry: (clip: InspirationClip) => void
  busy?: boolean
}) {
  return (
    <div>
      <p className="hint">
        Press <em>Use this prompt</em>. It fills Video & image and waits. Nothing renders until you
        press Generate. Cards that need a photo say so.
      </p>
      <div className="inspire-grid">
        {INSPIRATION_CLIPS.map((clip) => {
          const now = inspirationRunsNow(clip.mode)
          return (
            <article key={clip.id} className="inspire-card" style={{ ['--accent' as string]: clip.accent }}>
              <div className="inspire-clip" aria-hidden>
                <div className="inspire-scan" />
                <span className="inspire-mode">{clip.mode.toUpperCase()}</span>
                <span className="inspire-dur">{clip.durationHint}</span>
              </div>
              <div className="inspire-body">
                <h3>{clip.title}</h3>
                <p>{clip.blurb}</p>
                <div className="muted tiny">{clip.vibe}</div>
                <button className="btn acid" type="button" disabled={busy} onClick={() => onTry(clip)}>
                  {now ? 'Use this prompt' : 'Add a photo'}
                </button>
              </div>
            </article>
          )
        })}
      </div>
    </div>
  )
}

function TimeStyleTab({
  project,
  setProject,
  notify,
}: {
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
}) {
  const [duration, setDuration] = useState(project.target_duration_sec || 60)
  const [customMin, setCustomMin] = useState(Math.floor((project.target_duration_sec || 60) / 60))
  const [styleId, setStyleId] = useState(project.visual_style || 'cinematic')
  const [frameId, setFrameId] = useState(project.frame_size_id || '16:9-draft')
  const [imageFormat, setImageFormat] = useState(project.image_format || 'png')
  const [videoFormat, setVideoFormat] = useState(project.video_format || 'mp4')
  const [audioFormat, setAudioFormat] = useState(project.audio_format || 'wav')
  const [recipes, setRecipes] = useState<RecipeInfo[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDuration(project.target_duration_sec || 60)
    setStyleId(project.visual_style || 'cinematic')
    setFrameId(project.frame_size_id || '16:9-draft')
    setImageFormat(project.image_format || 'png')
    setVideoFormat(project.video_format || 'mp4')
    setAudioFormat(project.audio_format || 'wav')
  }, [project])

  useEffect(() => {
    api.recipes().then((r) => setRecipes(r.recipes || [])).catch(() => undefined)
  }, [])

  const shotTotal = project.shots.reduce((sum, s) => sum + (s.duration_sec || 0), 0)

  const save = async (extra?: Partial<Project>) => {
    setBusy(true)
    try {
      const frame = frameById(frameId)
      const next = {
        ...project,
        target_duration_sec: duration,
        visual_style: styleId,
        frame_size_id: frame.id,
        aspect_ratio: frame.ratio,
        width: frame.width,
        height: frame.height,
        image_format: imageFormat,
        video_format: videoFormat,
        audio_format: audioFormat,
        ...extra,
      }
      const p = await api.putProject(next)
      setProject(p)
      notify('Time & style saved.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const applyToShots = async () => {
    if (!project.shots.length) {
      notify('Plan shots with the Agent first.')
      return
    }
    const n = project.shots.length
    const each = Math.max(1, Math.round((duration / n) * 10) / 10)
    setBusy(true)
    try {
      let p = project
      for (const shot of project.shots) {
        p = await api.patchShot(project.id, shot.id, { duration_sec: each })
      }
      const next = {
        ...p,
        target_duration_sec: duration,
        visual_style: styleId,
        image_format: imageFormat,
        video_format: videoFormat,
        audio_format: audioFormat,
      }
      p = await api.putProject(next)
      setProject(p)
      notify(`Spread ${formatDuration(duration)} across ${n} shots (~${each}s each).`)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Set the <strong>whole</strong> length, frame size (landscape / portrait / 1:1…), look, and
        save formats. Generate + Film night use these dimensions.
      </p>

      <div className="panel" style={{ marginBottom: 16 }}>
        <h3>Video size</h3>
        <div className="muted tiny" style={{ marginBottom: 10 }}>
          Current: {frameById(frameId).label} · {frameById(frameId).width}×{frameById(frameId).height}
        </div>
        {(['landscape', 'square', 'portrait'] as const).map((ori) => (
          <div key={ori} style={{ marginBottom: 12 }}>
            <div className="section-label" style={{ textTransform: 'capitalize' }}>
              {ori}
            </div>
            <div className="mode-grid">
              {framesByOrientation(ori).map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`mode-chip ${frameId === f.id ? 'active' : ''}`}
                  onClick={() => setFrameId(f.id)}
                >
                  <strong>{f.ratio}</strong>
                  <span>
                    {f.width}×{f.height} — {f.blurb}
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
        <button
          className="btn acid"
          type="button"
          disabled={busy}
          onClick={() => save()}
          style={{ marginTop: 4 }}
        >
          Save frame size
        </button>
      </div>

      {recipes.length > 0 && (
        <div className="panel" style={{ marginBottom: 16 }}>
          <h3>Recipes</h3>
          <div className="mode-grid">
            {recipes.map((r) => (
              <button
                key={r.id}
                type="button"
                className="mode-chip"
                disabled={busy}
                onClick={async () => {
                  setBusy(true)
                  try {
                    const p = await api.applyRecipe(project.id, r.id)
                    setProject(p)
                    setFrameId(p.frame_size_id || frameId)
                    notify(`Recipe · ${r.title}`)
                  } catch (err) {
                    notify(String((err as Error).message || err))
                  } finally {
                    setBusy(false)
                  }
                }}
              >
                <strong>{r.title}</strong>
                <span>{r.blurb}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="two-col">
        <div className="panel">
          <h3>Total runtime</h3>
          <div className="mode-grid">
            {DURATION_PRESETS.filter((d) => d.id !== 'custom').map((d) => (
              <button
                key={d.id}
                type="button"
                className={`mode-chip ${duration === d.seconds ? 'active' : ''}`}
                onClick={() => {
                  setDuration(d.seconds)
                  setCustomMin(Math.floor(d.seconds / 60))
                }}
              >
                <strong>{d.label}</strong>
                <span>
                  {formatDuration(d.seconds)} — {d.hint}
                </span>
              </button>
            ))}
          </div>
          <div className="field" style={{ marginTop: 14 }}>
            <label>Custom length (minutes)</label>
            <input
              type="number"
              min={0.1}
              step={0.5}
              value={customMin}
              onChange={(e) => {
                const mins = Number(e.target.value)
                setCustomMin(mins)
                setDuration(Math.max(1, Math.round(mins * 60)))
              }}
            />
          </div>
          <div className="muted">
            Target: <strong>{formatDuration(duration)}</strong>
            {project.shots.length > 0 && (
              <>
                {' '}
                · Current shot list adds up to {formatDuration(shotTotal)}
              </>
            )}
          </div>
          <div className="inline-actions" style={{ marginTop: 12 }}>
            <button className="btn acid" type="button" disabled={busy} onClick={() => save()}>
              Save timing
            </button>
            <button className="btn" type="button" disabled={busy} onClick={applyToShots}>
              Spread across shots
            </button>
          </div>
        </div>

        <div className="panel">
          <h3>Visual style</h3>
          <div className="mode-grid">
            {VISUAL_STYLES.map((s) => (
              <button
                key={s.id}
                type="button"
                className={`mode-chip ${styleId === s.id ? 'active' : ''}`}
                onClick={() => setStyleId(s.id)}
              >
                <strong>{s.label}</strong>
                <span>{s.blurb}</span>
              </button>
            ))}
          </div>

          <h3 style={{ marginTop: 18 }}>Save formats</h3>
          <div className="controls-grid">
            <div className="field">
              <label>Image</label>
              <select value={imageFormat} onChange={(e) => setImageFormat(e.target.value as Project['image_format'])}>
                <option value="png">PNG</option>
                <option value="jpg">JPG</option>
                <option value="webp">WebP</option>
              </select>
            </div>
            <div className="field">
              <label>Video</label>
              <select value={videoFormat} onChange={(e) => setVideoFormat(e.target.value as Project['video_format'])}>
                <option value="mp4">MP4</option>
                <option value="webm">WebM</option>
                <option value="gif">GIF</option>
              </select>
            </div>
            <div className="field">
              <label>Audio</label>
              <select value={audioFormat} onChange={(e) => setAudioFormat(e.target.value as Project['audio_format'])}>
                <option value="wav">WAV</option>
                <option value="mp3">MP3</option>
              </select>
            </div>
          </div>
          <button className="btn acid" type="button" disabled={busy} onClick={() => save()} style={{ marginTop: 8 }}>
            Save style & formats
          </button>
        </div>
      </div>
    </div>
  )
}

function CreatorTab({
  project,
  setProject,
  notify,
  health,
}: {
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
  health: Health | null
}) {
  const [name, setName] = useState('Mira')
  const [role, setRole] = useState('lead')
  const [extra, setExtra] = useState('silver jacket, memorable silhouette')
  const [characterLock, setCharacterLock] = useState(
    'oval face, soft jaw, small beauty mark under left eye, steady gaze',
  )
  const [traits, setTraits] = useState<Record<string, string>>({ ...DEFAULT_TRAITS })
  const [busy, setBusy] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [lastLook, setLastLook] = useState('')
  const style = VISUAL_STYLES.find((s) => s.id === project.visual_style)

  const built = buildCharacterPrompt(name, traits, extra, style?.prompt_suffix, characterLock)

  const setTrait = (groupId: string, optionId: string) => {
    setTraits((prev) => ({ ...prev, [groupId]: optionId }))
  }

  const generateCharacter = async () => {
    setBusy(true)
    try {
      const { look, prompt } = buildCharacterPrompt(
        name,
        traits,
        extra,
        style?.prompt_suffix,
        characterLock,
      )
      setLastLook(look)

      // Create or update a matching character profile
      let character = project.characters.find(
        (c) => c.name.trim().toLowerCase() === name.trim().toLowerCase(),
      )
      let p = project
      if (character) {
        character = {
          ...character,
          role,
          look,
          character_lock: characterLock,
          personality: character.personality || traits.vibe || '',
        }
        p = await api.updateCharacter(project.id, character)
      } else {
        p = await api.addCharacter(project.id, {
          name: name.trim() || 'Character',
          role,
          look,
          personality: traits.vibe || '',
          voice_notes: '',
          character_lock: characterLock,
          tags: ['creator'],
        })
        character = p.characters.find(
          (c) => c.name.trim().toLowerCase() === (name.trim() || 'character').toLowerCase(),
        )
      }
      setProject(p)

      const job = await api.engineGenerate({
        mode: 't2i',
        model_id: 'sdxl-turbo',
        prompt,
        project_id: project.id,
        width: 768,
        height: 1024,
        quality: 'balanced',
        image_format: project.image_format || 'png',
        visual_style: project.visual_style,
      })

      // Wait briefly for preview/local jobs
      let done = job
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 400))
        done = await api.engineJob(job.id)
        if (done.status === 'done' || done.status === 'failed') break
      }

      if (done.status === 'failed') {
        notify(done.error || 'Character generation failed.')
        return
      }

      const media = done.thumb_path || done.media_path
      if (media && character) {
        const latest = await api.getProject(project.id)
        const fresh = latest.characters.find((c) => c.id === character!.id) || character
        p = await api.updateCharacter(project.id, {
          ...fresh,
          look,
          role,
          character_lock: characterLock,
          reference_path: media,
        })
        setProject(p)
        setPreviewUrl(mediaUrl(media) || null)
        notify(`Created ${name} — lock + ref saved. Edit anytime in Characters.`)
      } else {
        notify('Generated — open Characters if the ref needs a refresh.')
        const latest = await api.getProject(project.id)
        setProject(latest)
      }
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Sims-style character creator — pick skin, eyes, hair, build, write a character lock, then
        generate. Uses your Time tab style ({style?.label || 'cinematic'}).
        {health?.gpu ? '' : ' Preview mode until an image model is installed.'}
      </p>

      <div className="gen-layout">
        <div className="panel gen-panel">
          <div className="controls-grid">
            <div className="field">
              <label>Name</label>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label>Role</label>
              <input value={role} onChange={(e) => setRole(e.target.value)} placeholder="lead / rival / guide" />
            </div>
          </div>

          <div className="lock-box">
            <label>Character lock</label>
            <p className="muted tiny">
              Short identity notes that stay the same every generation (face marks, bone structure,
              signature details).
            </p>
            <textarea
              rows={3}
              value={characterLock}
              onChange={(e) => setCharacterLock(e.target.value)}
              placeholder="e.g. oval face, soft jaw, beauty mark under left eye, steady gaze…"
            />
          </div>

          {CHARACTER_TRAITS.map((group) => (
            <div key={group.id} style={{ marginBottom: 14 }}>
              <div className="section-label" style={{ marginBottom: 8 }}>
                {group.label}
              </div>
              <div className="accent-grid">
                {group.options.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={`accent-chip ${traits[group.id] === opt.id ? 'active' : ''}`}
                    onClick={() => setTrait(group.id, opt.id)}
                  >
                    <strong>{opt.label}</strong>
                  </button>
                ))}
              </div>
            </div>
          ))}

          <div className="field">
            <label>Extra details (clothes, props…)</label>
            <textarea rows={2} value={extra} onChange={(e) => setExtra(e.target.value)} />
          </div>

          <div className="muted tiny" style={{ marginBottom: 10 }}>
            Look recipe: {built.look}
          </div>

          <button className="btn acid" type="button" disabled={busy} onClick={generateCharacter}>
            {busy ? 'Generating…' : 'Generate character'}
          </button>
        </div>

        <div className="panel">
          <h3>Preview</h3>
          {previewUrl ? (
            <img className="upload-preview" src={previewUrl} alt={name} style={{ maxHeight: 420 }} />
          ) : (
            <div className="inspire-clip" style={{ height: 280, borderRadius: 14, ['--accent' as string]: '#ff3dce' }}>
              <div className="inspire-scan" />
              <span className="inspire-mode">CREATOR</span>
              <span className="inspire-dur">{name || 'Character'}</span>
            </div>
          )}
          <div className="muted" style={{ marginTop: 12 }}>
            {lastLook || 'Pick traits, then generate. The result becomes an editable character ref.'}
          </div>
        </div>
      </div>
    </div>
  )
}

function AudioTab({
  project,
  setProject,
  notify,
  health,
}: {
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
  health: Health | null
}) {
  const [kind, setKind] = useState<AudioKind>('music')
  const [accentId, setAccentId] = useState('british-rp')
  const [mood, setMood] = useState('dreamy')
  const [lyrics, setLyrics] = useState('')
  const [prompt, setPrompt] = useState('rainy neon city underscore with soft synth pulses')
  const [durationSec, setDurationSec] = useState(8)
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 1_000_000_000))
  const [shotId, setShotId] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobs, setJobs] = useState<EngineJob[]>([])
  const [voiceDesc, setVoiceDesc] = useState('young woman, quiet and determined')
  const [installed, setInstalled] = useState<Set<string>>(new Set())

  useEffect(() => {
    api
      .engineModels()
      .then((pack) => setInstalled(new Set(pack.models.filter((m) => m.installed).map((m) => m.id))))
      .catch(() => undefined)
  }, [])

  const kindMeta = AUDIO_KINDS.find((k) => k.id === kind)!
  // Best installed model for each kind (the old fixed picks sent sound effects to
  // AudioGen, which the engine cannot run).
  const pickModel = (): string => {
    const first = (...ids: string[]) => ids.find((id) => installed.has(id)) || ids[ids.length - 1]
    if (kind === 'voice') return 'voxcpm2'
    if (kind === 'sfx' || kind === 'ambience') return first('stable-audio-3-sfx', 'stable-audio-open')
    if (kind === 'song') return first('ace-step-1.5', 'stable-audio-song')
    return first('ace-step-1.5', 'stable-audio-open')
  }
  const usesAce = pickModel() === 'ace-step-1.5'
  const accent = VOICE_ACCENTS.find((a) => a.id === accentId) || VOICE_ACCENTS[0]

  const prevDone = useRef(0)
  useEffect(() => {
    const tick = async () => {
      try {
        const list = (await api.engineJobs()).filter((j) => j.mode === 't2a')
        setJobs(list)
        const done = list.filter((j) => j.status === 'done' && j.media_path).length
        if (done > prevDone.current) {
          const p = await api.getProject(project.id)
          setProject(p)
        }
        prevDone.current = done
      } catch {
        /* ignore */
      }
    }
    tick()
    const t = window.setInterval(tick, 2000)
    return () => window.clearInterval(t)
  }, [project.id, setProject])

  const buildPrompt = () => {
    // VoxCPM2 reads the voice from brackets in front of the line
    if (kind === 'voice') return `(${voiceDesc.trim() || 'natural voice'})${prompt.trim()}`
    const parts = [kindMeta.prompt_prefix, prompt.trim()]
    parts.push(`${mood} mood`)
    if (kind === 'song') {
      parts.push(accent.prompt_hint)
      // ACE-Step sings real lyrics given after a "Lyrics:" line
      if (lyrics.trim() && !usesAce) parts.push(`lyrics idea: ${lyrics.trim()}`)
    }
    if (kind === 'score') {
      parts.push(`for a ${project.visual_style || 'cinematic'} ${project.mode.replace('_', ' ')}`)
    }
    const text = parts.filter(Boolean).join(', ')
    return kind === 'song' && usesAce && lyrics.trim() ? `${text}\nLyrics:\n${lyrics.trim()}` : text
  }

  const run = async () => {
    if (!prompt.trim()) {
      notify('Describe the music, song, or sound first.')
      return
    }
    setBusy(true)
    try {
      const modelId = pickModel()
      const job = await api.engineGenerate({
        mode: 't2a',
        model_id: modelId,
        prompt: buildPrompt(),
        duration_sec: durationSec,
        seed,
        project_id: project.id,
        shot_id: shotId || undefined,
        audio_format: project.audio_format || 'wav',
        quality: 'balanced',
      })
      notify(
        `Audio queued · ${kindMeta.label} · when ready it appears here and in Sampling → Library`,
      )
      setSeed(Math.floor(Math.random() * 1_000_000_000))
      setJobs((prev) => [job, ...prev])
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Music, songs, scores, ambience, and sound effects. Finished clips show up here and under Film → Takes.
        {health?.gpu ? ` GPU: ${health.device_name}.` : ' Preview tones until an audio model is installed.'}
      </p>

      <div className="gen-layout">
        <div className="panel gen-panel">
          <h3>What to make</h3>
          <div className="mode-grid">
            {AUDIO_KINDS.map((k) => (
              <button
                key={k.id}
                type="button"
                className={`mode-chip ${kind === k.id ? 'active' : ''}`}
                onClick={() => setKind(k.id)}
              >
                <strong>{k.label}</strong>
                <span>{k.blurb}</span>
              </button>
            ))}
          </div>

          {kind === 'voice' && (
            <div className="field" style={{ marginTop: 14 }}>
              <label>Voice</label>
              <input
                value={voiceDesc}
                onChange={(e) => setVoiceDesc(e.target.value)}
                placeholder="old man, gravelly, tired — or: young woman, warm, slightly amused"
              />
            </div>
          )}

          <div className="field" style={{ marginTop: 14 }}>
            <label>{kind === 'voice' ? 'Line to say' : 'Description'}</label>
            <textarea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={
                kind === 'voice'
                  ? 'We close at nine. Come back tomorrow.'
                  : kind === 'song'
                    ? 'A late-night pop song about glass jars of memories…'
                    : 'Describe the music or sound…'
              }
            />
          </div>

          <div className="controls-grid">
            {kind !== 'voice' && (
              <div className="field">
                <label>Mood</label>
                <select value={mood} onChange={(e) => setMood(e.target.value)}>
                  {MUSIC_MOODS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {kind !== 'voice' && (
              <div className="field">
                <label>Length (sec)</label>
                <input
                  type="number"
                  min={usesAce ? 10 : 2}
                  max={usesAce ? 240 : 30}
                  step={1}
                  value={durationSec}
                  onChange={(e) => setDurationSec(Number(e.target.value))}
                />
              </div>
            )}
            <div className="field">
              <label>Seed</label>
              <div className="inline-actions" style={{ gap: 6 }}>
                <input
                  type="number"
                  min={0}
                  value={seed}
                  onChange={(e) => setSeed(Math.max(0, Number(e.target.value) || 0))}
                  style={{ flex: 1, minWidth: 0 }}
                />
                <button
                  className="btn ghost tiny"
                  type="button"
                  onClick={() => setSeed(Math.floor(Math.random() * 1_000_000_000))}
                >
                  Random
                </button>
              </div>
            </div>
          </div>

          {kind === 'song' && (
            <>
              <h3 style={{ marginTop: 8 }}>Voice accent</h3>
              <div className="accent-grid">
                {VOICE_ACCENTS.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className={`accent-chip ${accentId === a.id ? 'active' : ''}`}
                    onClick={() => setAccentId(a.id)}
                  >
                    <strong>{a.label}</strong>
                    <span>{a.region}</span>
                  </button>
                ))}
              </div>
              <div className="field" style={{ marginTop: 12 }}>
                <label>{usesAce ? 'Lyrics (sung as written — use [verse] / [chorus])' : 'Lyrics idea (optional)'}</label>
                <textarea
                  rows={3}
                  value={lyrics}
                  onChange={(e) => setLyrics(e.target.value)}
                  placeholder={'Verse / chorus lines…\n“I carry light in jars of rain…”'}
                />
              </div>
            </>
          )}

          <div className="field">
            <label>Attach to shot (optional)</label>
            <select value={shotId} onChange={(e) => setShotId(e.target.value)}>
              <option value="">— standalone audio —</option>
              {project.shots.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.index + 1}. {s.title}
                </option>
              ))}
            </select>
          </div>

          <div className="muted tiny" style={{ marginBottom: 10 }}>
            Prompt preview: {buildPrompt().slice(0, 160)}
            {buildPrompt().length > 160 ? '…' : ''}
          </div>

          <button className="btn acid" type="button" disabled={busy} onClick={run}>
            Generate {kindMeta.label}
          </button>
        </div>

        <div className="panel">
          <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Audio queue</h3>
            {jobs.some((j) => j.status === 'done' || j.status === 'failed' || j.status === 'cancelled') && (
              <button
                className="btn ghost tiny"
                type="button"
                onClick={async () => {
                  try {
                    const r = await api.engineClearFinishedJobs()
                    notify(`Removed ${r.removed} finished job(s)`)
                    setJobs((await api.engineJobs()).filter((j) => j.mode === 't2a'))
                  } catch (err) {
                    notify(String((err as Error).message || err))
                  }
                }}
              >
                Clear finished
              </button>
            )}
          </div>
          <div className="job-list">
            {jobs.length === 0 && <div className="empty">No audio jobs yet.</div>}
            {jobs.map((job) => (
              <div className="job-item" key={job.id}>
                <header>
                  <strong>{job.model_label}</strong>
                  <div className="job-item-actions">
                    <span className={`badge ${job.status}`}>{job.status}</span>
                    <button
                      type="button"
                      className="btn ghost tiny"
                      title="Remove from queue"
                      onClick={async () => {
                        try {
                          await api.engineDismissJob(job.id)
                          setJobs((await api.engineJobs()).filter((j) => j.mode === 't2a'))
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        }
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </header>
                <div className="muted">{job.prompt}</div>
                <div className="muted tiny">
                  {job.status === 'done'
                    ? 'Audio ready — play below, or open Sampling → Library'
                    : job.message}
                </div>
                <div className="progress">
                  <div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
                </div>
                {job.media_path && (
                  <div style={{ marginTop: 8 }}>
                    <audio controls src={mediaUrl(job.media_path)} style={{ width: '100%' }} />
                    <div className="inline-actions" style={{ marginTop: 8, flexWrap: 'wrap', gap: 8 }}>
                      <a
                        className="btn ghost tiny"
                        href={mediaUrl(job.media_path) || '#'}
                        download
                      >
                        Download
                      </a>
                      <button
                        type="button"
                        className="btn acid tiny"
                        onClick={async () => {
                          try {
                            const r = await api.engineJobSaveToProject(job.id, project.id, shotId || undefined)
                            setProject(r.project)
                            notify(r.hint || 'Saved to Sampling → Library')
                          } catch (err) {
                            notify(String((err as Error).message || err))
                          }
                        }}
                      >
                        Save to Sampling
                      </button>
                    </div>
                  </div>
                )}
                {job.preview && <div className="muted tiny">Preview tone — install audio model for real music/songs.</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function UpsampleTab({ project, notify }: { project: Project; notify: (m: string) => void }) {
  const [kind, setKind] = useState<'upsample_image' | 'upsample_video'>('upsample_image')
  const [path, setPath] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const run = async () => {
    if (!path) {
      notify('Upload a file first.')
      return
    }
    setBusy(true)
    try {
      const job = await api.engineGenerate({
        mode: kind,
        prompt: 'upsample',
        project_id: project.id,
        image_path: kind === 'upsample_image' ? path : undefined,
        video_path: kind === 'upsample_video' ? path : undefined,
        image_format: project.image_format,
        video_format: project.video_format,
      })
      notify(`Upsample queued · ${job.id}`)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" style={{ maxWidth: 560 }}>
      <h3>Upsample</h3>
      <p className="hint">Enlarge / sharpen a still or clip after drafting.</p>
      <div className="field">
        <label>Type</label>
        <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
          <option value="upsample_image">Image</option>
          <option value="upsample_video">Video</option>
        </select>
      </div>
      <div className="field">
        <label>File</label>
        <input
          type="file"
          accept={kind === 'upsample_image' ? 'image/*' : 'video/*,image/*'}
          onChange={async (e) => {
            const f = e.target.files?.[0]
            if (!f) return
            const up = await api.engineUpload(f)
            setPath(up.path)
            setPreview(up.url)
          }}
        />
        {preview && kind === 'upsample_image' && <img className="upload-preview" src={preview} alt="" />}
      </div>
      <button className="btn acid" type="button" disabled={busy} onClick={run}>
        Upsample
      </button>
    </div>
  )
}

function ModelsTab({
  notify,
  focusTemplates = false,
}: {
  notify: (m: string) => void
  focusTemplates?: boolean
}) {
  const [models, setModels] = useState<EngineModel[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [loras, setLoras] = useState<LoraFile[]>([])
  const [lorasPath, setLorasPath] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [filter, setFilter] = useState<
    'all' | 'big' | 't2i' | 't2v' | 'i2v' | 'ref2i' | 'ref2v' | 't2a' | 'upsample_image' | 'upsample_video'
  >('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'downloaded' | 'not_downloaded'>('all')
  const [customHf, setCustomHf] = useState('rootonchair/LTX-2.3-Distilled-v1.1-Diffusers')
  const [customLabel, setCustomLabel] = useState('LTX-2.3 22B Distilled v1.1')
  const [customKind, setCustomKind] = useState<'video' | 'image' | 'audio' | 'upsample'>('video')
  const [customModes, setCustomModes] = useState<string[]>(['t2v', 'i2v', 'ref2v'])
  const [customVram, setCustomVram] = useState(24)
  const [adding, setAdding] = useState(false)
  const [wan2gpPath, setWan2gpPath] = useState('')
  const [wan2gpBusy, setWan2gpBusy] = useState(false)
  const [wan2gpHint, setWan2gpHint] = useState<string | null>(null)
  const [assets, setAssets] = useState<Wan2gpInventory | null>(null)
  const [templates, setTemplates] = useState<ModelTemplate[]>([])
  const [templateKind, setTemplateKind] = useState<'all' | 'video' | 'image' | 'audio' | 'upsample'>('all')
  const [installingId, setInstallingId] = useState<string | null>(null)
  const [warm, setWarm] = useState<EngineWarmStatus | null>(null)
  const [preloadId, setPreloadId] = useState<string | null>(null)
  const templatesRef = useRef<HTMLDivElement | null>(null)

  const load = async () => {
    const [pack, loraPack, inv, tpl, warmPack] = await Promise.all([
      api.engineModels(),
      api.engineLoras(),
      api.engineAssets().catch(() => null),
      api.engineTemplates().catch(() => null),
      api.engineWarm().catch(() => null),
    ])
    setModels(pack.models)
    setActiveId(pack.active_model_id || null)
    setLoras(loraPack.loras)
    setLorasPath(loraPack.path)
    if (inv) setAssets(inv)
    if (tpl) setTemplates(tpl.templates)
    if (warmPack) setWarm(warmPack)
  }

  useEffect(() => {
    load().catch((e) => notify(String(e.message || e)))
    const t = window.setInterval(() => {
      Promise.all([
        api.engineModels(),
        api.engineTemplates().catch(() => null),
        api.engineWarm().catch(() => null),
      ])
        .then(([pack, tpl, warmPack]) => {
          setModels(pack.models)
          setActiveId(pack.active_model_id || null)
          if (tpl) setTemplates(tpl.templates)
          if (warmPack) setWarm(warmPack)
        })
        .catch(() => undefined)
    }, 5000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    if (focusTemplates) {
      window.setTimeout(() => templatesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }
  }, [focusTemplates])

  const modeFiltered = models.filter((m) => {
    if (filter === 'big') return (m.min_vram_gb || 0) >= 16 || m.tier === 'big'
    if (filter === 'all') return true
    return (m.modes || []).includes(filter as GenMode)
  })

  const dlCounts = modeFiltered.reduce(
    (acc, m) => {
      const st = modelStatus(m)
      if (st === 'installed') acc.downloaded += 1
      else if (st === 'downloading') acc.downloading += 1
      else acc.notDownloaded += 1
      return acc
    },
    { downloaded: 0, notDownloaded: 0, downloading: 0 },
  )

  const shown = modeFiltered.filter((m) => {
    const st = modelStatus(m)
    if (statusFilter === 'downloaded') return st === 'installed'
    if (statusFilter === 'not_downloaded') return st !== 'installed'
    return true
  })

  const kindDefaultModes = (kind: typeof customKind): string[] => {
    if (kind === 'audio') return ['t2a']
    if (kind === 'image') return ['t2i', 'ref2i']
    if (kind === 'upsample') return ['upsample_image', 'upsample_video']
    return ['t2v', 'i2v', 'ref2v']
  }

  const act = async (modelId: string, fn: () => Promise<unknown>, okMsg: string) => {
    setBusyId(modelId)
    try {
      await fn()
      notify(okMsg)
      await load()
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusyId(null)
    }
  }

  const addCustom = async () => {
    setAdding(true)
    try {
      const r = await api.engineModelAddCustom({
        hf_id: customHf.trim(),
        label: customLabel.trim() || undefined,
        kind: customKind,
        modes: customModes.length ? customModes : kindDefaultModes(customKind),
        min_vram_gb: customVram,
        default_steps: customKind === 'video' && /distill/i.test(customHf) ? 8 : 20,
        default_guidance: /distill/i.test(customHf) ? 1 : 5,
        activate: true,
      })
      notify(`Added ${r.model.label} — select it in Generate`)
      setModels(r.models)
      setActiveId(r.model.id)
      await load()
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setAdding(false)
    }
  }

  const shownTemplates = templates.filter(
    (t) => templateKind === 'all' || t.kind === templateKind,
  )

  const installTemplate = async (t: ModelTemplate) => {
    setInstallingId(t.id)
    try {
      const r = await api.engineTemplateInstall(t.id, {
        include_optional: true,
        activate: true,
      })
      setTemplates(r.templates)
      setModels(r.models)
      notify(r.hint || `Downloading ${t.label}…`)
      await load()
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setInstallingId(null)
    }
  }

  return (
    <div>
      <div className="panel" ref={templatesRef}>
        <h3>Model templates</h3>
        <p className="hint">
          Comfy-style packs — click one card to download the Diffusers model plus any listed text
          encoders, VAEs, LoRAs, or upscalers. Progress updates live below.
        </p>
        <div className="mode-grid" style={{ marginTop: 10 }}>
          {(['all', 'video', 'image', 'audio', 'upsample'] as const).map((k) => (
            <button
              key={k}
              type="button"
              className={`mode-chip ${templateKind === k ? 'active' : ''}`}
              onClick={() => setTemplateKind(k)}
            >
              <strong>{k === 'all' ? 'All packs' : k}</strong>
            </button>
          ))}
        </div>
        <div className="template-grid" style={{ marginTop: 14 }}>
          {shownTemplates.map((t) => {
            const pct = Math.round((t.progress || 0) * 100)
            const busy = installingId === t.id || t.download_status === 'downloading'
            return (
              <button
                key={t.id}
                type="button"
                className={`template-card ${t.ready ? 'ready' : ''} ${busy ? 'busy' : ''}`}
                disabled={busy && !t.ready}
                onClick={() => installTemplate(t)}
              >
                <header>
                  <strong>{t.label}</strong>
                  <span className={`badge ${t.ready ? 'done' : busy ? 'queued' : 'queued'}`}>
                    {t.ready ? 'Ready' : busy ? `${pct}%` : 'Install pack'}
                  </span>
                </header>
                <p className="muted tiny">{t.blurb}</p>
                <div className="muted tiny">
                  {t.kind} · ≥{t.min_vram_gb} GB · {(t.modes || []).join(' · ')}
                </div>
                <ul className="template-deps">
                  {(t.components || []).map((c) => (
                    <li key={c.id}>
                      <span>{c.role}</span> {c.label}
                      {c.installed ? ' ✓' : c.required === false ? ' (optional)' : ''}
                    </li>
                  ))}
                </ul>
                {(busy || (t.progress || 0) > 0) && !t.ready && (
                  <div className="progress" style={{ marginTop: 8 }}>
                    <div style={{ width: `${pct}%` }} />
                  </div>
                )}
              </button>
            )
          })}
          {shownTemplates.length === 0 && (
            <div className="empty">No templates in this filter.</div>
          )}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Choose a model</h3>
        <p className="hint">
          Pick a model and press Download. Weights land in <code>models/</code> and show Ready.
          The GPU stays idle until you generate. <strong>Load into studio</strong> is optional if you
          want the next clip to start faster.
        </p>
        {warm?.preloading ? (
          <p className="job-phase tone-load tiny" style={{ marginTop: 8 }}>
            {warm.message || 'Preloading model into RAM/VRAM…'}
          </p>
        ) : warm?.cached?.length ? (
          <p className="job-phase tone-done tiny" style={{ marginTop: 8 }}>
            Ready in studio: {warm.cached[0]}
          </p>
        ) : null}
        <div className="mode-grid" style={{ marginTop: 10 }}>
          {(
            [
              'all',
              'big',
              't2i',
              't2v',
              'i2v',
              'ref2i',
              'ref2v',
              't2a',
              'upsample_image',
              'upsample_video',
            ] as const
          ).map((f) => (
            <button
              key={f}
              type="button"
              className={`mode-chip ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              <strong>
                {f === 'all'
                  ? 'All'
                  : f === 'big'
                    ? 'Big GPU'
                    : f === 'upsample_image'
                      ? 'Upsample img'
                      : f === 'upsample_video'
                        ? 'Upsample vid'
                        : f}
              </strong>
            </button>
          ))}
        </div>
        <p className="model-dl-summary muted tiny" style={{ marginTop: 12 }}>
          Downloaded: {dlCounts.downloaded} · Not downloaded: {dlCounts.notDownloaded} ·
          Downloading: {dlCounts.downloading}
        </p>
        <div className="mode-grid model-status-filters" style={{ marginTop: 8 }}>
          {(
            [
              ['all', 'All status'],
              ['downloaded', 'Downloaded'],
              ['not_downloaded', 'Not downloaded'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`mode-chip ${statusFilter === id ? 'active' : ''}`}
              onClick={() => setStatusFilter(id)}
            >
              <strong>{label}</strong>
            </button>
          ))}
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Advanced · legacy Wan2GP import</h3>
        <p className="muted tiny">
          Not required. Everyday Generate uses StudioNels Downloads only. Leave this blank unless
          you deliberately want to scan an old Wan2GP folder for LoRAs / extras.
        </p>
        <div className="field" style={{ marginTop: 10 }}>
          <label>Wan2GP folder path</label>
          <input
            value={wan2gpPath}
            onChange={(e) => setWan2gpPath(e.target.value)}
            placeholder="C:\pinokio\api\wan2gp   or   …\wan2gp\ckpts"
          />
        </div>
        <div className="inline-actions" style={{ gap: 8, flexWrap: 'wrap' }}>
          <button
            className="btn acid"
            type="button"
            disabled={wan2gpBusy || !wan2gpPath.trim()}
            onClick={async () => {
              setWan2gpBusy(true)
              setWan2gpHint(null)
              try {
                const r = await api.engineWan2gpImport(wan2gpPath.trim(), true)
                setModels(r.models)
                setAssets(r.inventory)
                const c = r.counts || {}
                setWan2gpHint(r.hint)
                notify(
                  `Imported — video ${c.video_packs || 0} · image ${c.image_models || 0} · audio ${c.audio_models || 0} · upsample ${c.upsample_models || 0} · LoRAs ${c.loras || 0}`,
                )
                await load()
              } catch (err) {
                notify(String((err as Error).message || err))
              } finally {
                setWan2gpBusy(false)
              }
            }}
          >
            {wan2gpBusy ? 'Importing…' : 'Import all assets'}
          </button>
          <button
            className="btn ghost"
            type="button"
            disabled={wan2gpBusy}
            onClick={async () => {
              try {
                const r = await api.engineWan2gpScan()
                setAssets(r)
                const by = r.by_mode || {}
                setWan2gpHint(
                  `Per tab: t2v ${by.t2v || 0} · i2v ${by.i2v || 0} · ref2v ${by.ref2v || 0} · t2i ${by.t2i || 0} · t2a ${by.t2a || 0} · upsample ${(by.upsample_image || 0) + (by.upsample_video || 0)} · LoRAs ${r.counts?.loras || 0}`,
                )
                await load()
              } catch (err) {
                notify(String((err as Error).message || err))
              }
            }}
          >
            Scan assets
          </button>
        </div>
        {wan2gpHint && <p className="muted tiny" style={{ marginTop: 8 }}>{wan2gpHint}</p>}
        {assets?.counts && (
          <div className="muted tiny" style={{ marginTop: 8 }}>
            On disk: video {assets.counts.video_packs || 0} · image {assets.counts.image_models || 0} ·
            audio {assets.counts.audio_models || 0} · upsample {assets.counts.upsample_models || 0} ·
            LoRAs {assets.counts.loras || 0} · TEs {assets.counts.text_encoders || 0} · VAEs{' '}
            {(assets.counts.video_vaes || 0) + (assets.counts.audio_vaes || 0)} · upscalers{' '}
            {assets.counts.upscalers || 0}
          </div>
        )}
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <h3>Add Hugging Face Diffusers model</h3>
        <p className="muted tiny">
          Register any Diffusers repo, then Download it under Models until Ready. Example:{' '}
          <code>rootonchair/LTX-2.3-Distilled-v1.1-Diffusers</code>.
        </p>
        <div className="controls-grid" style={{ marginTop: 10 }}>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label>Hugging Face id</label>
            <input value={customHf} onChange={(e) => setCustomHf(e.target.value)} placeholder="owner/repo" />
          </div>
          <div className="field">
            <label>Label</label>
            <input value={customLabel} onChange={(e) => setCustomLabel(e.target.value)} />
          </div>
          <div className="field">
            <label>Kind</label>
            <select
              value={customKind}
              onChange={(e) => {
                const k = e.target.value as typeof customKind
                setCustomKind(k)
                setCustomModes(kindDefaultModes(k))
              }}
            >
              <option value="video">Video (t2v / i2v / ref2v)</option>
              <option value="image">Image (t2i / ref2i)</option>
              <option value="audio">Audio (t2a)</option>
              <option value="upsample">Upsample</option>
            </select>
          </div>
          <div className="field">
            <label>Min VRAM (GB)</label>
            <input
              type="number"
              min={0}
              step={1}
              value={customVram}
              onChange={(e) => setCustomVram(Number(e.target.value) || 0)}
            />
          </div>
          <div className="field" style={{ gridColumn: '1 / -1' }}>
            <label>Generate tabs this model appears in</label>
            <div className="mode-grid" style={{ marginTop: 6 }}>
              {(
                [
                  't2i',
                  't2v',
                  'i2v',
                  'ref2i',
                  'ref2v',
                  't2a',
                  'upsample_image',
                  'upsample_video',
                ] as const
              ).map((m) => {
                const on = customModes.includes(m)
                return (
                  <button
                    key={m}
                    type="button"
                    className={`mode-chip ${on ? 'active' : ''}`}
                    onClick={() =>
                      setCustomModes((prev) =>
                        on ? prev.filter((x) => x !== m) : [...prev, m],
                      )
                    }
                  >
                    <strong>{m}</strong>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
        <button className="btn acid" type="button" disabled={adding || !customHf.includes('/')} onClick={addCustom}>
          {adding ? 'Adding…' : 'Add & use model'}
        </button>
      </div>

      <div className="job-list" style={{ marginTop: 16 }}>
        {shown.length === 0 && (
          <div className="empty">No models match these filters.</div>
        )}
        {shown.map((m) => {
          const st = modelStatus(m)
          const pct = Math.round((m.download_progress || 0) * 100)
          const isActive = activeId === m.id || m.active
          const isDownloaded = st === 'installed'
          const inStudio = (warm?.cached || []).some((c) => c === m.label)
          return (
            <div
              className={`job-item model-row ${isDownloaded ? 'model-downloaded' : 'model-missing'}`}
              key={m.id}
            >
              <header>
                <strong className="model-row-title">
                  <span
                    className={`model-dl-dot ${isDownloaded ? 'on' : 'off'}`}
                    aria-hidden
                    title={isDownloaded ? 'Downloaded' : 'Not downloaded'}
                  />
                  {m.label}
                  {isDownloaded && (
                    <span className="model-on-disk" title="Weights on disk">
                      {' '}
                      ✓ On disk
                    </span>
                  )}
                  {isActive ? ' · active' : ''}
                  {m.distilled ? ' · distilled' : ''}
                  {m.wan2gp || m.format === 'wan2gp' ? ' · Wan2GP' : ''}
                  {m.custom ? ' · custom' : ''}
                  {m.discovered ? ' · local' : ''}
                </strong>
                <span className="model-row-badges">
                  {inStudio && <span className="badge ready">Ready in studio</span>}
                  <span className={`badge ${modelDownloadBadgeClass(st)}`}>
                    {modelDownloadLabel(st, pct)}
                  </span>
                </span>
              </header>
              <div className="muted tiny">
                {m.kind} · ≥{m.min_vram_gb} GB
                {m.tier === 'big' ? ' · big GPU' : ''}
                {m.hf_id ? ` · ${m.hf_id}` : ' · built-in'}
                {m.local_path ? ' · on disk' : ''}
                {m.notes ? ` — ${m.notes}` : ''}
              </div>
              {(st === 'downloading' ||
                st === 'stalled' ||
                st === 'failed' ||
                st === 'cancelled') && (
                <ModelDownloadProgress
                  model={m}
                  compact
                  onCancel={
                    st === 'downloading' || st === 'stalled'
                      ? () => void act(m.id, () => api.engineModelCancel(m.id), 'Download cancelled')
                      : undefined
                  }
                  onRetry={
                    st === 'failed' || st === 'stalled' || st === 'cancelled'
                      ? () =>
                          void act(
                            m.id,
                            () => api.engineModelDownload(m.id, true),
                            `Downloading ${m.label}…`,
                          )
                      : undefined
                  }
                />
              )}
              {m.download_error && st === 'installed' && (
                <div className="fit-warn tiny">{m.download_error}</div>
              )}
              <div className="inline-actions" style={{ marginTop: 10, flexWrap: 'wrap', gap: 8 }}>
                <button
                  className="btn acid tiny"
                  type="button"
                  disabled={busyId === m.id || isActive}
                  onClick={() =>
                    act(m.id, () => api.engineModelActivate(m.id), `Active model → ${m.label}`)
                  }
                >
                  {isActive ? 'Selected' : 'Use this model'}
                </button>
                {st === 'installed' && m.kind !== 'upsample' && (
                  <button
                    className="btn secondary tiny"
                    type="button"
                    disabled={
                      busyId === m.id ||
                      preloadId === m.id ||
                      Boolean(warm?.preloading) ||
                      (warm?.cached || []).some((c) => c === m.label)
                    }
                    onClick={() => {
                      setPreloadId(m.id)
                      void (async () => {
                        try {
                          await api.engineModelActivate(m.id)
                          const r = await api.enginePreload({ model_id: m.id })
                          notify(
                            r.message ||
                              (r.started
                                ? `Preloading ${m.label} into studio…`
                                : `Load started for ${m.label}`),
                          )
                          const w = await api.engineWarm().catch(() => null)
                          if (w) setWarm(w)
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        } finally {
                          setPreloadId(null)
                        }
                      })()
                    }}
                  >
                    {(warm?.cached || []).some((c) => c === m.label)
                      ? 'Loaded in studio'
                      : preloadId === m.id || (warm?.preloading && warm.preload_model_id === m.id)
                        ? 'Loading…'
                        : isActive
                          ? 'Ready this model'
                          : 'Load into studio'}
                  </button>
                )}
                {(st === 'not_downloaded' || st === 'cancelled' || st === 'failed' || st === 'stalled') && (
                  <button
                    className="btn secondary tiny"
                    type="button"
                    disabled={busyId === m.id || !m.hf_id}
                    onClick={() =>
                      act(
                        m.id,
                        () => api.engineModelDownload(m.id, st !== 'not_downloaded'),
                        `Downloading ${m.label}…`,
                      )
                    }
                  >
                    {st === 'stalled' || st === 'failed' ? 'Retry download' : 'Download'}
                  </button>
                )}
                {(st === 'downloading' || st === 'stalled') && (
                  <button
                    className="btn ghost tiny"
                    type="button"
                    disabled={busyId === m.id}
                    onClick={() => act(m.id, () => api.engineModelCancel(m.id), 'Download cancelled')}
                  >
                    Cancel
                  </button>
                )}
                {(st === 'downloading' || st === 'stalled' || st === 'cancelled' || st === 'failed') && (
                  <button
                    className="btn ghost tiny"
                    type="button"
                    disabled={busyId === m.id}
                    onClick={() =>
                      act(m.id, () => api.engineModelClear(m.id, false), 'Cleared stuck status')
                    }
                  >
                    Clear stuck
                  </button>
                )}
                {m.custom && !m.discovered && (
                  <button
                    className="btn ghost tiny"
                    type="button"
                    disabled={busyId === m.id}
                    onClick={() =>
                      act(m.id, () => api.engineModelRemoveCustom(m.id), `Removed ${m.label}`)
                    }
                  >
                    Remove custom
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="inline-actions" style={{ justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>LoRAs</h3>
          <button
            className="btn ghost tiny"
            type="button"
            onClick={async () => {
              await load()
              notify(loras.length ? `Scanned ${loras.length} LoRA(s)` : 'No LoRAs — drop into loras/ or import Wan2GP.')
            }}
          >
            Rescan
          </button>
        </div>
        <p className="muted tiny">
          StudioNels <code>loras/</code>
          {lorasPath ? ` → ${lorasPath}` : ''} plus any Wan2GP <code>loras/</code> from Import.
          They show in Generate’s LoRA dropdown.
        </p>
        {loras.length === 0 ? (
          <div className="empty">No LoRAs found yet.</div>
        ) : (
          <div className="job-list">
            {loras.map((l) => (
              <div className="job-item" key={l.path}>
                <header>
                  <strong>{l.name}</strong>
                  <span className="badge done">{l.size_mb} MB</span>
                </header>
                <div className="muted tiny">{l.path}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function AddonsTab({ notify }: { notify: (m: string) => void }) {
  return (
    <div className="panel">
      <h3>Plugins & skills</h3>
      <p className="hint">
        Add-ons live in <code>addons/plugins/</code> and <code>addons/skills/</code> inside the app
        folder. Drop a JSON plugin or Markdown skill there, then restart the API.
      </p>
      <p className="muted">Bundled examples: Neon Color Grading, Auto Audio Bed, Shot List Director.</p>
      <button className="btn acid" type="button" onClick={() => notify('Check addons/ in your StudioNels folder.')}>
        Open folder tip
      </button>
    </div>
  )
}

function LearningTab({ onGo }: { onGo: (id: TabId) => void }) {
  const [active, setActive] = useState<LearnSectionId>(() => {
    try {
      const id = window.sessionStorage.getItem('studionels_learn_section') as LearnSectionId | null
      if (id && LEARN_TOPICS.some((t) => t.id === id)) {
        window.sessionStorage.removeItem('studionels_learn_section')
        return id
      }
    } catch {
      /* ignore */
    }
    return 'start-here'
  })
  const topic = LEARN_TOPICS.find((t) => t.id === active) || LEARN_TOPICS[0]

  return (
    <div className="learn-layout">
      <aside className="learn-nav panel">
        <h3>Learning</h3>
        <p className="muted tiny">
          Explained like it’s your first day with AI video — how-tos, where to click, and examples.
        </p>
        <div className="learn-toc">
          {LEARN_TOPICS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`learn-toc-item ${active === t.id ? 'active' : ''}`}
              onClick={() => setActive(t.id)}
            >
              {t.title}
            </button>
          ))}
        </div>
      </aside>
      <article className="learn-article panel">
        <header className="learn-hero">
          <h2>{topic.title}</h2>
          <p>{topic.blurb}</p>
        </header>

        <section>
          <h3>Where to find it</h3>
          <ul className="learn-where">
            {topic.where.map((w) => (
              <li key={w.label + w.detail}>
                <strong>{w.label}</strong>
                <span className="muted"> — {w.detail}</span>
                {w.tab && (
                  <button className="btn ghost tiny" type="button" onClick={() => onGo(w.tab!)}>
                    Open
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>

        {topic.howto.map((h) => (
          <section key={h.title}>
            <h3>{h.title}</h3>
            <ol className="learn-steps">
              {h.steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
            {h.example && (
              <div className="learn-example">
                <span className="muted tiny">Example</span>
                <p>{h.example}</p>
              </div>
            )}
          </section>
        ))}

        <section>
          <h3>Examples & tips</h3>
          <ul className="learn-examples">
            {topic.examples.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          {topic.tip && <p className="learn-tip">{topic.tip}</p>}
        </section>
      </article>
    </div>
  )
}

function SourcesTab({ notify }: { notify: (m: string) => void }) {
  const [github, setGithub] = useState('')
  const [hf, setHf] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [token, setToken] = useState('')
  const [tokenSet, setTokenSet] = useState(false)
  const [kind, setKind] = useState<'model' | 'lora' | 'addon'>('lora')
  const [source, setSource] = useState('')
  const [imports, setImports] = useState<
    Awaited<ReturnType<typeof api.personalImports>>
  >([])
  const [hints, setHints] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)

  const load = async () => {
    const p = await api.getPersonal()
    setGithub(p.github_url || '')
    setHf(p.huggingface_url || '')
    setDisplayName(p.display_name || '')
    setTokenSet(p.huggingface_token_set)
    setImports(p.imports || [])
    setHints(p.hints || {})
  }

  useEffect(() => {
    load().catch((e) => notify(String(e.message || e)))
    const t = window.setInterval(() => {
      api.personalImports().then(setImports).catch(() => undefined)
    }, 2500)
    return () => window.clearInterval(t)
  }, [])

  const saveLinks = async () => {
    setBusy(true)
    try {
      const p = await api.putPersonal({
        github_url: github,
        huggingface_url: hf,
        creator_display_name: displayName,
        huggingface_token: token.trim() || (tokenSet ? '(unchanged)' : ''),
      })
      setToken('')
      setTokenSet(p.huggingface_token_set)
      setImports(p.imports || [])
      notify('Your GitHub & Hugging Face links are saved on this machine.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const runImport = async () => {
    if (!source.trim()) {
      notify('Paste a Hugging Face or GitHub URL first.')
      return
    }
    setBusy(true)
    try {
      const job = await api.importPersonal({ kind, source: source.trim() })
      setImports((prev) => [job, ...prev])
      notify(`Import started · ${kind}`)
      setSource('')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Personalise StudioNels with <strong>your</strong> GitHub and Hugging Face pages. Import
        models, LoRAs, or add-ons from those links into the local folders — no path pasting.
      </p>
      <div className="gen-layout">
        <div className="panel">
          <h3>My links</h3>
          <div className="field">
            <label>Display name (optional)</label>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Studio name on this machine"
            />
          </div>
          <div className="field">
            <label>GitHub URL</label>
            <input
              value={github}
              onChange={(e) => setGithub(e.target.value)}
              placeholder={hints.github || 'https://github.com/you'}
            />
            <div className="muted tiny">Profile or a repo where you keep packs / skills.</div>
          </div>
          <div className="field">
            <label>Hugging Face URL</label>
            <input
              value={hf}
              onChange={(e) => setHf(e.target.value)}
              placeholder={hints.huggingface || 'https://huggingface.co/you'}
            />
            <div className="muted tiny">Your HF profile or collection of models / LoRAs.</div>
          </div>
          <div className="field">
            <label>
              Hugging Face token {tokenSet ? '(saved — leave blank to keep)' : '(optional, for gated models)'}
            </label>
            <input
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={tokenSet ? '••••••••' : 'hf_…'}
            />
            <div className="muted tiny">Stored only in local settings — never sent to StudioNels cloud.</div>
          </div>
          <div className="inline-actions">
            <button className="btn acid" type="button" disabled={busy} onClick={saveLinks}>
              Save my links
            </button>
            {github && (
              <a className="btn ghost" href={github.startsWith('http') ? github : `https://${github}`} target="_blank" rel="noreferrer">
                Open GitHub
              </a>
            )}
            {hf && (
              <a className="btn ghost" href={hf.startsWith('http') ? hf : `https://${hf}`} target="_blank" rel="noreferrer">
                Open Hugging Face
              </a>
            )}
          </div>
        </div>

        <div className="panel">
          <h3>Import into local folders</h3>
          <p className="muted tiny">
            Pull your own (or public) stuff into <code>models/</code>, <code>loras/</code>, or{' '}
            <code>addons/</code>.
          </p>
          <div className="field">
            <label>What is it?</label>
            <select value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
              <option value="model">Model (HF repo → models/)</option>
              <option value="lora">LoRA file → loras/</option>
              <option value="addon">Add-on (JSON/MD) → addons/</option>
            </select>
          </div>
          <div className="field">
            <label>URL or repo</label>
            <input
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder={
                kind === 'model'
                  ? hints.import_model
                  : kind === 'lora'
                    ? hints.import_lora
                    : hints.import_addon
              }
            />
          </div>
          <button className="btn acid" type="button" disabled={busy} onClick={runImport}>
            Import to StudioNels
          </button>

          <h3 style={{ marginTop: 20 }}>Recent imports</h3>
          <div className="job-list">
            {imports.length === 0 && <div className="empty">No imports yet.</div>}
            {imports.map((job) => (
              <div className="job-item" key={job.id}>
                <header>
                  <strong>
                    {job.kind.toUpperCase()} · {job.name || job.source}
                  </strong>
                  <span className={`badge ${job.status}`}>{job.status}</span>
                </header>
                <div className="muted tiny">{job.message}</div>
                <div className="progress">
                  <div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
                </div>
                {job.local_path && <div className="muted tiny">{job.local_path}</div>}
                <div className="inline-actions" style={{ marginTop: 8 }}>
                  {(job.status === 'running' || job.status === 'queued') && (
                    <button
                      className="btn ghost tiny"
                      type="button"
                      onClick={async () => {
                        try {
                          await api.cancelPersonalImport(job.id)
                          notify('Import cancelled')
                          setImports(await api.personalImports())
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        }
                      }}
                    >
                      Cancel stuck import
                    </button>
                  )}
                  {(job.status === 'cancelled' || job.status === 'failed' || job.status === 'done') && (
                    <button
                      className="btn ghost tiny"
                      type="button"
                      onClick={async () => {
                        try {
                          await api.clearPersonalImport(job.id)
                          setImports(await api.personalImports())
                        } catch (err) {
                          notify(String((err as Error).message || err))
                        }
                      }}
                    >
                      Remove from list
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function InfoTab() {
  const folders = [
    { path: 'models/', put: 'AI models (or download in-app / My links import)' },
    { path: 'loras/', put: 'Optional LoRA .safetensors files' },
    { path: 'outputs/', put: 'Generated images, video, audio' },
    { path: 'uploads/', put: 'Your reference images & clips' },
    { path: 'projects/', put: 'Saved studio projects' },
    { path: 'addons/plugins/', put: 'Plugin JSON add-ons' },
    { path: 'addons/skills/', put: 'Agent skill JSON / Markdown' },
    { path: 'cache/', put: 'Settings & job queue (leave alone)' },
  ]
  return (
    <div>
      <p className="hint">
        Pinokio-style layout — everything sits in the StudioNels folder you downloaded. No hidden
        mystery directories required. New here? Open <strong>Learning</strong> for first-time how-tos.
      </p>
      <div className="panel">
        <h3>Where to put downloads</h3>
        <div className="shot-list">
          {folders.map((f) => (
            <div className="profile-item" key={f.path}>
              <strong style={{ color: 'var(--neon)' }}>{f.path}</strong>
              <div className="muted">{f.put}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
