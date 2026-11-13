import { useEffect, useState } from 'react'
import { api } from './api'
import { FRAME_SIZES, framesByOrientation } from './frameSizes'
import type { Health, Settings } from './types'

const STORAGE_KEY = 'studionels_onboarded_v1'

export function shouldShowFirstRun(health: Health | null): boolean {
  if (typeof window === 'undefined') return false
  try {
    if (window.localStorage.getItem(STORAGE_KEY) === '1') {
      // Still show if engine is preview-only so friends get the ROCm path
      return Boolean(health?.will_preview)
    }
  } catch {
    /* ignore */
  }
  return true
}

export function markFirstRunDone() {
  try {
    window.localStorage.setItem(STORAGE_KEY, '1')
  } catch {
    /* ignore */
  }
}

export default function FirstRunWizard({
  health,
  settings,
  setSettings,
  onDone,
  onStartProject,
  notify,
}: {
  health: Health | null
  settings: Settings | null
  setSettings: (s: Settings) => void
  onDone: () => void
  onStartProject: (frameSizeId: string) => void
  notify: (m: string) => void
}) {
  const [step, setStep] = useState(0)
  const [frameId, setFrameId] = useState('16:9-draft')
  const [busy, setBusy] = useState(false)
  const [sampleJob, setSampleJob] = useState<string | null>(null)

  useEffect(() => {
    if (health?.suggested_preset && settings && health.suggested_preset !== settings.preset_id) {
      // preselect suggestion visually only — apply on step 1 confirm
    }
  }, [health, settings])

  const applyPreset = async () => {
    if (!settings || !health?.suggested_preset) return
    setBusy(true)
    try {
      const s = await api.putSettings({ ...settings, preset_id: health.suggested_preset })
      setSettings(s)
      notify(`Preset → ${health.suggested_preset}`)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const runSample = async () => {
    setBusy(true)
    try {
      const frame = FRAME_SIZES.find((f) => f.id === frameId) || FRAME_SIZES[1]
      const job = await api.engineGenerate({
        mode: 't2i',
        prompt: 'cinematic portrait, soft light, StudioNels sample still',
        width: frame.width,
        height: frame.height,
        quality: 'draft',
        cpu_offload: true,
        force_preview: Boolean(health?.will_preview),
      })
      setSampleJob(job.id)
      notify(
        health?.will_preview
          ? `Sample queued as preview · ${job.id}`
          : `Sample queued · ETA may show in Generate`,
      )
      setStep(3)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const finish = (start: boolean) => {
    markFirstRunDone()
    if (start) onStartProject(frameId)
    onDone()
  }

  const ready = Boolean(health?.ready_for_inference)
  const rocm = Boolean(health?.rocm)

  return (
    <div className="modal-backdrop wizard-backdrop" onClick={() => finish(false)}>
      <div className="modal wizard-modal" onClick={(e) => e.stopPropagation()}>
        <div className="section-label">First run · StudioNels</div>
        <h2>
          {step === 0 && 'Is your AMD card ready?'}
          {step === 1 && 'Pick a safe frame size'}
          {step === 2 && 'Try a sample still'}
          {step === 3 && 'You’re set'}
        </h2>

        {step === 0 && (
          <>
            <p>
              <strong>{health?.first_run_headline || health?.device_name || 'Checking…'}</strong>
            </p>
            <p className="muted">
              {health?.first_run_detail ||
                'We’ll detect ROCm / VRAM and point you at a safe preset.'}
            </p>
            <ul className="wizard-list">
              <li>GPU: {health?.device_name || '—'}</li>
              <li>VRAM: {health?.vram_gb != null ? `${health.vram_gb} GB` : 'unknown'}</li>
              <li>ROCm: {rocm ? 'yes' : 'not visible yet'}</li>
              <li>Mode: {ready ? 'real generation' : 'preview until engine install'}</li>
            </ul>
            {!ready && (
              <p className="fit-warn">
                Install AMD ROCm PyTorch + Diffusers for real frames. Until then StudioNels still
                plans, locks characters, and cuts — jobs draw previews.
              </p>
            )}
            {health?.suggested_preset && (
              <button className="btn secondary" type="button" disabled={busy} onClick={applyPreset}>
                Apply suggested preset · {health.suggested_preset}
              </button>
            )}
            <div className="cta-row" style={{ marginTop: 14 }}>
              <button className="btn acid" type="button" onClick={() => setStep(1)}>
                Next · frame size
              </button>
              <button className="btn ghost" type="button" onClick={() => finish(false)}>
                Skip for now
              </button>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <p className="muted">Start draft-sized. You can switch to HD / 9:16 later in Time & Style.</p>
            {(['landscape', 'square', 'portrait'] as const).map((ori) => (
              <div key={ori} style={{ marginBottom: 10 }}>
                <div className="section-label" style={{ textTransform: 'capitalize' }}>
                  {ori}
                </div>
                <div className="mode-grid">
                  {framesByOrientation(ori)
                    .filter((f) => f.id.includes('draft') || f.id === '1:1' || f.id === '9:16' || f.id === '16:9-hd')
                    .map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        className={`mode-chip ${frameId === f.id ? 'active' : ''}`}
                        onClick={() => setFrameId(f.id)}
                      >
                        <strong>{f.ratio}</strong>
                        <span>
                          {f.width}×{f.height}
                        </span>
                      </button>
                    ))}
                </div>
              </div>
            ))}
            <div className="cta-row">
              <button className="btn acid" type="button" onClick={() => setStep(2)}>
                Next · sample
              </button>
              <button className="btn ghost" type="button" onClick={() => setStep(0)}>
                Back
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <p className="muted">
              Queues one draft still so you see whether the engine is preview or real. Safe to skip.
            </p>
            <div className="cta-row">
              <button className="btn acid" type="button" disabled={busy} onClick={runSample}>
                Run sample still
              </button>
              <button className="btn secondary" type="button" onClick={() => setStep(3)}>
                Skip sample
              </button>
              <button className="btn ghost" type="button" onClick={() => setStep(1)}>
                Back
              </button>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <p>
              Main path from here: <strong>Film night</strong> → <strong>Director</strong>. Generate /
              Rehearsal live under Advanced when you need them.
            </p>
            {sampleJob && <p className="muted tiny">Sample job: {sampleJob}</p>}
            <div className="cta-row">
              <button className="btn acid" type="button" onClick={() => finish(true)}>
                Start a project
              </button>
              <button className="btn ghost" type="button" onClick={() => finish(false)}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
