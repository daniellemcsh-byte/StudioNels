import { useEffect, useMemo, useRef, useState } from 'react'
import { api, mediaUrl } from './api'
import type {
  CompiledShot,
  EngineModel,
  FilmMemory,
  Project,
  PropProfile,
  Shot,
  StoryboardCheck,
  StoryboardIssue,
  Take,
} from './types'

const CAMERAS = ['wide', 'medium', 'close-up', 'extreme close-up', 'tracking', 'pov', 'overhead', 'aerial', 'low-angle', 'insert', 'handheld']
const TIMES = ['', 'dawn', 'morning', 'midday', 'afternoon', 'golden hour', 'dusk', 'night', 'midnight']

const EMPTY_MEMORY: FilmMemory = {
  world: '',
  era: '',
  tone: '',
  palette: '',
  camera_language: '',
  sound_world: '',
  motifs: '',
  avoid: '',
  facts: [],
  render_model_id: null,
}

type Draft = {
  title: string
  action: string
  dialogue: string
  camera: string
  duration_sec: number
  prompt: string
  prompt_locked: boolean
  storyboard_note: string
  director_notes: string
  scene_id: string
  character_ids: string[]
  prop_ids: string[]
  time_of_day: string
  mood: string
  lens: string
  movement: string
  sound: string
  state_after: string
}

function draftFrom(shot: Shot | null, n: number): Draft {
  return {
    title: shot?.title || `Shot ${n}`,
    action: shot?.action || '',
    dialogue: shot?.dialogue || '',
    camera: shot?.camera || 'medium',
    duration_sec: shot?.duration_sec || 3,
    prompt: shot?.prompt || '',
    prompt_locked: !!shot?.prompt_locked,
    storyboard_note: shot?.storyboard_note || '',
    director_notes: shot?.director_notes || '',
    scene_id: shot?.scene_id || '',
    character_ids: shot?.character_ids || [],
    prop_ids: shot?.prop_ids || [],
    time_of_day: shot?.time_of_day || '',
    mood: shot?.mood || '',
    lens: shot?.lens || '',
    movement: shot?.movement || '',
    sound: shot?.sound || '',
    state_after: shot?.state_after || '',
  }
}

const LEVEL_ICON: Record<StoryboardIssue['level'], string> = { error: '●', warn: '▲', info: '◆' }

export default function StoryboardStudio({
  project,
  setProject,
  busy,
  setBusy,
  notify,
  onGenerate,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
  onGenerate: (ids?: string[]) => void
}) {
  const [models, setModels] = useState<EngineModel[]>([])
  const [compiled, setCompiled] = useState<Record<string, CompiledShot>>({})
  const [profile, setProfile] = useState<{ label: string; tips: string[] } | null>(null)
  const [check, setCheck] = useState<StoryboardCheck | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft>(draftFrom(null, 1))
  const [memory, setMemory] = useState<FilmMemory>({ ...EMPTY_MEMORY, ...(project.memory || {}) })
  const [props, setProps] = useState<PropProfile[]>(project.props || [])
  const [memoryDirty, setMemoryDirty] = useState(false)
  const [newFact, setNewFact] = useState('')
  const [newProp, setNewProp] = useState({ name: '', description: '', owner_id: '' })
  const [suggestions, setSuggestions] = useState<Array<{ kind: string; value: string; reason: string }>>([])
  const [showIssues, setShowIssues] = useState(true)
  // shot id -> keyframe job id, while the still is being made
  const [keyframeJobs, setKeyframeJobs] = useState<Record<string, string>>({})
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({})

  // Poll keyframe jobs; reload the project when one finishes so the still appears.
  useEffect(() => {
    const pending = Object.entries(keyframeJobs)
    if (pending.length === 0) return
    const t = window.setInterval(async () => {
      let changed = false
      const next = { ...keyframeJobs }
      for (const [shotId, jobId] of pending) {
        try {
          const j = await api.engineJob(jobId)
          if (j.status !== 'queued' && j.status !== 'running') {
            delete next[shotId]
            changed = true
            if (j.status !== 'done') notify(`Keyframe failed: ${String(j.error || j.message).slice(0, 160)}`)
          }
        } catch {
          delete next[shotId]
          changed = true
        }
      }
      if (changed) {
        setKeyframeJobs(next)
        try {
          setProject(await api.getProject(project.id))
        } catch {
          /* next refresh will catch up */
        }
      }
    }, 2500)
    return () => window.clearInterval(t)
  }, [keyframeJobs, project.id, setProject, notify])

  const makeKeyframe = async (shot: Shot) => {
    try {
      const r = await api.makeKeyframe(project.id, shot.id)
      setKeyframeJobs((k) => ({ ...k, [shot.id]: r.job_id }))
    } catch (err) {
      notify(String((err as Error).message || err))
    }
  }

  const uploadKeyframe = (shot: Shot, file: File) =>
    run(async () => {
      const up = await api.engineUpload(file, 'image')
      setProject(await api.patchShot(project.id, shot.id, { keyframe_path: up.path }))
      notify('Keyframe set — this shot will start from your image.')
    })

  const renderModelId = memory.render_model_id || ''

  // Keep local memory in sync when the project changes elsewhere (unless editing it).
  useEffect(() => {
    if (memoryDirty) return
    setMemory({ ...EMPTY_MEMORY, ...(project.memory || {}) })
    setProps(project.props || [])
  }, [project, memoryDirty])

  useEffect(() => {
    api
      .engine()
      .then((e) => setModels(e.models.filter((m) => m.kind === 'video' || m.kind === 'image')))
      .catch(() => undefined)
  }, [])

  // Re-compile prompts + re-run the continuity check whenever the board or model changes.
  useEffect(() => {
    let alive = true
    const t = window.setTimeout(() => {
      Promise.all([
        api.storyboardCompiled(project.id, renderModelId || null),
        api.storyboardCheck(project.id, renderModelId || null),
      ])
        .then(([c, k]) => {
          if (!alive) return
          setCompiled(Object.fromEntries(c.shots.map((s) => [s.shot_id, s])))
          setProfile(c.profile)
          setCheck(k)
          if (!renderModelId && c.model_id) setMemory((m) => ({ ...m, render_model_id: c.model_id }))
        })
        .catch(() => undefined)
    }, 250)
    return () => {
      alive = false
      window.clearTimeout(t)
    }
  }, [project.id, project.updated_at, renderModelId])

  const takeMap = useMemo(() => {
    const m = new Map<string, Take>()
    for (const t of project.takes) {
      if (!m.has(t.shot_id)) m.set(t.shot_id, t)
      const shot = project.shots.find((s) => s.id === t.shot_id)
      if (shot?.pinned_take_id === t.id) m.set(t.shot_id, t)
    }
    return m
  }, [project])

  const issuesByShot = useMemo(() => {
    const m = new Map<string, StoryboardIssue[]>()
    for (const i of check?.issues || []) {
      if (!i.shot_id) continue
      m.set(i.shot_id, [...(m.get(i.shot_id) || []), i])
    }
    return m
  }, [check])

  const total = check?.total_sec ?? project.shots.reduce((a, s) => a + (s.duration_sec || 0), 0)
  const target = project.target_duration_sec || 0
  const pct = target ? Math.min(100, Math.round((total / target) * 100)) : 0

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    try {
      await fn()
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const saveMemory = (next: FilmMemory = memory, nextProps: PropProfile[] = props, quiet = false) =>
    run(async () => {
      const p = await api.putMemory(project.id, next, nextProps)
      setMemoryDirty(false)
      setProject(p)
      if (!quiet) notify('Film memory saved — every shot prompt now uses it.')
    })

  const editMemory = (patch: Partial<FilmMemory>) => {
    setMemory((m) => ({ ...m, ...patch }))
    setMemoryDirty(true)
  }

  const openEdit = (shot: Shot | null) => {
    setEditingId(shot ? shot.id : 'new')
    setDraft(draftFrom(shot, project.shots.length + 1))
  }

  const saveCard = () =>
    run(async () => {
      const body = {
        ...draft,
        title: draft.title.trim() || 'Untitled shot',
        duration_sec: Number(draft.duration_sec) || 3,
        scene_id: draft.scene_id || null,
      }
      const p =
        editingId === 'new' || !editingId
          ? await api.addShot(project.id, body)
          : await api.patchShot(project.id, editingId, body)
      setProject(p)
      setEditingId(null)
      notify(editingId === 'new' ? 'Shot added to the board.' : 'Card saved.')
    })

  const moveShot = (shot: Shot, dir: -1 | 1) => {
    const next = Math.max(0, Math.min(project.shots.length - 1, shot.index + dir))
    if (next === shot.index) return
    void run(async () => setProject(await api.patchShot(project.id, shot.id, { index: next })))
  }

  const learn = () =>
    run(async () => {
      const r = await api.learnMemory(project.id)
      setSuggestions(r.suggestions)
      notify(r.suggestions.length ? `${r.suggestions.length} things worth remembering.` : 'Nothing new to remember yet.')
    })

  const acceptSuggestion = async (s: { kind: string; value: string }) => {
    setSuggestions((all) => all.filter((x) => x !== s))
    if (s.kind === 'character') {
      await run(async () => setProject(await api.addCharacter(project.id, { name: s.value })))
      notify(`${s.value} added to the cast — give them a look in Characters.`)
    } else if (s.kind === 'prop') {
      const next = [...props, { id: `prop_${Date.now().toString(36)}`, name: s.value, description: '', owner_id: null }]
      setProps(next)
      await saveMemory(memory, next, true)
    } else if (s.kind === 'world') {
      const next = { ...memory, world: s.value }
      setMemory(next)
      await saveMemory(next, props, true)
    }
  }

  const jumpTo = (shotId: string | null) => {
    if (!shotId) return
    cardRefs.current[shotId]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const renderModels = [...models].sort((a, b) => Number(!!b.installed) - Number(!!a.installed))

  return (
    <div className="sb">
      <div className="panel sb-top">
        <div className="sb-runtime">
          <div className="sb-runtime-label">
            <strong>{project.shots.length}</strong> shots · <strong>{total.toFixed(1)}s</strong>
            {target ? ` of ${target.toFixed(0)}s target` : ''}
          </div>
          {target > 0 && (
            <div className="sb-meter" aria-label={`Runtime ${pct}% of target`}>
              <span style={{ width: `${pct}%` }} className={total > target * 1.25 ? 'over' : ''} />
            </div>
          )}
        </div>
        <label className="sb-model">
          <span>Prompts tuned for</span>
          <select
            value={renderModelId}
            onChange={(e) => {
              const next = { ...memory, render_model_id: e.target.value || null }
              setMemory(next)
              void saveMemory(next, props, true)
            }}
          >
            {renderModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
                {m.installed ? ' · downloaded' : ''}
              </option>
            ))}
          </select>
        </label>
        <div className="sb-check-chips" role="status">
          {check && (
            <button type="button" className="sb-chip-btn" onClick={() => setShowIssues((v) => !v)}>
              <span className="lvl-error">● {check.counts.error}</span>
              <span className="lvl-warn">▲ {check.counts.warn}</span>
              <span className="lvl-info">◆ {check.counts.info}</span>
              <span className="muted tiny">{showIssues ? 'hide' : 'continuity'}</span>
            </button>
          )}
        </div>
        <div className="inline-actions" style={{ gap: 8 }}>
          <button className="btn acid" type="button" disabled={busy} onClick={() => openEdit(null)}>
            + Card
          </button>
          {project.shots.length > 0 && (
            <button
              className="btn ghost"
              type="button"
              disabled={busy}
              title="Make a still for every shot that has none; each shot's video then starts from it"
              onClick={() => {
                for (const s of project.shots) if (!s.keyframe_path && !keyframeJobs[s.id]) void makeKeyframe(s)
              }}
            >
              Make keyframes
            </button>
          )}
          {project.shots.length > 0 && (
            <button className="btn" type="button" disabled={busy} onClick={() => onGenerate()}>
              Generate missing shots
            </button>
          )}
        </div>
      </div>

      <div className="sb-layout">
        <aside className="panel sb-memory" aria-label="Film memory">
          <div className="sb-section-head">
            <h3>Film memory</h3>
            <button className="btn acid tiny" type="button" disabled={busy || !memoryDirty} onClick={() => saveMemory()}>
              {memoryDirty ? 'Save' : 'Saved'}
            </button>
          </div>
          <p className="muted tiny">
            Everything here is written into every shot's prompt, in the format the chosen model reads best.
          </p>
          {(
            [
              ['world', 'World', 'A city where memories are bottled and sold'],
              ['era', 'Era', 'Near future, 2080s'],
              ['tone', 'Tone', 'Melancholic, hopeful'],
              ['palette', 'Palette', 'Magenta, cyan, warm gold'],
              ['camera_language', 'Camera language', 'Anamorphic, shallow depth of field'],
              ['sound_world', 'Sound world', 'Rain on metal, distant synth hum'],
              ['motifs', 'Motifs', 'Glowing jars, reflections'],
              ['avoid', 'Never show', 'Text, logos, daylight'],
            ] as const
          ).map(([key, label, ph]) => (
            <div className="field" key={key}>
              <label>{label}</label>
              <input value={(memory[key] as string) || ''} placeholder={ph} onChange={(e) => editMemory({ [key]: e.target.value })} />
            </div>
          ))}

          <div className="sb-subhead">Cast</div>
          {project.characters.length === 0 ? (
            <p className="muted tiny">No characters yet — add them in Story → Characters.</p>
          ) : (
            <ul className="sb-list">
              {project.characters.map((c) => (
                <li key={c.id}>
                  <strong>{c.name}</strong>
                  <span className={c.character_lock || c.look ? 'muted tiny' : 'fit-warn tiny'}>
                    {c.character_lock || c.look || 'no look yet — may drift between shots'}
                  </span>
                </li>
              ))}
            </ul>
          )}

          <div className="sb-subhead">Props</div>
          <ul className="sb-list">
            {props.map((p) => (
              <li key={p.id}>
                <strong>{p.name}</strong>
                <span className="muted tiny">
                  {p.description || '—'}
                  {p.owner_id ? ` · carried by ${project.characters.find((c) => c.id === p.owner_id)?.name || '?'}` : ''}
                </span>
                <button
                  type="button"
                  className="sb-x"
                  aria-label={`Remove ${p.name}`}
                  onClick={() => {
                    const next = props.filter((x) => x.id !== p.id)
                    setProps(next)
                    void saveMemory(memory, next, true)
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <div className="sb-add-row">
            <input placeholder="Prop name" value={newProp.name} onChange={(e) => setNewProp({ ...newProp, name: e.target.value })} />
            <input
              placeholder="What it looks like"
              value={newProp.description}
              onChange={(e) => setNewProp({ ...newProp, description: e.target.value })}
            />
            <select value={newProp.owner_id} onChange={(e) => setNewProp({ ...newProp, owner_id: e.target.value })}>
              <option value="">No owner</option>
              {project.characters.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <button
              className="btn ghost tiny"
              type="button"
              disabled={!newProp.name.trim()}
              onClick={() => {
                const next = [
                  ...props,
                  {
                    id: `prop_${Date.now().toString(36)}`,
                    name: newProp.name.trim(),
                    description: newProp.description.trim(),
                    owner_id: newProp.owner_id || null,
                  },
                ]
                setProps(next)
                setNewProp({ name: '', description: '', owner_id: '' })
                void saveMemory(memory, next, true)
              }}
            >
              Add prop
            </button>
          </div>

          <div className="sb-subhead">Remembered facts</div>
          <ul className="sb-list">
            {(memory.facts || []).map((f, i) => (
              <li key={`${i}-${f}`}>
                <span className="tiny">{f}</span>
                <button
                  type="button"
                  className="sb-x"
                  aria-label="Forget this"
                  onClick={() => {
                    const next = { ...memory, facts: memory.facts.filter((_, j) => j !== i) }
                    setMemory(next)
                    void saveMemory(next, props, true)
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
          <div className="sb-add-row">
            <input
              placeholder="e.g. Mira's left hand is bandaged from shot 4 on"
              value={newFact}
              onChange={(e) => setNewFact(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newFact.trim()) {
                  const next = { ...memory, facts: [...(memory.facts || []), newFact.trim()] }
                  setMemory(next)
                  setNewFact('')
                  void saveMemory(next, props, true)
                }
              }}
            />
          </div>

          <div className="sb-section-head" style={{ marginTop: 14 }}>
            <span className="sb-subhead" style={{ margin: 0 }}>
              Learn from the board
            </span>
            <button className="btn ghost tiny" type="button" disabled={busy || project.shots.length === 0} onClick={learn}>
              Scan shots
            </button>
          </div>
          {suggestions.map((s) => (
            <div className="sb-suggestion" key={`${s.kind}-${s.value}`}>
              <span>
                <strong>{s.kind}</strong> {s.value} <span className="muted tiny">({s.reason})</span>
              </span>
              <button className="btn acid tiny" type="button" onClick={() => void acceptSuggestion(s)}>
                Remember
              </button>
            </div>
          ))}
        </aside>

        <section className="sb-main">
          {profile && (
            <div className="sb-profile muted tiny">
              Prompts below are written for <strong>{profile.label}</strong>: {profile.tips.join(' ')}
            </div>
          )}

          {showIssues && check && check.issues.length > 0 && (
            <div className="panel sb-issues">
              {check.issues
                .filter((i) => i.code !== 'carry_state')
                .map((i, n) => (
                  <button key={`${i.code}-${i.shot_id}-${n}`} type="button" className={`sb-issue lvl-${i.level}`} onClick={() => jumpTo(i.shot_id)}>
                    <span className="sb-issue-icon">{LEVEL_ICON[i.level]}</span>
                    <span>
                      {i.shot_number ? <strong>Shot {i.shot_number}: </strong> : null}
                      {i.message}
                      {i.fix ? <span className="muted tiny"> — {i.fix}</span> : null}
                    </span>
                  </button>
                ))}
            </div>
          )}

          {editingId && (
            <div className="panel sb-editor">
              <h3>{editingId === 'new' ? 'New card' : 'Edit card'}</h3>
              <div className="sb-editor-grid">
                <div className="field">
                  <label>Title</label>
                  <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
                </div>
                <div className="field">
                  <label>Camera</label>
                  <select value={draft.camera} onChange={(e) => setDraft({ ...draft, camera: e.target.value })}>
                    {CAMERAS.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>Seconds</label>
                  <input
                    type="number"
                    min={0.5}
                    step={0.5}
                    value={draft.duration_sec}
                    onChange={(e) => setDraft({ ...draft, duration_sec: Number(e.target.value) })}
                  />
                </div>
                <div className="field">
                  <label>Location</label>
                  <select value={draft.scene_id} onChange={(e) => setDraft({ ...draft, scene_id: e.target.value })}>
                    <option value="">— none —</option>
                    {project.scenes.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>Time of day</label>
                  <select value={draft.time_of_day} onChange={(e) => setDraft({ ...draft, time_of_day: e.target.value })}>
                    {TIMES.map((t) => (
                      <option key={t} value={t}>
                        {t || 'same as location'}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label>Mood</label>
                  <input value={draft.mood} placeholder="tense, tender…" onChange={(e) => setDraft({ ...draft, mood: e.target.value })} />
                </div>
                <div className="field">
                  <label>Lens</label>
                  <input value={draft.lens} placeholder="35mm, macro…" onChange={(e) => setDraft({ ...draft, lens: e.target.value })} />
                </div>
                <div className="field">
                  <label>Camera move</label>
                  <input value={draft.movement} placeholder="slow push-in, orbit…" onChange={(e) => setDraft({ ...draft, movement: e.target.value })} />
                </div>
              </div>
              <div className="field">
                <label>Action — what happens</label>
                <textarea rows={2} value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })} />
              </div>
              <div className="sb-editor-grid two">
                <div className="field">
                  <label>Dialogue</label>
                  <input value={draft.dialogue} onChange={(e) => setDraft({ ...draft, dialogue: e.target.value })} />
                </div>
                <div className="field">
                  <label>Sound</label>
                  <input value={draft.sound} placeholder="footsteps, rain, low hum…" onChange={(e) => setDraft({ ...draft, sound: e.target.value })} />
                </div>
              </div>
              {project.characters.length > 0 && (
                <div className="field">
                  <label>In this shot</label>
                  <div className="sb-pills">
                    {project.characters.map((c) => {
                      const on = draft.character_ids.includes(c.id)
                      return (
                        <button
                          key={c.id}
                          type="button"
                          className={`mode-pill ${on ? 'active' : ''}`}
                          onClick={() =>
                            setDraft({
                              ...draft,
                              character_ids: on ? draft.character_ids.filter((x) => x !== c.id) : [...draft.character_ids, c.id],
                            })
                          }
                        >
                          {c.name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
              {props.length > 0 && (
                <div className="field">
                  <label>Props</label>
                  <div className="sb-pills">
                    {props.map((p) => {
                      const on = draft.prop_ids.includes(p.id)
                      return (
                        <button
                          key={p.id}
                          type="button"
                          className={`mode-pill ${on ? 'active' : ''}`}
                          onClick={() =>
                            setDraft({ ...draft, prop_ids: on ? draft.prop_ids.filter((x) => x !== p.id) : [...draft.prop_ids, p.id] })
                          }
                        >
                          {p.name}
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
              <div className="field">
                <label>State after this shot (carried into the next)</label>
                <input
                  value={draft.state_after}
                  placeholder="Her coat is soaked; the jar has a crack"
                  onChange={(e) => setDraft({ ...draft, state_after: e.target.value })}
                />
              </div>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={draft.prompt_locked}
                  onChange={(e) => {
                    const locked = e.target.checked
                    const fromCompiled = editingId && editingId !== 'new' ? compiled[editingId]?.prompt : ''
                    setDraft({ ...draft, prompt_locked: locked, prompt: locked && !draft.prompt ? fromCompiled || '' : draft.prompt })
                  }}
                />
                <span>Write the prompt myself (otherwise it is written for the model from memory)</span>
              </label>
              {draft.prompt_locked && (
                <div className="field">
                  <label>My prompt</label>
                  <textarea rows={4} value={draft.prompt} onChange={(e) => setDraft({ ...draft, prompt: e.target.value })} />
                </div>
              )}
              <div className="field">
                <label>Director notes</label>
                <input value={draft.director_notes} onChange={(e) => setDraft({ ...draft, director_notes: e.target.value })} />
              </div>
              <div className="cta-row">
                <button className="btn acid" type="button" disabled={busy} onClick={saveCard}>
                  {editingId === 'new' ? 'Add to board' : 'Save card'}
                </button>
                <button className="btn ghost" type="button" onClick={() => setEditingId(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {project.shots.length === 0 && !editingId ? (
            <div className="empty">Empty board. Add a card, or ask the Agent to plan the film.</div>
          ) : (
            <div className="sb-board">
              {project.shots.map((shot) => {
                const take = takeMap.get(shot.id)
                const keyframeSrc = shot.keyframe_path ? mediaUrl(shot.keyframe_path) : undefined
                const src = mediaUrl(take?.thumb_path || take?.media_path) || keyframeSrc
                const makingKeyframe = !!keyframeJobs[shot.id]
                const c = compiled[shot.id]
                const issues = (issuesByShot.get(shot.id) || []).filter((i) => i.code !== 'carry_state')
                const worst = issues.find((i) => i.level === 'error') || issues.find((i) => i.level === 'warn') || issues[0]
                const cast = project.characters.filter((ch) => (shot.character_ids || []).includes(ch.id))
                const shotProps = props.filter((p) => (shot.prop_ids || []).includes(p.id))
                const scene = project.scenes.find((s) => s.id === shot.scene_id)
                return (
                  <div className={`sb-card ${worst ? `has-${worst.level}` : ''}`} key={shot.id} ref={(el) => {
                      cardRefs.current[shot.id] = el
                    }}>
                    <div className="sb-thumb">
                      {src ? <img src={src} alt="" /> : <span className="sb-thumb-num">{shot.index + 1}</span>}
                      <span className="sb-thumb-meta">
                        {shot.camera} · {shot.duration_sec}s
                      </span>
                      {makingKeyframe && <span className="sb-thumb-badge working">Making keyframe…</span>}
                      {!makingKeyframe && shot.keyframe_path && <span className="sb-thumb-badge">Starts from keyframe</span>}
                    </div>
                    <div className="sb-card-body">
                      <strong>
                        {shot.index + 1}. {shot.title}
                      </strong>
                      <div className="sb-action">{shot.action || shot.storyboard_note || <em className="muted">No action yet</em>}</div>
                      <div className="sb-chips">
                        {scene && <span className="sb-chip">{scene.name}</span>}
                        {(shot.time_of_day || scene?.time_of_day) && <span className="sb-chip">{shot.time_of_day || scene?.time_of_day}</span>}
                        {cast.map((ch) => (
                          <span className="sb-chip cast" key={ch.id}>
                            {ch.name}
                          </span>
                        ))}
                        {shotProps.map((p) => (
                          <span className="sb-chip prop" key={p.id}>
                            {p.name}
                          </span>
                        ))}
                        {shot.dialogue && <span className="sb-chip">“{shot.dialogue.slice(0, 28)}{shot.dialogue.length > 28 ? '…' : ''}”</span>}
                      </div>
                      {shot.state_after && <div className="sb-after tiny">After: {shot.state_after}</div>}
                      {issues.length > 0 && (
                        <ul className="sb-card-issues">
                          {issues.slice(0, 3).map((i, n) => (
                            <li key={n} className={`lvl-${i.level}`}>
                              {LEVEL_ICON[i.level]} {i.message}
                            </li>
                          ))}
                        </ul>
                      )}
                      {c && (
                        <details className="fold sb-prompt">
                          <summary>
                            {c.source === 'locked' ? 'Your prompt' : `Prompt for ${c.label}`} ·{' '}
                            <span className={c.over_budget ? 'lvl-warn' : ''}>
                              {c.budget_unit === 'tokens' ? c.tokens : c.words}/{c.budget} {c.budget_unit}
                            </span>
                          </summary>
                          <div className="sb-budget">
                            <span
                              style={{
                                width: `${Math.min(100, Math.round(((c.budget_unit === 'tokens' ? c.tokens : c.words) / c.budget) * 100))}%`,
                              }}
                              className={c.over_budget ? 'over' : ''}
                            />
                          </div>
                          <p className="sb-prompt-text">{c.prompt}</p>
                          {c.negative && (
                            <p className="muted tiny">
                              <strong>Avoid:</strong> {c.negative}
                            </p>
                          )}
                          {c.warnings.map((w) => (
                            <div className="fit-warn tiny" key={w}>
                              {w}
                            </div>
                          ))}
                          <div className="inline-actions" style={{ gap: 6 }}>
                            <button
                              className="btn ghost tiny"
                              type="button"
                              onClick={() => {
                                void navigator.clipboard?.writeText(c.prompt)
                                notify('Prompt copied.')
                              }}
                            >
                              Copy
                            </button>
                          </div>
                        </details>
                      )}
                      <div className="sb-actions">
                        <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => openEdit(shot)}>
                          Edit
                        </button>
                        <button className="btn ghost tiny" type="button" disabled={busy || shot.index === 0} onClick={() => moveShot(shot, -1)} aria-label="Move earlier">
                          ←
                        </button>
                        <button
                          className="btn ghost tiny"
                          type="button"
                          disabled={busy || shot.index >= project.shots.length - 1}
                          onClick={() => moveShot(shot, 1)}
                          aria-label="Move later"
                        >
                          →
                        </button>
                        <button className="btn acid tiny" type="button" disabled={busy} onClick={() => onGenerate([shot.id])}>
                          Generate
                        </button>
                        <button
                          className="btn ghost tiny"
                          type="button"
                          disabled={busy || makingKeyframe}
                          title="Make a still with the image model; the video starts from it so the face holds"
                          onClick={() => void makeKeyframe(shot)}
                        >
                          {shot.keyframe_path ? 'New keyframe' : 'Keyframe'}
                        </button>
                        <label className="btn ghost tiny sb-upload" title="Use your own image as this shot's keyframe">
                          Upload
                          <input
                            type="file"
                            accept="image/*,.png,.jpg,.jpeg,.webp"
                            hidden
                            onChange={(e) => {
                              const f = e.target.files?.[0]
                              if (f) void uploadKeyframe(shot, f)
                              e.target.value = ''
                            }}
                          />
                        </label>
                        {shot.keyframe_path && (
                          <button
                            className="btn ghost tiny"
                            type="button"
                            disabled={busy}
                            title="Stop starting this shot from its keyframe"
                            onClick={() =>
                              void run(async () => setProject(await api.patchShot(project.id, shot.id, { keyframe_path: null })))
                            }
                          >
                            × keyframe
                          </button>
                        )}
                        <button
                          className="btn ghost tiny"
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            if (!window.confirm(`Delete card “${shot.title}”? Its takes are removed too.`)) return
                            void run(async () => {
                              setProject(await api.deleteShot(project.id, shot.id))
                              if (editingId === shot.id) setEditingId(null)
                              notify('Card removed.')
                            })
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
