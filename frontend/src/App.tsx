import { useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api, mediaUrl } from './api'
import { INSPIRATION_CLIPS, type InspirationClip } from './inspiration'
import {
  DURATION_PRESETS,
  VISUAL_STYLES,
  formatDuration,
} from './stylesCatalog'
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
  CharacterProfile,
  EngineJob,
  EngineStatus,
  GenMode,
  Health,
  Mode,
  Preset,
  Project,
  ProjectSummary,
  SceneProfile,
  Settings,
  Shot,
  TabId,
  Take,
} from './types'
import './styles.css'

const TABS: { id: TabId; label: string }[] = [
  { id: 'inspiration', label: 'Inspiration' },
  { id: 'agent', label: 'Agent' },
  { id: 'profiles', label: 'Profiles' },
  { id: 'time', label: 'Time & Style' },
  { id: 'shots', label: 'Shots' },
  { id: 'storyboard', label: 'Storyboard' },
  { id: 'characters', label: 'Characters' },
  { id: 'creator', label: 'Creator' },
  { id: 'generate', label: 'Generate' },
  { id: 'audio', label: 'Audio' },
  { id: 'upsample', label: 'Upsample' },
  { id: 'models', label: 'Models' },
  { id: 'addons', label: 'Add-ons' },
  { id: 'sampling', label: 'Sampling' },
  { id: 'director', label: 'Director' },
  { id: 'info', label: 'Info' },
  { id: 'settings', label: 'Settings' },
]

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

function formatWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString('en-GB', {
      timeZone: 'Europe/London',
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

function Brand() {
  return (
    <div className="brand-mark" aria-label="Framewright">
      <span className="dot" aria-hidden />
      Framewright
    </div>
  )
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [settings, setSettings] = useState<Settings | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [project, setProject] = useState<Project | null>(null)
  const [tab, setTab] = useState<TabId>('inspiration')
  const [inspirationSeed, setInspirationSeed] = useState<InspirationSeed | null>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [title, setTitle] = useState('My first local film')
  const [mode, setMode] = useState<Mode>('short')
  const [agentText, setAgentText] = useState('')
  const [replaceShots, setReplaceShots] = useState(true)

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 2800)
  }

  const refreshHome = async () => {
    const [h, p, s, list] = await Promise.all([
      api.health(),
      api.presets(),
      api.getSettings(),
      api.listProjects(),
    ])
    setHealth(h)
    setPresets(p)
    setSettings(s)
    setProjects(list)
  }

  useEffect(() => {
    refreshHome().catch((e) => notify(String(e.message || e)))
  }, [])

  const openProject = async (id: string) => {
    setBusy(true)
    try {
      const p = await api.getProject(id)
      setProject(p)
      setTab('agent')
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
      })
      setShowNew(false)
      setProject(p)
      setTab('profiles')
      await refreshHome()
      notify('Project created — add a character or jump to Agent.')
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

  const runAgent = async () => {
    if (!project || !agentText.trim()) return
    setBusy(true)
    try {
      const p = await api.agent(project.id, agentText.trim(), replaceShots)
      setProject(p)
      setAgentText('')
      setTab('shots')
      notify('Shot list ready — edit anything before generating.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const generateShots = async (shotIds?: string[]) => {
    if (!project) return
    setBusy(true)
    try {
      const p = await api.generate(project.id, shotIds, 'video')
      setProject(p)
      setTab('sampling')
      notify(
        health?.gpu
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
    return (
      <div className="app-shell home">
        <div className="home-top">
          <Brand />
          <div className="status-pills">
            <span className={`pill ${health?.ollama ? 'on' : 'off'}`}>
              Agent {health?.ollama ? 'Ollama live' : 'built-in planner'}
            </span>
            <span className={`pill ${health?.gpu ? 'on' : 'off'}`}>
              Engine {health?.gpu ? health.device_name : 'preview (no GPU torch)'}
            </span>
            <span className="pill">
              Preset {settings?.preset_id || 'amd-low-vram'}
            </span>
          </div>
        </div>

        <section className="hero">
          <Brand />
          <h1>Make films on your Radeon. Fully local.</h1>
          <p>
            Tell an agent your idea, keep character and scene profiles, break the story into
            editable shots, sample takes, then cut in Director mode — all on your machine, tuned
            for AMD and low VRAM by default.
          </p>
          <div className="cta-row">
            <button className="btn acid" type="button" onClick={() => setShowNew(true)}>
              Start a project
            </button>
            <button
              className="btn secondary"
              type="button"
              onClick={() => document.getElementById('projects')?.scrollIntoView({ behavior: 'smooth' })}
            >
              Open saved work
            </button>
          </div>
        </section>

        <section className="home-projects" id="projects">
          <div className="section-label">Your projects</div>
          {projects.length === 0 ? (
            <div className="empty">No projects yet. Start one — it saves under ~/.framewright.</div>
          ) : (
            <div className="project-grid">
              {projects.map((p, i) => (
                <button
                  key={p.id}
                  className="project-tile"
                  type="button"
                  style={{ animationDelay: `${i * 0.05}s` }}
                  onClick={() => openProject(p.id)}
                >
                  <h3>{p.title}</h3>
                  <p>
                    {p.mode.replace('_', ' ')} · {p.shot_count} shots
                  </p>
                  <p className="tiny muted">Updated {formatWhen(p.updated_at)} (London)</p>
                </button>
              ))}
            </div>
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
        {toast && <div className="toast">{toast}</div>}
      </div>
    )
  }

  return (
    <div className="app-shell studio">
      <header className="studio-top">
        <div className="studio-title">
          <Brand />
          <strong>{project.title}</strong>
          <span>
            {project.mode.replace('_', ' ')} · {project.shots.length} shots · preset{' '}
            {project.preset_id}
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
            onClick={() => generateShots()}
          >
            Generate all shots
          </button>
        </div>
      </header>

      <nav className="tabs" aria-label="Studio sections">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="studio-body">
        {tab === 'inspiration' && (
          <InspirationTab
            onTry={(clip) => {
              setInspirationSeed({
                mode: clip.mode,
                prompt: clip.prompt,
                title: clip.title,
              })
              setTab('generate')
              notify(`Loaded “${clip.title}” into Generate.`)
            }}
          />
        )}
        {tab === 'agent' && (
          <AgentTab
            project={project}
            text={agentText}
            setText={setAgentText}
            replaceShots={replaceShots}
            setReplaceShots={setReplaceShots}
            busy={busy}
            onSend={runAgent}
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
        {tab === 'storyboard' && <StoryboardTab project={project} onGenerate={generateShots} />}
        {tab === 'characters' && (
          <CharactersTab
            project={project}
            setProject={setProject}
            busy={busy}
            onGenerateRefs={generateRefs}
            notify={notify}
            setBusy={setBusy}
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
          />
        )}
        {tab === 'audio' && (
          <AudioTab project={project} setProject={setProject} notify={notify} health={health} />
        )}
        {tab === 'upsample' && (
          <UpsampleTab project={project} notify={notify} />
        )}
        {tab === 'models' && <ModelsTab notify={notify} />}
        {tab === 'addons' && <AddonsTab notify={notify} />}
        {tab === 'info' && <InfoTab />}
        {tab === 'sampling' && (
          <SamplingTab
            project={project}
            setProject={setProject}
            busy={busy}
            setBusy={setBusy}
            notify={notify}
          />
        )}
        {tab === 'director' && (
          <DirectorTab
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
          />
        )}
      </main>
      {toast && <div className="toast">{toast}</div>}
    </div>
  )
}

function AgentTab({
  project,
  text,
  setText,
  replaceShots,
  setReplaceShots,
  busy,
  onSend,
}: {
  project: Project
  text: string
  setText: (v: string) => void
  replaceShots: boolean
  setReplaceShots: (v: boolean) => void
  busy: boolean
  onSend: () => void
}) {
  return (
    <div className="chat">
      <p className="hint">
        Talk like you would to a director. Example: “A quiet sci-fi short about a courier who
        delivers memories in glass jars.” The agent turns it into editable shots.
      </p>
      <div className="chat-log">
        {project.agent_messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
      </div>
      <div className="chat-compose">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe your idea…"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) onSend()
          }}
        />
        <div className="compose-row">
          <label className="muted">
            <input
              type="checkbox"
              checked={replaceShots}
              onChange={(e) => setReplaceShots(e.target.checked)}
            />{' '}
            Replace current shot list
          </label>
          <button className="btn acid" type="button" disabled={busy || !text.trim()} onClick={onSend}>
            Plan shots
          </button>
        </div>
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
    await save(next)
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
            </div>
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

  if (project.shots.length === 0) {
    return (
      <div className="empty">
        No shots yet. Open the Agent tab and describe your idea — or add profiles first.
      </div>
    )
  }

  return (
    <div>
      <p className="hint">Every field is editable. Generate one shot to test, or all from the top bar.</p>
      <div className="shot-list">
        {project.shots.map((shot) => (
          <div className="shot-card" key={shot.id}>
            <div className="shot-index">{shot.index + 1}</div>
            <div className="shot-editor">
              <div className="inline-actions">
                <span className={`badge ${shot.status}`}>{shot.status}</span>
                <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => onGenerate(shot.id)}>
                  Generate
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

function StoryboardTab({
  project,
  onGenerate,
}: {
  project: Project
  onGenerate: (ids?: string[]) => void
}) {
  const takeMap = useMemo(() => {
    const m = new Map<string, Take>()
    for (const t of project.takes) {
      if (!m.has(t.shot_id)) m.set(t.shot_id, t)
      const shot = project.shots.find((s) => s.id === t.shot_id)
      if (shot?.pinned_take_id === t.id) m.set(t.shot_id, t)
    }
    return m
  }, [project])

  if (!project.shots.length) {
    return <div className="empty">Storyboard fills in after the agent plans shots.</div>
  }

  return (
    <div>
      <p className="hint">Visual board of your film. Pin favorites later in Sampling.</p>
      <div className="inline-actions" style={{ marginBottom: 12 }}>
        <button className="btn" type="button" onClick={() => onGenerate()}>
          Generate missing shots
        </button>
      </div>
      <div className="board">
        {project.shots.map((shot) => {
          const take = takeMap.get(shot.id)
          const src = mediaUrl(take?.thumb_path || take?.media_path)
          return (
            <div className="board-card" key={shot.id}>
              <div className="board-thumb">
                {src ? <img src={src} alt="" /> : <span>{shot.index + 1}. {shot.title}</span>}
              </div>
              <div className="board-body">
                <strong>
                  {shot.index + 1}. {shot.title}
                </strong>
                <div className="muted">{shot.storyboard_note || shot.action}</div>
                <div className="muted tiny">
                  {shot.camera} · {shot.duration_sec}s
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function CharactersTab({
  project,
  setProject,
  busy,
  setBusy,
  onGenerateRefs,
  notify,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  onGenerateRefs: (kind: 'character_still' | 'scene_still') => void
  notify: (m: string) => void
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
        Generate refs, then edit anything — look notes, mood, or swap the reference image if you need
        a change.
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

function GenerateTab({
  project,
  setProject,
  notify,
  health,
  seed,
  onSeedConsumed,
}: {
  project: Project
  setProject: (p: Project) => void
  notify: (m: string) => void
  health: Health | null
  seed?: InspirationSeed | null
  onSeedConsumed?: () => void
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
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [refUrl, setRefUrl] = useState<string | null>(null)
  const [width, setWidth] = useState(768)
  const [height, setHeight] = useState(432)
  const [quality, setQuality] = useState('balanced')
  const [durationSec, setDurationSec] = useState(3)
  const [loraPath, setLoraPath] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!seed) return
    setMode(seed.mode)
    setPrompt(seed.prompt)
    onSeedConsumed?.()
  }, [seed])

  const refresh = async () => {
    const [e, j] = await Promise.all([api.engine(), api.engineJobs()])
    setEngine(e)
    setJobs(j)
    if (!modelId) {
      const models = e.models.filter((m) => m.modes.includes(mode))
      if (models[0]) setModelId(models[0].id)
    }
  }

  useEffect(() => {
    refresh().catch((err) => notify(String(err.message || err)))
    const t = window.setInterval(() => {
      api.engineJobs().then(setJobs).catch(() => undefined)
    }, 2000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    if (!engine) return
    const models = engine.models.filter((m) => m.modes.includes(mode))
    if (!models.find((m) => m.id === modelId)) {
      setModelId(models[0]?.id || '')
    }
  }, [mode, engine])

  const modeMeta = engine?.modes.find((m) => m.id === mode)
  const models = engine?.models.filter((m) => m.modes.includes(mode)) || []
  const style = VISUAL_STYLES.find((s) => s.id === project.visual_style)

  const upload = async (file: File, kind: 'image' | 'reference') => {
    const res = await api.engineUpload(file)
    if (kind === 'image') {
      setImagePath(res.path)
      setImageUrl(res.url)
    } else {
      setRefPath(res.path)
      setRefUrl(res.url)
    }
  }

  const run = async () => {
    if (!prompt.trim() && mode.startsWith('t')) {
      notify('Add a prompt first.')
      return
    }
    setBusy(true)
    try {
      const styled =
        style && !prompt.toLowerCase().includes(style.label.toLowerCase())
          ? `${prompt.trim()}, ${style.prompt_suffix}`
          : prompt
      const job = await api.engineGenerate({
        mode,
        model_id: modelId || undefined,
        prompt: styled,
        negative_prompt: negative,
        image_path: imagePath,
        reference_path: refPath,
        project_id: project.id,
        shot_id: shotId || undefined,
        cpu_offload: true,
        width,
        height,
        quality,
        duration_sec: durationSec,
        lora_path: loraPath || undefined,
        image_format: project.image_format,
        video_format: project.video_format,
        audio_format: project.audio_format,
        visual_style: project.visual_style,
      })
      notify(`Queued ${job.mode.toUpperCase()} · ${job.model_label}`)
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

  return (
    <div>
      <p className="hint">
        Built-in generator (Wan2GP-style) — pick a mode, model, and run inside Framewright. No ComfyUI.
        {health?.gpu
          ? ` GPU: ${health.device_name}.`
          : ' Running preview until ROCm PyTorch + weights are installed.'}
      </p>

      <div className="gen-layout">
        <div className="panel gen-panel">
          <h3>Mode</h3>
          <div className="mode-grid">
            {(engine?.modes || []).map((m) => (
              <button
                key={m.id}
                type="button"
                className={`mode-chip ${mode === m.id ? 'active' : ''}`}
                onClick={() => setMode(m.id)}
              >
                <strong>{m.label}</strong>
                <span>{m.blurb}</span>
              </button>
            ))}
          </div>

          <div className="field" style={{ marginTop: 14 }}>
            <label>Model</label>
            <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} (≥{m.min_vram_gb} GB)
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>Prompt</label>
            <textarea rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the image or shot…" />
          </div>
          <div className="muted tiny" style={{ marginBottom: 10 }}>
            Style from Time tab: <strong>{style?.label || project.visual_style}</strong> · Save as{' '}
            {project.image_format} / {project.video_format} / {project.audio_format}
          </div>
          <div className="field">
            <label>Negative (optional)</label>
            <input value={negative} onChange={(e) => setNegative(e.target.value)} />
          </div>

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
              <label>Quality</label>
              <select value={quality} onChange={(e) => setQuality(e.target.value)}>
                <option value="draft">Draft</option>
                <option value="balanced">Balanced</option>
                <option value="high">High</option>
                <option value="max">Max</option>
              </select>
            </div>
            <div className="field">
              <label>Clip length (sec)</label>
              <input
                type="number"
                min={1}
                step={0.5}
                value={durationSec}
                onChange={(e) => setDurationSec(Number(e.target.value))}
              />
            </div>
          </div>

          <div className="lora-box">
            <strong>Optional LoRA</strong>
            <div className="muted tiny">Drop files in the app’s <code>loras/</code> folder, then paste the full path here.</div>
            <input
              value={loraPath}
              onChange={(e) => setLoraPath(e.target.value)}
              placeholder="/path/to/framewright/loras/my_style.safetensors"
            />
          </div>

          {modeMeta?.needs_image && (
            <div className="field">
              <label>Input image (I2V)</label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], 'image')}
              />
              {imageUrl && <img className="upload-preview" src={imageUrl} alt="input" />}
            </div>
          )}
          {modeMeta?.needs_reference && (
            <div className="field">
              <label>Reference image</label>
              <input
                type="file"
                accept="image/*"
                onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], 'reference')}
              />
              {refUrl && <img className="upload-preview" src={refUrl} alt="reference" />}
            </div>
          )}

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

          <button className="btn acid" type="button" disabled={busy} onClick={run}>
            Generate {mode.toUpperCase()}
          </button>
        </div>

        <div className="panel">
          <h3>Queue</h3>
          <div className="muted tiny" style={{ marginBottom: 10 }}>
            Models folder: {engine?.models_path || '…'} · backend {engine?.backend}
          </div>
          <div className="job-list">
            {jobs.length === 0 && <div className="empty">No jobs yet.</div>}
            {jobs.map((job) => (
              <div className="job-item" key={job.id}>
                <header>
                  <strong>
                    {job.mode.toUpperCase()} · {job.model_label}
                  </strong>
                  <span className={`badge ${job.status}`}>{job.status}</span>
                </header>
                <div className="muted">{job.prompt || '(no prompt)'}</div>
                <div className="progress">
                  <div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
                </div>
                <div className="muted tiny">{job.message}</div>
                {job.thumb_path && mediaUrl(job.thumb_path) && (
                  <img src={mediaUrl(job.thumb_path)} alt="" className="job-thumb" />
                )}
                {job.preview && <div className="muted tiny">Preview output — not full model weights.</div>}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
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
  if (project.takes.length === 0) {
    return <div className="empty">Generate shots first — takes will appear here for comparison.</div>
  }

  const byShot = project.shots.map((shot) => ({
    shot,
    takes: project.takes.filter((t) => t.shot_id === shot.id),
  }))

  return (
    <div>
      <p className="hint">Compare takes. Pin the ones you want in Director mode.</p>
      {byShot.map(({ shot, takes }) =>
        takes.length ? (
          <div key={shot.id} style={{ marginBottom: 24 }}>
            <h3 style={{ fontFamily: 'var(--font-display)' }}>
              {shot.index + 1}. {shot.title}
            </h3>
            <div className="takes-grid">
              {takes.map((take) => (
                <div className="take-card" key={take.id}>
                  {mediaUrl(take.media_path) && (
                    <img src={mediaUrl(take.media_path)} alt={take.label} />
                  )}
                  <div className="body">
                    <strong>{take.label}</strong>
                    <div className="muted tiny">
                      seed {take.seed}
                      {take.is_placeholder ? ' · preview placeholder' : ''}
                    </div>
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

function DirectorTab({
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
  const clips =
    project.timeline.length > 0
      ? [...project.timeline].sort((a, b) => a.order - b.order)
      : project.shots
          .filter((s) => s.pinned_take_id)
          .map((s, i) => ({
            id: `temp_${s.id}`,
            shot_id: s.id,
            take_id: s.pinned_take_id,
            start_sec: 0,
            end_sec: s.duration_sec,
            pinned: true,
            order: i,
          }))

  const move = async (index: number, dir: -1 | 1) => {
    const next = clips.map((c) => ({ ...c }))
    const j = index + dir
    if (j < 0 || j >= next.length) return
    ;[next[index], next[j]] = [next[j], next[index]]
    setBusy(true)
    try {
      const p = await api.setTimeline(
        project.id,
        next.map((c, order) => ({
          id: c.id.startsWith('temp_') ? `clip_${c.shot_id}` : c.id,
          shot_id: c.shot_id,
          take_id: c.take_id,
          start_sec: c.start_sec,
          end_sec: c.end_sec ?? null,
          pinned: c.pinned,
          order,
        })),
      )
      setProject(p)
    } finally {
      setBusy(false)
    }
  }

  const buildFromPins = async () => {
    setBusy(true)
    try {
      const built = project.shots
        .filter((s) => s.pinned_take_id)
        .map((s, order) => ({
          id: `clip_${s.id}`,
          shot_id: s.id,
          take_id: s.pinned_take_id,
          start_sec: 0,
          end_sec: s.duration_sec,
          pinned: true,
          order,
        }))
      const p = await api.setTimeline(project.id, built)
      setProject(p)
      notify('Director timeline built from pinned takes.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="timeline">
      <p className="hint">
        Director mode: pin takes in Sampling, arrange them here, add notes, and keep editing as you
        go. Export is your ordered cut list for an NLE or local stitcher.
      </p>
      <div className="inline-actions">
        <button className="btn acid" type="button" disabled={busy} onClick={buildFromPins}>
          Build timeline from pins
        </button>
      </div>
      {clips.length === 0 ? (
        <div className="empty">Pin takes in Sampling to start directing.</div>
      ) : (
        <div className="timeline-track">
          {clips.map((clip, i) => {
            const shot = project.shots.find((s) => s.id === clip.shot_id)
            const take = project.takes.find((t) => t.id === clip.take_id)
            return (
              <div className={`clip ${clip.pinned ? 'pinned' : ''}`} key={clip.id}>
                <strong>
                  {i + 1}. {shot?.title || 'Shot'}
                </strong>
                <div className="muted tiny">{take?.label || 'No take'}</div>
                {mediaUrl(take?.thumb_path || take?.media_path) && (
                  <img
                    src={mediaUrl(take?.thumb_path || take?.media_path)}
                    alt=""
                    style={{ width: '100%', borderRadius: 8, aspectRatio: '16/9', objectFit: 'cover' }}
                  />
                )}
                <div className="inline-actions">
                  <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => move(i, -1)}>
                    ←
                  </button>
                  <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => move(i, 1)}>
                    →
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
      <div className="panel">
        <h3>Cut list</h3>
        <ol>
          {clips.map((clip, i) => {
            const shot = project.shots.find((s) => s.id === clip.shot_id)
            return (
              <li key={clip.id}>
                {i + 1}. {shot?.title} — {shot?.action} ({shot?.duration_sec}s)
              </li>
            )
          })}
        </ol>
      </div>
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
}: {
  project: Project
  setProject: (p: Project) => void
  settings: Settings
  setSettings: (s: Settings) => void
  presets: Preset[]
  health: Health | null
  notify: (m: string) => void
}) {
  const [draft, setDraft] = useState(settings)

  useEffect(() => setDraft(settings), [settings])

  const save = async () => {
    const s = await api.putSettings(draft)
    setSettings(s)
    const updated = { ...project, preset_id: draft.preset_id }
    const p = await api.putProject(updated)
    setProject(p)
    notify('Settings saved. Low-VRAM preset keeps the app shareable.')
  }

  return (
    <div>
      <p className="hint">
        Default is AMD Low VRAM so friends with smaller cards can use Framewright. On your R9700
        32GB, switch to the R9700 preset. Generation is built-in (Diffusers / Wan) — not ComfyUI.
      </p>
      <div className="settings-grid panel">
        <div className="field">
          <label>Compute preset</label>
          <select
            value={draft.preset_id}
            onChange={(e) => setDraft({ ...draft, preset_id: e.target.value })}
          >
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label} (~{p.target_vram_gb} GB)
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>Ollama URL</label>
          <input
            value={draft.ollama_url}
            onChange={(e) => setDraft({ ...draft, ollama_url: e.target.value })}
          />
        </div>
        <div className="field">
          <label>Ollama model</label>
          <input
            value={draft.ollama_model}
            onChange={(e) => setDraft({ ...draft, ollama_model: e.target.value })}
          />
        </div>
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
          CPU offload (saves VRAM)
        </label>
        <div className="muted">
          Engine: built-in · Torch: {health?.torch ? 'yes' : 'no'} · GPU:{' '}
          {health?.gpu ? health.device_name : 'not ready'} · Ollama:{' '}
          {health?.ollama ? 'connected' : 'offline'} · Data: {health?.data_dir}
        </div>
        <button className="btn acid" type="button" onClick={save}>
          Save settings
        </button>
      </div>
    </div>
  )
}

function InspirationTab({ onTry }: { onTry: (clip: InspirationClip) => void }) {
  return (
    <div>
      <p className="hint">
        Little idea clips of what Framewright can do — tap <em>Try this</em> to drop the prompt into
        Generate.
      </p>
      <div className="inspire-grid">
        {INSPIRATION_CLIPS.map((clip) => (
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
              <button className="btn acid" type="button" onClick={() => onTry(clip)}>
                Try this
              </button>
            </div>
          </article>
        ))}
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
  const [imageFormat, setImageFormat] = useState(project.image_format || 'png')
  const [videoFormat, setVideoFormat] = useState(project.video_format || 'mp4')
  const [audioFormat, setAudioFormat] = useState(project.audio_format || 'wav')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDuration(project.target_duration_sec || 60)
    setStyleId(project.visual_style || 'cinematic')
    setImageFormat(project.image_format || 'png')
    setVideoFormat(project.video_format || 'mp4')
    setAudioFormat(project.audio_format || 'wav')
  }, [project])

  const shotTotal = project.shots.reduce((sum, s) => sum + (s.duration_sec || 0), 0)

  const save = async (extra?: Partial<Project>) => {
    setBusy(true)
    try {
      const next = {
        ...project,
        target_duration_sec: duration,
        visual_style: styleId,
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
        Set the <strong>whole</strong> length of your piece (clip → feature), pick a look (cinematic,
        clay, cartoon…), and choose save formats. The Agent uses these when planning shots.
      </p>

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
  const [traits, setTraits] = useState<Record<string, string>>({ ...DEFAULT_TRAITS })
  const [busy, setBusy] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [lastLook, setLastLook] = useState('')
  const style = VISUAL_STYLES.find((s) => s.id === project.visual_style)

  const built = buildCharacterPrompt(name, traits, extra, style?.prompt_suffix)

  const setTrait = (groupId: string, optionId: string) => {
    setTraits((prev) => ({ ...prev, [groupId]: optionId }))
  }

  const generateCharacter = async () => {
    setBusy(true)
    try {
      const { look, prompt } = buildCharacterPrompt(name, traits, extra, style?.prompt_suffix)
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
          reference_path: media,
        })
        setProject(p)
        setPreviewUrl(mediaUrl(media) || null)
        notify(`Created ${name} — ref saved. Edit anytime in Characters.`)
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
        Sims-style character creator — pick skin, eyes, hair, build, then generate a portrait ref.
        Uses your Time tab style ({style?.label || 'cinematic'}).
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
  const [shotId, setShotId] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobs, setJobs] = useState<EngineJob[]>([])

  const kindMeta = AUDIO_KINDS.find((k) => k.id === kind)!
  const accent = VOICE_ACCENTS.find((a) => a.id === accentId) || VOICE_ACCENTS[0]

  useEffect(() => {
    const t = window.setInterval(() => {
      api.engineJobs().then((list) => setJobs(list.filter((j) => j.mode === 't2a'))).catch(() => undefined)
    }, 2000)
    api.engineJobs().then((list) => setJobs(list.filter((j) => j.mode === 't2a'))).catch(() => undefined)
    return () => window.clearInterval(t)
  }, [])

  const buildPrompt = () => {
    const parts = [kindMeta.prompt_prefix, prompt.trim()]
    parts.push(`${mood} mood`)
    if (kind === 'song') {
      parts.push(accent.prompt_hint)
      if (lyrics.trim()) parts.push(`lyrics idea: ${lyrics.trim()}`)
    }
    if (kind === 'score') {
      parts.push(`for a ${project.visual_style || 'cinematic'} ${project.mode.replace('_', ' ')}`)
    }
    return parts.filter(Boolean).join(', ')
  }

  const run = async () => {
    if (!prompt.trim()) {
      notify('Describe the music, song, or sound first.')
      return
    }
    setBusy(true)
    try {
      const modelId =
        kind === 'sfx' || kind === 'ambience'
          ? 'audiogen-medium'
          : kind === 'song'
            ? 'stable-audio-song'
            : 'stable-audio-open'
      const job = await api.engineGenerate({
        mode: 't2a',
        model_id: modelId,
        prompt: buildPrompt(),
        duration_sec: durationSec,
        project_id: project.id,
        shot_id: shotId || undefined,
        audio_format: project.audio_format || 'wav',
        quality: 'balanced',
      })
      notify(`Audio queued · ${kindMeta.label}`)
      setJobs((prev) => [job, ...prev])
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

  return (
    <div>
      <p className="hint">
        Dedicated audio studio — instrumentals, songs with a voice accent, film scores, ambience, and
        SFX. Saves as {project.audio_format || 'wav'}.
        {health?.gpu ? ` GPU: ${health.device_name}.` : ' Preview tones until audio models are installed.'}
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

          <div className="field" style={{ marginTop: 14 }}>
            <label>Description</label>
            <textarea
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={
                kind === 'song'
                  ? 'A late-night pop song about glass jars of memories…'
                  : 'Describe the music or sound…'
              }
            />
          </div>

          <div className="controls-grid">
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
            <div className="field">
              <label>Length (sec)</label>
              <input
                type="number"
                min={2}
                max={120}
                step={1}
                value={durationSec}
                onChange={(e) => setDurationSec(Number(e.target.value))}
              />
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
                <label>Lyrics idea (optional)</label>
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
          <h3>Audio queue</h3>
          <div className="job-list">
            {jobs.length === 0 && <div className="empty">No audio jobs yet.</div>}
            {jobs.map((job) => (
              <div className="job-item" key={job.id}>
                <header>
                  <strong>{job.model_label}</strong>
                  <span className={`badge ${job.status}`}>{job.status}</span>
                </header>
                <div className="muted">{job.prompt}</div>
                <div className="progress">
                  <div style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} />
                </div>
                {job.media_path && (
                  <audio controls src={mediaUrl(job.media_path)} style={{ width: '100%', marginTop: 8 }} />
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

function ModelsTab({ notify }: { notify: (m: string) => void }) {
  return (
    <div className="panel">
      <h3>Models</h3>
      <p className="hint">
        Switch and download models from the Generate tab’s model menu. Files land in the app’s{' '}
        <code>models/</code> folder (Pinokio-style). Drop LoRAs in <code>loras/</code>.
      </p>
      <p className="muted">
        Tip: open <strong>Info</strong> for the full folder map. In-app download buttons arrive with
        the Models manager API on your next pull — for now pick a model in Generate and it will fetch
        on first real GPU run.
      </p>
      <button className="btn" type="button" onClick={() => notify('Use Generate → Model dropdown to switch.')}>
        Got it
      </button>
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
      <button className="btn acid" type="button" onClick={() => notify('Check addons/ in your Framewright folder.')}>
        Open folder tip
      </button>
    </div>
  )
}

function InfoTab() {
  const folders = [
    { path: 'models/', put: 'AI models (or download in-app)' },
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
        Pinokio-style layout — everything sits in the Framewright folder you downloaded. No hidden
        mystery directories required.
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
