import { useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api, mediaUrl } from './api'
import { LEARN_TOPICS, type LearnSectionId } from './learning'
import {
  CAPTION_STYLES,
  DIRECTOR_FILTERS,
  filterCss,
  formatTimecode,
} from './directorCatalog'
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
  AgentProvider,
  AgentProviderInfo,
  CharacterProfile,
  ContinuityData,
  EngineJob,
  EngineStatus,
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
  Take,
  TimelineClip,
} from './types'
import './styles.css'

const NAV_GROUPS: { id: string; label: string; items: { id: TabId; label: string }[] }[] = [
  {
    id: 'start',
    label: 'Start',
    items: [
      { id: 'inspiration', label: 'Inspiration' },
      { id: 'agent', label: 'Agent' },
      { id: 'profiles', label: 'Profiles' },
      { id: 'time', label: 'Time & Style' },
      { id: 'creator', label: 'Creator' },
    ],
  },
  {
    id: 'story',
    label: 'Story',
    items: [
      { id: 'shots', label: 'Shots' },
      { id: 'storyboard', label: 'Storyboard' },
      { id: 'characters', label: 'Characters' },
    ],
  },
  {
    id: 'make',
    label: 'Make',
    items: [
      { id: 'generate', label: 'Generate' },
      { id: 'audio', label: 'Audio' },
      { id: 'upsample', label: 'Upsample' },
      { id: 'models', label: 'Models' },
    ],
  },
  {
    id: 'edit',
    label: 'Edit',
    items: [
      { id: 'continuity', label: 'Continuity' },
      { id: 'rehearsal', label: 'Rehearsal' },
      { id: 'sampling', label: 'Sampling' },
      { id: 'director', label: 'Director' },
    ],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      { id: 'learning', label: 'Learning' },
      { id: 'sources', label: 'My links' },
      { id: 'addons', label: 'Add-ons' },
      { id: 'info', label: 'Info' },
      { id: 'settings', label: 'Settings' },
    ],
  },
]

function groupForTab(tabId: TabId): string {
  return NAV_GROUPS.find((g) => g.items.some((i) => i.id === tabId))?.id || 'start'
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
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({
    start: true,
    story: false,
    make: false,
    edit: false,
    system: false,
  })
  const [navOpen, setNavOpen] = useState(true)
  const [inspirationSeed, setInspirationSeed] = useState<InspirationSeed | null>(null)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)

  const goTab = (id: TabId) => {
    setTab(id)
    const gid = groupForTab(id)
    setOpenGroups((prev) => ({ ...prev, [gid]: true }))
  }
  const [showNew, setShowNew] = useState(false)
  const [homeView, setHomeView] = useState<'home' | 'learning' | 'sources'>('home')
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
      goTab('agent')
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
      goTab('profiles')
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
      goTab('shots')
      notify('Shot list ready — edit anything before generating.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
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
            <span className={`pill ${health?.agent_reachable ? 'on' : 'off'}`}>
              Agent{' '}
              {health?.agent_label || health?.agent_provider || (health?.ollama ? 'Ollama' : 'built-in')}
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
            <button className="btn secondary" type="button" onClick={() => setHomeView('learning')}>
              Learning guide
            </button>
            <button className="btn ghost" type="button" onClick={() => setHomeView('sources')}>
              My GitHub / HF
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
            {NAV_GROUPS.map((group) => {
              const open = !!openGroups[group.id]
              return (
                <div className="nav-group" key={group.id}>
                  <button
                    type="button"
                    className={`nav-group-btn ${open ? 'open' : ''}`}
                    onClick={() =>
                      setOpenGroups((prev) => ({ ...prev, [group.id]: !prev[group.id] }))
                    }
                    aria-expanded={open}
                  >
                    <span>{group.label}</span>
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
            onTry={(clip) => {
              setInspirationSeed({
                mode: clip.mode,
                prompt: clip.prompt,
                title: clip.title,
              })
              goTab('generate')
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
      </div>
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
      <p className="hint">
        Every field is editable. With <em>continue from previous</em> on, Generate runs as i2v from
        the prior take’s last frame so scenes stay in the same world.
      </p>
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
  const [loraScale, setLoraScale] = useState(0.8)
  const [loras, setLoras] = useState<LoraFile[]>([])
  const [lorasPath, setLorasPath] = useState('')
  const [busy, setBusy] = useState(false)
  const [estimate, setEstimate] = useState<GpuEstimate | null>(null)
  const [estimating, setEstimating] = useState(false)
  const [continuePrev, setContinuePrev] = useState(project.continue_from_previous !== false)
  const [continueInfo, setContinueInfo] = useState<string | null>(null)

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
    setLoras(e.loras || [])
    setLorasPath(e.loras_path || '')
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

  const estimatePayload = () => ({
    mode,
    model_id: modelId || undefined,
    width,
    height,
    quality,
    duration_sec: durationSec,
    cpu_offload: true,
    preset_id: project.preset_id,
  })

  useEffect(() => {
    let cancelled = false
    setEstimating(true)
    const payload = estimatePayload()
    if (continuePrev && (mode === 't2v' || mode === 'i2v')) {
      payload.mode = 'i2v'
    }
    api
      .engineEstimate(payload)
      .then((e) => {
        if (!cancelled) setEstimate(e)
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setEstimating(false)
      })
    return () => {
      cancelled = true
    }
  }, [mode, modelId, width, height, quality, durationSec, project.preset_id, continuePrev])

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
    if (estimate && !estimate.can_queue) {
      notify(estimate.warnings[0] || 'This job will not fit on your GPU. Lower settings first.')
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
        project_id: project.id,
        shot_id: shotId || undefined,
        cpu_offload: true,
        width,
        height,
        quality,
        duration_sec: durationSec,
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
          ? `Queued continuation i2v · ${job.model_label}${eta}`
          : `Queued ${job.mode.toUpperCase()} · ${job.model_label}${eta}`,
      )
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
            {loraPath && (
              <div className="field" style={{ marginTop: 10 }}>
                <label>LoRA strength {loraScale.toFixed(2)}</label>
                <input
                  type="range"
                  min={0.1}
                  max={1.2}
                  step={0.05}
                  value={loraScale}
                  onChange={(e) => setLoraScale(Number(e.target.value))}
                />
              </div>
            )}
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

          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={continuePrev}
              onChange={(e) => setContinuePrev(e.target.checked)}
            />
            <span>
              Continue from previous video’s last frame (i2v chain)
              {continueInfo ? <span className="tiny"> — {continueInfo}</span> : null}
            </span>
          </label>

          <div className={`gpu-fit fit-${estimate?.fit || 'unknown'}`}>
            <header>
              <strong>Can my GPU do this?</strong>
              <span>{estimating ? '…' : estimate?.eta_label || '—'}</span>
            </header>
            {estimate ? (
              <>
                <div className="muted tiny">
                  {estimate.device_name}
                  {estimate.vram_available_gb != null
                    ? ` · ${estimate.vram_available_gb} GB free`
                    : ''}{' '}
                  · needs ~{estimate.vram_estimate_gb} GB · {estimate.width}×{estimate.height} ·{' '}
                  {estimate.frames} frames
                </div>
                {estimate.warnings.map((w) => (
                  <div className="fit-warn" key={w}>
                    {w}
                  </div>
                ))}
                {estimate.advice.map((a) => (
                  <div className="muted tiny" key={a}>
                    {a}
                  </div>
                ))}
                {estimate.will_preview && (
                  <div className="muted tiny">Will run as preview until engine weights are ready.</div>
                )}
              </>
            ) : (
              <div className="muted tiny">Checking VRAM fit…</div>
            )}
          </div>

          <button
            className="btn acid"
            type="button"
            disabled={busy || (estimate != null && !estimate.can_queue)}
            onClick={run}
          >
            Generate {mode.toUpperCase()}
            {estimate?.eta_label ? ` · ${estimate.eta_label}` : ''}
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
                      {take.is_rehearsal ? ' · rehearsal' : ''}
                      {take.rejected ? ' · rejected' : ''}
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

function clipDuration(clip: TimelineClip, shotDur: number): number {
  const tin = clip.trim_in ?? clip.start_sec ?? 0
  const tout =
    clip.trim_out ??
    clip.end_sec ??
    shotDur ??
    3
  const raw = Math.max(0.2, Number(tout) - Number(tin))
  const speed = clip.speed && clip.speed > 0 ? clip.speed : 1
  return raw / speed
}

function normalizeClip(c: TimelineClip, order: number, shotDur = 3): TimelineClip {
  const id = c.id.startsWith('temp_') ? `clip_${c.shot_id}` : c.id
  const trimOut = c.trim_out ?? c.end_sec ?? shotDur
  return {
    id,
    shot_id: c.shot_id,
    take_id: c.take_id ?? null,
    start_sec: c.start_sec ?? 0,
    end_sec: c.end_sec ?? trimOut,
    trim_in: c.trim_in ?? c.start_sec ?? 0,
    trim_out: trimOut,
    speed: c.speed ?? 1,
    pinned: c.pinned ?? true,
    order,
    caption: c.caption ?? '',
    caption_style: c.caption_style || 'bottom',
    filter_id: c.filter_id || 'none',
    filter_intensity: c.filter_intensity ?? 1,
    director_note: c.director_note ?? '',
  }
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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [playhead, setPlayhead] = useState(0)

  const clips: TimelineClip[] = useMemo(() => {
    if (project.timeline.length > 0) {
      return [...project.timeline].sort((a, b) => a.order - b.order)
    }
    return project.shots
      .filter((s) => s.pinned_take_id)
      .map((s, i) => ({
        id: `temp_${s.id}`,
        shot_id: s.id,
        take_id: s.pinned_take_id,
        start_sec: 0,
        end_sec: s.duration_sec,
        trim_in: 0,
        trim_out: s.duration_sec,
        speed: 1,
        pinned: true,
        order: i,
        caption: '',
        caption_style: 'bottom',
        filter_id: project.default_filter_id || 'none',
        filter_intensity: 1,
        director_note: '',
      }))
  }, [project])

  const layout = useMemo(() => {
    let cursor = 0
    return clips.map((clip) => {
      const shot = project.shots.find((s) => s.id === clip.shot_id)
      const dur = clipDuration(clip, shot?.duration_sec || 3)
      const seg = { clip, shot, start: cursor, end: cursor + dur, dur }
      cursor += dur
      return seg
    })
  }, [clips, project.shots])

  const totalSec = layout.length ? layout[layout.length - 1].end : 0
  const selected = clips.find((c) => c.id === selectedId) || clips[0] || null
  const selectedSeg = layout.find((s) => s.clip.id === selected?.id)
  const selectedTake = selected
    ? project.takes.find((t) => t.id === selected.take_id)
    : undefined
  const readyCount = clips.filter((c) => c.take_id).length
  const pct = clips.length ? Math.round((readyCount / clips.length) * 100) : 0

  const persist = async (nextClips: TimelineClip[], msg?: string) => {
    setBusy(true)
    try {
      const payload = nextClips.map((c, order) => {
        const shot = project.shots.find((s) => s.id === c.shot_id)
        return normalizeClip(c, order, shot?.duration_sec || 3)
      })
      const p = await api.setTimeline(project.id, payload)
      setProject(p)
      if (msg) notify(msg)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const patchSelected = async (patch: Partial<TimelineClip>) => {
    if (!selected) return
    const next = clips.map((c) => (c.id === selected.id ? { ...c, ...patch } : c))
    await persist(next)
  }

  const buildFromPins = async () => {
    const built = project.shots
      .filter((s) => s.pinned_take_id)
      .map((s, order) =>
        normalizeClip(
          {
            id: `clip_${s.id}`,
            shot_id: s.id,
            take_id: s.pinned_take_id,
            start_sec: 0,
            end_sec: s.duration_sec,
            trim_in: 0,
            trim_out: s.duration_sec,
            speed: 1,
            pinned: true,
            order,
            caption: '',
            caption_style: 'bottom',
            filter_id: project.default_filter_id || 'none',
            filter_intensity: 1,
            director_note: '',
          },
          order,
          s.duration_sec,
        ),
      )
    await persist(built, 'Timeline built from pinned takes.')
  }

  const move = async (index: number, dir: -1 | 1) => {
    const next = clips.map((c) => ({ ...c }))
    const j = index + dir
    if (j < 0 || j >= next.length) return
    ;[next[index], next[j]] = [next[j], next[index]]
    await persist(next)
  }

  const cutClip = async () => {
    if (!selected) return
    const shot = project.shots.find((s) => s.id === selected.shot_id)
    const dur = clipDuration(selected, shot?.duration_sec || 3)
    if (dur < 0.6) {
      notify('Clip too short to cut — trim instead.')
      return
    }
    const tin = selected.trim_in ?? 0
    const tout = selected.trim_out ?? selected.end_sec ?? dur
    const mid = tin + (Number(tout) - tin) / 2
    const a: TimelineClip = {
      ...selected,
      id: selected.id.startsWith('temp_') ? `clip_${selected.shot_id}_a` : `${selected.id}_a`,
      trim_out: mid,
      end_sec: mid,
    }
    const b: TimelineClip = {
      ...selected,
      id: `clip_${selected.shot_id}_${Date.now().toString(36)}`,
      trim_in: mid,
      start_sec: mid,
      caption: selected.caption || '',
    }
    const idx = clips.findIndex((c) => c.id === selected.id)
    const next = [...clips.slice(0, idx), a, b, ...clips.slice(idx + 1)]
    setSelectedId(a.id)
    await persist(next, 'Cut into two clips.')
  }

  const removeClip = async () => {
    if (!selected) return
    const next = clips.filter((c) => c.id !== selected.id)
    setSelectedId(next[0]?.id || null)
    await persist(next, 'Clip removed from timeline.')
  }

  const applyFilterAll = async (filterId: string) => {
    const next = clips.map((c) => ({ ...c, filter_id: filterId }))
    const p = await api.putProject({ ...project, default_filter_id: filterId })
    setProject(p)
    await persist(next, `Filter “${filterId}” on all clips.`)
  }

  useEffect(() => {
    if (!selectedId && clips[0]) setSelectedId(clips[0].id)
  }, [clips, selectedId])

  return (
    <div className="director">
      <p className="hint">
        Cut, trim, caption, and grade on a real timeline. The playhead shows where you are in the
        cut — click a block to edit that scene.
      </p>

      <div className="director-progress panel">
        <div className="inline-actions" style={{ justifyContent: 'space-between' }}>
          <strong>
            Progress · {readyCount}/{clips.length} clips with media · {pct}%
          </strong>
          <span className="muted tiny">
            Total {formatTimecode(totalSec)} / target {formatTimecode(project.target_duration_sec || 0)}
          </span>
        </div>
        <div className="progress" style={{ marginTop: 8 }}>
          <div style={{ width: `${pct}%` }} />
        </div>
        <div className="muted tiny" style={{ marginTop: 6 }}>
          Playhead {formatTimecode(playhead)}
          {selectedSeg
            ? ` · editing “${selectedSeg.shot?.title || 'clip'}” (${formatTimecode(selectedSeg.start)}–${formatTimecode(selectedSeg.end)})`
            : ''}
        </div>
      </div>

      <div className="inline-actions" style={{ flexWrap: 'wrap' }}>
        <button className="btn acid" type="button" disabled={busy} onClick={buildFromPins}>
          Build from pins
        </button>
        <button
          className="btn secondary"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const p = await api.generateCaptions(project.id, false)
              setProject(p)
              notify('Captions generated from dialogue / action — edit any line below.')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Generate captions
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy || !selected}
          onClick={cutClip}
        >
          Cut clip in half
        </button>
        <button className="btn ghost" type="button" disabled={busy || !selected} onClick={removeClip}>
          Remove from timeline
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={() => window.open(api.captionsSrtUrl(project.id), '_blank')}
        >
          Download .srt
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const pack = await api.exportNle(project.id)
              notify(`NLE package · ${pack.clip_count} clips`)
              window.open(pack.download_url, '_blank')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Export EDL / FCPXML
        </button>
      </div>

      {clips.length === 0 ? (
        <div className="empty">Pin takes in Sampling, then Build from pins.</div>
      ) : (
        <>
          <div className="panel director-ruler">
            <h3>Timeline</h3>
            <div className="tl-ruler" aria-label="Timeline">
              {layout.map((seg, i) => {
                const widthPct = totalSec > 0 ? (seg.dur / totalSec) * 100 : 100 / layout.length
                const active = selected?.id === seg.clip.id
                return (
                  <button
                    key={seg.clip.id}
                    type="button"
                    className={`tl-block ${active ? 'active' : ''} ${seg.clip.take_id ? 'has-media' : 'missing'}`}
                    style={{ flexGrow: seg.dur, flexBasis: `${widthPct}%` }}
                    onClick={() => {
                      setSelectedId(seg.clip.id)
                      setPlayhead(seg.start)
                    }}
                    title={`${seg.shot?.title} · ${formatTimecode(seg.dur)}`}
                  >
                    <span className="tl-idx">{i + 1}</span>
                    <span className="tl-name">{seg.shot?.title || 'Clip'}</span>
                    <span className="tl-dur">{formatTimecode(seg.dur)}</span>
                    {seg.clip.caption ? <span className="tl-cap">CC</span> : null}
                  </button>
                )
              })}
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(totalSec, 0.1)}
              step={0.1}
              value={Math.min(playhead, totalSec)}
              onChange={(e) => {
                const v = Number(e.target.value)
                setPlayhead(v)
                const hit = layout.find((s) => v >= s.start && v < s.end) || layout[layout.length - 1]
                if (hit) setSelectedId(hit.clip.id)
              }}
              aria-label="Playhead"
            />
          </div>

          <div className="gen-layout">
            <div className="panel">
              <h3>Viewer</h3>
              {selected ? (
                <div
                  className="director-viewer"
                  style={{
                    filter: filterCss(selected.filter_id, selected.filter_intensity ?? 1),
                  }}
                >
                  {mediaUrl(selectedTake?.thumb_path || selectedTake?.media_path) ? (
                    <img
                      src={mediaUrl(selectedTake?.thumb_path || selectedTake?.media_path)}
                      alt=""
                    />
                  ) : (
                    <div className="empty">No media on this clip yet.</div>
                  )}
                  {(project.captions_enabled !== false && selected.caption) && (
                    <div className={`caption-overlay style-${selected.caption_style || 'bottom'}`}>
                      {selected.caption}
                    </div>
                  )}
                </div>
              ) : (
                <div className="empty">Select a clip on the timeline.</div>
              )}
              {selected && (
                <div className="inline-actions" style={{ marginTop: 10 }}>
                  <button
                    className="btn ghost tiny"
                    type="button"
                    disabled={busy}
                    onClick={() => move(clips.findIndex((c) => c.id === selected.id), -1)}
                  >
                    ← Earlier
                  </button>
                  <button
                    className="btn ghost tiny"
                    type="button"
                    disabled={busy}
                    onClick={() => move(clips.findIndex((c) => c.id === selected.id), 1)}
                  >
                    Later →
                  </button>
                </div>
              )}
            </div>

            <div className="panel">
              <h3>Edit scene</h3>
              {!selected ? (
                <div className="empty">Pick a timeline block.</div>
              ) : (
                <>
                  <div className="muted tiny" style={{ marginBottom: 10 }}>
                    {selectedSeg?.shot?.title} · trim & speed adjust the cut without regenerating
                  </div>
                  <div className="controls-grid">
                    <div className="field">
                      <label>Trim in (sec)</label>
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={selected.trim_in ?? 0}
                        onChange={(e) =>
                          patchSelected({ trim_in: Number(e.target.value), start_sec: Number(e.target.value) })
                        }
                      />
                    </div>
                    <div className="field">
                      <label>Trim out (sec)</label>
                      <input
                        type="number"
                        min={0.2}
                        step={0.1}
                        value={selected.trim_out ?? selected.end_sec ?? 3}
                        onChange={(e) =>
                          patchSelected({
                            trim_out: Number(e.target.value),
                            end_sec: Number(e.target.value),
                          })
                        }
                      />
                    </div>
                    <div className="field">
                      <label>Speed</label>
                      <select
                        value={String(selected.speed ?? 1)}
                        onChange={(e) => patchSelected({ speed: Number(e.target.value) })}
                      >
                        {[0.5, 0.75, 1, 1.25, 1.5, 2].map((s) => (
                          <option key={s} value={s}>
                            {s}×
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="field">
                    <label>Caption (editable)</label>
                    <textarea
                      rows={3}
                      value={selected.caption || ''}
                      onChange={(e) => patchSelected({ caption: e.target.value })}
                      placeholder="Spoken line or on-screen text…"
                    />
                  </div>
                  <div className="field">
                    <label>Caption style</label>
                    <select
                      value={selected.caption_style || 'bottom'}
                      onChange={(e) => patchSelected({ caption_style: e.target.value })}
                    >
                      {CAPTION_STYLES.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label} — {s.blurb}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="field">
                    <label>Filter on this clip</label>
                    <select
                      value={selected.filter_id || 'none'}
                      onChange={(e) => patchSelected({ filter_id: e.target.value })}
                    >
                      {DIRECTOR_FILTERS.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.label} — {f.blurb}
                        </option>
                      ))}
                    </select>
                  </div>
                  {(selected.filter_id || 'none') !== 'none' && (
                    <div className="field">
                      <label>Filter strength {(selected.filter_intensity ?? 1).toFixed(2)}</label>
                      <input
                        type="range"
                        min={0.1}
                        max={1}
                        step={0.05}
                        value={selected.filter_intensity ?? 1}
                        onChange={(e) => patchSelected({ filter_intensity: Number(e.target.value) })}
                      />
                    </div>
                  )}
                  <div className="field">
                    <label>Director note</label>
                    <input
                      value={selected.director_note || ''}
                      onChange={(e) => patchSelected({ director_note: e.target.value })}
                      placeholder="e.g. tighten pause before turn"
                    />
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="panel">
            <h3>Look across the cut</h3>
            <p className="muted tiny">Apply one filter to every clip, or keep grades per scene above.</p>
            <div className="provider-grid">
              {DIRECTOR_FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  className={`mode-chip ${project.default_filter_id === f.id ? 'active' : ''}`}
                  disabled={busy}
                  onClick={() => applyFilterAll(f.id)}
                >
                  <strong>{f.label}</strong>
                  <span>{f.blurb}</span>
                </button>
              ))}
            </div>
          </div>
        </>
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
  const [providers, setProviders] = useState<AgentProviderInfo[]>([])
  const [keyDraft, setKeyDraft] = useState('')

  useEffect(() => setDraft(settings), [settings])
  useEffect(() => {
    api.agentProviders().then((r) => setProviders(r.providers)).catch(() => undefined)
  }, [])

  const selected = providers.find((p) => p.id === draft.agent_provider)

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

  return (
    <div>
      <p className="hint">
        Default is AMD Low VRAM so friends with smaller cards can use Framewright. Pick a free local
        agent (Ollama / built-in) or plug in a paid LLM API for smarter shot planning.
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

        <h3 style={{ gridColumn: '1 / -1', margin: '8px 0 0' }}>Agent LLM</h3>
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
                Stored only in your local Framewright settings file — never sent to Framewright
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
          CPU offload (saves VRAM)
        </label>
        <div className="muted" style={{ gridColumn: '1 / -1' }}>
          Engine: built-in · Torch: {health?.torch ? 'yes' : 'no'} · GPU:{' '}
          {health?.gpu ? health.device_name : 'not ready'} · Agent:{' '}
          {health?.agent_detail || health?.agent_label || '—'} · Data: {health?.data_dir}
        </div>
        <button className="btn acid" type="button" onClick={save}>
          Save settings
        </button>
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
        Promote winners, then generate high quality in Generate / Sampling.
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
        <button className="btn acid" type="button" disabled={busy} onClick={run}>
          Run rehearsal pass ({project.shots.length} shots)
        </button>
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
  const [loras, setLoras] = useState<LoraFile[]>([])
  const [lorasPath, setLorasPath] = useState('')

  const load = async () => {
    const pack = await api.engineLoras()
    setLoras(pack.loras)
    setLorasPath(pack.path)
  }

  useEffect(() => {
    load().catch((e) => notify(String(e.message || e)))
  }, [])

  return (
    <div>
      <div className="panel">
        <h3>Models</h3>
        <p className="hint">
          Switch and download models from the Generate tab’s model menu. Files land in the app’s{' '}
          <code>models/</code> folder (Pinokio-style).
        </p>
        <p className="muted">
          Tip: open <strong>Info</strong> for the full folder map. Pick a model in Generate and it
          will fetch on first real GPU run.
        </p>
      </div>
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="inline-actions" style={{ justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0 }}>LoRAs in folder</h3>
          <button
            className="btn ghost tiny"
            type="button"
            onClick={async () => {
              await load()
              notify(loras.length ? `Scanned ${lorasPath}` : 'Folder empty — drop files into loras/.')
            }}
          >
            Rescan
          </button>
        </div>
        <p className="muted tiny">
          Drop <code>.safetensors</code> / <code>.pt</code> into <code>loras/</code>
          {lorasPath ? ` → ${lorasPath}` : ''}. They appear in Generate’s LoRA dropdown.
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
      <button className="btn acid" type="button" onClick={() => notify('Check addons/ in your Framewright folder.')}>
        Open folder tip
      </button>
    </div>
  )
}

function LearningTab({ onGo }: { onGo: (id: TabId) => void }) {
  const [active, setActive] = useState<LearnSectionId>('start-here')
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
        Personalise Framewright with <strong>your</strong> GitHub and Hugging Face pages. Import
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
            <div className="muted tiny">Stored only in local settings — never sent to Framewright cloud.</div>
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
            Import to Framewright
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
        Pinokio-style layout — everything sits in the Framewright folder you downloaded. No hidden
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
