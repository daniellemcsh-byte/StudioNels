import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { api, mediaUrl } from './api'
import type {
  CharacterProfile,
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
  { id: 'agent', label: 'Agent' },
  { id: 'profiles', label: 'Profiles' },
  { id: 'shots', label: 'Shots' },
  { id: 'storyboard', label: 'Storyboard' },
  { id: 'characters', label: 'Characters' },
  { id: 'sampling', label: 'Sampling' },
  { id: 'director', label: 'Director' },
  { id: 'settings', label: 'Settings' },
]

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
  const [tab, setTab] = useState<TabId>('agent')
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
        health?.comfyui
          ? 'Generation queued / previews ready.'
          : 'Local preview takes created. Connect ComfyUI + ROCm for real video.',
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
            <span className={`pill ${health?.comfyui ? 'on' : 'off'}`}>
              Gen {health?.comfyui ? 'ComfyUI live' : 'preview mode'}
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
  return (
    <div className="profile-item">
      <header>
        <strong>{c.name}</strong>
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
      </header>
      <div className="muted">{c.role || 'No role'}</div>
      <div className="muted">{c.look || 'No look notes'}</div>
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
  return (
    <div className="profile-item">
      <header>
        <strong>{s.name}</strong>
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
      </header>
      <div className="muted">
        {[s.location, s.time_of_day, s.mood].filter(Boolean).join(' · ') || 'No details'}
      </div>
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
  busy,
  onGenerateRefs,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  onGenerateRefs: (kind: 'character_still' | 'scene_still') => void
  notify: (m: string) => void
}) {
  return (
    <div>
      <p className="hint">
        Need a face or place look? Generate local reference stills from your profiles. With ComfyUI
        + ROCm these become real model outputs; otherwise you get studio placeholders.
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
              <div className="take-card" key={c.id}>
                {mediaUrl(c.reference_path) ? (
                  <img src={mediaUrl(c.reference_path)} alt={c.name} />
                ) : (
                  <div className="board-thumb">{c.name}</div>
                )}
                <div className="body">
                  <strong>{c.name}</strong>
                  <div className="muted">{c.look || 'Add look notes in Profiles'}</div>
                </div>
              </div>
            ))}
            {project.characters.length === 0 && <div className="empty">Add characters in Profiles first.</div>}
          </div>
        </div>
        <div className="panel">
          <h3>Scene looks</h3>
          <div className="takes-grid">
            {project.scenes.map((s) => (
              <div className="take-card" key={s.id}>
                {mediaUrl(s.reference_path) ? (
                  <img src={mediaUrl(s.reference_path)} alt={s.name} />
                ) : (
                  <div className="board-thumb">{s.name}</div>
                )}
                <div className="body">
                  <strong>{s.name}</strong>
                  <div className="muted">{s.visual_notes || s.mood || 'Add notes in Profiles'}</div>
                </div>
              </div>
            ))}
            {project.scenes.length === 0 && <div className="empty">Add scenes in Profiles first.</div>}
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
        Default is <strong>AMD Low VRAM</strong> so friends with smaller cards can use Framewright.
        On your R9700 32GB, switch to the R9700 preset when you want longer / sharper clips.
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
          <label>ComfyUI URL (ROCm)</label>
          <input
            value={draft.comfyui_url}
            onChange={(e) => setDraft({ ...draft, comfyui_url: e.target.value })}
          />
        </div>
        <div className="muted">
          Status now — Ollama: {health?.ollama ? 'connected' : 'offline (built-in planner)'} ·
          ComfyUI: {health?.comfyui ? 'connected' : 'offline (preview media)'} · Data:{' '}
          {health?.data_dir}
        </div>
        <button className="btn acid" type="button" onClick={save}>
          Save settings
        </button>
      </div>
    </div>
  )
}
