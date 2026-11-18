import { useState } from 'react'
import { api, mediaUrl } from './api'
import type { Project } from './types'

const STAGES: Array<{
  id: 'full' | 'rehearse' | 'promote' | 'finals' | 'stitch'
  label: string
  blurb: string
}> = [
  {
    id: 'full',
    label: 'Run Film night',
    blurb: 'Rehearse if needed → promote winners → finals → captions → stitch',
  },
  { id: 'rehearse', label: '1 · Rehearse', blurb: 'Cheap draft takes for every shot' },
  { id: 'promote', label: '2 · Promote', blurb: 'Pin best rehearsal per shot' },
  { id: 'finals', label: '3 · Finals', blurb: 'Continue-chain generate for the cut' },
  { id: 'stitch', label: '4 · Stitch', blurb: 'Captions + local preview cut' },
]

export default function FilmNightTab({
  project,
  setProject,
  busy,
  setBusy,
  notify,
  onOpenDirector,
  onMakeTest,
  onAddShot,
}: {
  project: Project
  setProject: (p: Project) => void
  busy: boolean
  setBusy: (v: boolean) => void
  notify: (m: string) => void
  onOpenDirector: () => void
  onMakeTest: () => void
  onAddShot: () => void
}) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [steps, setSteps] = useState<string[]>([])

  const run = async (stage: (typeof STAGES)[number]['id']) => {
    if (!project.shots.length && stage !== 'stitch') {
      notify('Plan shots with the Agent first.')
      return
    }
    setBusy(true)
    try {
      const res = await api.filmNight(project.id, stage)
      if (res.project) setProject(res.project)
      else setProject(await api.getProject(project.id))
      setSteps(res.steps || [])
      notify(res.message || 'Done — watch the Generation dock (bottom-right) for job progress.')
      if (res.stitch?.preview_url) setPreviewUrl(res.stitch.preview_url)
      if (stage === 'stitch' || (stage === 'full' && res.stitch)) {
        /* stay here so they can play, or jump */
      }
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const stitchOnly = async () => {
    setBusy(true)
    try {
      const res = await api.stitch(project.id)
      notify(res.message || 'Stitch ready')
      if (res.preview_url) setPreviewUrl(res.preview_url)
      setSteps([res.message])
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <p className="hint">
        Film night cuts a short from shots you already have: draft, pick a winner, finish, then stitch.
        A single test clip starts in Video & image.
      </p>

      {project.shots.length === 0 ? (
        <div className="panel film-night-hero">
          <h3>Nothing to cut yet</h3>
          <p>
            This project has 0 shots and 0 takes, so Rehearse, Finals, and Stitch have nothing to run.
          </p>
          <p className="muted">
            Make a 2 second test first, or add a shot and write what happens in it.
          </p>
          <div className="cta-row">
            <button className="btn acid" type="button" disabled={busy} onClick={onMakeTest}>
              Make a test clip
            </button>
            <button className="btn secondary" type="button" disabled={busy} onClick={onAddShot}>
              Add a first shot
            </button>
          </div>
        </div>
      ) : (
        <div className="panel film-night-hero">
          <h3>Film night</h3>
          <p className="muted">
            {project.shots.length} shots · {project.takes.length} takes ·{' '}
            {project.aspect_ratio || '16:9'} · {project.width || 768}×{project.height || 432}
          </p>
          <div className="cta-row">
            <button className="btn acid" type="button" disabled={busy} onClick={() => run('full')}>
              Run Film night
            </button>
            <button className="btn secondary" type="button" disabled={busy} onClick={onOpenDirector}>
              Open Director
            </button>
            <button className="btn ghost" type="button" disabled={busy} onClick={stitchOnly}>
              Stitch only
            </button>
          </div>
        </div>
      )}

      {project.shots.length > 0 && (
      <div className="mode-grid" style={{ marginTop: 16 }}>
        {STAGES.filter((s) => s.id !== 'full').map((s) => (
          <button
            key={s.id}
            type="button"
            className="mode-chip"
            disabled={busy}
            onClick={() => run(s.id)}
          >
            <strong>{s.label}</strong>
            <span>{s.blurb}</span>
          </button>
        ))}
      </div>
      )}

      {steps.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h3>Last run</h3>
          {steps.map((s) => (
            <div className="muted tiny" key={s}>
              · {s}
            </div>
          ))}
        </div>
      )}

      {previewUrl && (
        <div className="panel" style={{ marginTop: 16 }}>
          <h3>Stitched cut</h3>
          <video
            className="stitch-player"
            src={previewUrl.startsWith('http') || previewUrl.startsWith('/') ? previewUrl : mediaUrl(previewUrl)}
            controls
            playsInline
          />
        </div>
      )}
    </div>
  )
}
