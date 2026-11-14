import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from './api'
import type { EngineModel, GenMode, LoraFile } from './types'

export type AdvTab =
  | 'general'
  | 'loras'
  | 'steps'
  | 'post'
  | 'audio'
  | 'quality'
  | 'sliding'
  | 'misc'
  | 'configs'

export interface WanAdvancedSettings {
  memory_profile: string
  compilation: string
  attention_mode: string
  transformer_quant: string
  text_encoder_quant: string
  skip_cache_type: string
  skip_start_pct: number
  remux_audio: string
  replace_voice: string
  perturbation: string
  perturbation_layers: string
  denoise_start_pct: number
  denoise_end_pct: number
  apg: string
  cfg_star: string
  cfg_zero_layer: number
  self_refiner: string
  uncertainty: number
  certainty_skip: number
  sliding_window_size: number
  window_overlap: number
  color_correction: number
  discard_last_frames: number
  trim_first_frames: number
  riflex: string
  override_fps: string
  output_filename: string
  activated_loras: string
  lora_multipliers: string
  include_media_export: boolean
}

export const DEFAULT_ADV: WanAdvancedSettings = {
  memory_profile: 'default',
  compilation: 'default',
  attention_mode: 'default',
  transformer_quant: 'default',
  text_encoder_quant: 'default',
  skip_cache_type: 'none',
  skip_start_pct: 0,
  remux_audio: 'none',
  replace_voice: 'none',
  perturbation: 'off',
  perturbation_layers: '9',
  denoise_start_pct: 10,
  denoise_end_pct: 90,
  apg: 'off',
  cfg_star: 'off',
  cfg_zero_layer: -1,
  self_refiner: 'disabled',
  uncertainty: 0,
  certainty_skip: 0.999,
  sliding_window_size: 121,
  window_overlap: 1,
  color_correction: 0,
  discard_last_frames: 0,
  trim_first_frames: 0,
  riflex: 'auto',
  override_fps: 'model',
  output_filename: '',
  activated_loras: '',
  lora_multipliers: '',
  include_media_export: false,
}

const ADV_TABS: { id: AdvTab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'loras', label: 'LoRAs' },
  { id: 'steps', label: 'Steps Skipping' },
  { id: 'post', label: 'Post Processing' },
  { id: 'audio', label: 'Audio' },
  { id: 'quality', label: 'Quality' },
  { id: 'sliding', label: 'Sliding Window' },
  { id: 'misc', label: 'Misc.' },
  { id: 'configs', label: 'Configs' },
]

const SETTINGS_KEY = 'studionels_wan_advanced_settings'
const DEFAULTS_KEY = 'studionels_wan_advanced_defaults'

function Box({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="wan-box">
      {hint ? <p className="wan-box-hint">{hint}</p> : null}
      <div className="wan-box-inner">
        <label className="wan-box-label">{label}</label>
        {children}
      </div>
    </div>
  )
}

function SliderRow({
  label,
  hint,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string
  hint?: string
  min: number
  max: number
  step?: number
  value: number
  onChange: (n: number) => void
}) {
  return (
    <div className="wan-box">
      <div className="wan-box-inner">
        <label className="wan-box-label">
          {label}
          {hint ? <span className="muted tiny"> {hint}</span> : null}
        </label>
        <div className="wan-slider-row">
          <input
            type="range"
            min={min}
            max={max}
            step={step ?? 1}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
          />
          <input
            type="number"
            min={min}
            max={max}
            step={step ?? 1}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
          />
        </div>
      </div>
    </div>
  )
}

export function ModelFamilyPicker({
  models,
  modelId,
  mode,
  configId,
  onSelectModel,
  onSelectConfig,
}: {
  models: EngineModel[]
  modelId: string
  mode: string
  configId: string
  onSelectModel: (id: string) => void
  onSelectConfig: (id: string) => void
}) {
  const families = useMemo(() => {
    const map = new Map<string, EngineModel[]>()
    for (const m of models) {
      if (mode && !(m.modes || []).includes(mode as GenMode)) continue
      const fam = m.family || 'Other'
      if (!map.has(fam)) map.set(fam, [])
      map.get(fam)!.push(m)
    }
    const prefer = ['Wan2.2', 'Wan2.1', 'LTX', 'MiniMax', 'Hunyuan', 'Image', 'Audio', 'Upsample', 'Other']
    const keys = [...map.keys()].sort((a, b) => {
      const ia = prefer.indexOf(a)
      const ib = prefer.indexOf(b)
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b)
    })
    return keys.map((k) => ({
      id: k,
      variants: (map.get(k) || []).sort((a, b) =>
        (a.variant || a.label).localeCompare(b.variant || b.label),
      ),
    }))
  }, [models, mode])

  const current = models.find((m) => m.id === modelId)
  const familyId = current?.family || families[0]?.id || 'Wan2.2'
  const family = families.find((f) => f.id === familyId) || families[0]
  const variants = family?.variants || []

  return (
    <div className="wan-family-bar" role="group" aria-label="Model family">
      <div className="wan-family-slot">
        <label className="tiny muted">Family</label>
        <select
          value={familyId}
          onChange={(e) => {
            const next = families.find((f) => f.id === e.target.value)
            const pick = next?.variants[0]
            if (pick) onSelectModel(pick.id)
          }}
        >
          {families.map((f) => (
            <option key={f.id} value={f.id}>
              {f.id}
            </option>
          ))}
        </select>
      </div>
      <div className="wan-family-slot wan-family-slot-wide">
        <label className="tiny muted">Variant</label>
        <select value={modelId} onChange={(e) => onSelectModel(e.target.value)} size={1}>
          {variants.map((m) => {
            const st = m.download_status || (m.installed ? 'installed' : 'not_downloaded')
            const tag =
              st === 'installed'
                ? '●'
                : st === 'downloading'
                  ? '↓'
                  : m.wan2gp_only
                    ? '◇'
                    : '○'
            return (
              <option key={m.id} value={m.id}>
                {tag} {m.variant || m.label}
              </option>
            )
          })}
        </select>
      </div>
      <div className="wan-family-slot">
        <label className="tiny muted">Config</label>
        <select value={configId} onChange={(e) => onSelectConfig(e.target.value)}>
          <option value="default">Default</option>
          <option value="fast">Fast</option>
          <option value="quality">Quality</option>
          <option value="low_vram">Low VRAM</option>
        </select>
      </div>
    </div>
  )
}

export function VariantListBox({
  models,
  modelId,
  familyId,
  mode,
  onSelectModel,
}: {
  models: EngineModel[]
  modelId: string
  familyId: string
  mode: string
  onSelectModel: (id: string) => void
}) {
  const list = models
    .filter((m) => (m.family || 'Other') === familyId)
    .filter((m) => (m.modes || []).includes(mode as EngineModel['modes'][number]))
    .sort((a, b) => (a.variant || a.label).localeCompare(b.variant || b.label))

  return (
    <div className="wan-box wan-variant-list-box">
      <p className="wan-box-hint">
        Models in <strong>{familyId}</strong> — pick a variant (same list style as Wan2GP).
      </p>
      <div className="wan-box-inner">
        <label className="wan-box-label">{familyId} variants</label>
        <div className="wan-variant-list" role="listbox" aria-label={`${familyId} variants`}>
          {list.length === 0 ? (
            <div className="muted tiny">No variants for this mode in {familyId}.</div>
          ) : (
            list.map((m) => {
              const active = m.id === modelId
              const st = m.download_status || (m.installed ? 'installed' : 'not_downloaded')
              return (
                <button
                  key={m.id}
                  type="button"
                  role="option"
                  aria-selected={active}
                  className={`wan-variant-item ${active ? 'active' : ''}`}
                  onClick={() => onSelectModel(m.id)}
                >
                  <span className="wan-radio" data-on={active ? '1' : '0'}>
                    {active ? '✓' : ''}
                  </span>
                  <span className="wan-variant-name">{m.variant || m.label}</span>
                  <span className="muted tiny">
                    {st === 'installed' ? 'ready' : m.wan2gp_only ? 'Wan2GP' : st.replace('_', ' ')}
                  </span>
                </button>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

export function WanAdvancedPanel({
  open,
  onToggle,
  settings,
  onChange,
  loras,
  onRefreshLoras,
  notify,
}: {
  open: boolean
  onToggle: () => void
  settings: WanAdvancedSettings
  onChange: (next: WanAdvancedSettings) => void
  loras: LoraFile[]
  onRefreshLoras: () => Promise<void>
  notify: (m: string) => void
}) {
  const [tab, setTab] = useState<AdvTab>('configs')
  const [loraUrl, setLoraUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const set = <K extends keyof WanAdvancedSettings>(key: K, value: WanAdvancedSettings[K]) =>
    onChange({ ...settings, [key]: value })

  const setAsDefault = () => {
    try {
      window.localStorage.setItem(DEFAULTS_KEY, JSON.stringify(settings))
      window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
      notify('Saved advanced settings as default.')
    } catch {
      notify('Could not save defaults.')
    }
  }

  const resetSettings = () => {
    try {
      const raw = window.localStorage.getItem(DEFAULTS_KEY)
      const next = raw ? ({ ...DEFAULT_ADV, ...JSON.parse(raw) } as WanAdvancedSettings) : { ...DEFAULT_ADV }
      onChange(next)
      notify('Reset advanced settings.')
    } catch {
      onChange({ ...DEFAULT_ADV })
      notify('Reset to built-in defaults.')
    }
  }

  const exportSettings = () => {
    const payload = {
      studionels_advanced: settings,
      exported_at: new Date().toISOString(),
      include_media: settings.include_media_export,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `studionels-settings-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(a.href)
    notify('Exported settings JSON.')
  }

  const importSettingsFile = async (file: File) => {
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const next = {
        ...DEFAULT_ADV,
        ...(data.studionels_advanced || data.advanced || data),
      } as WanAdvancedSettings
      onChange(next)
      notify(`Loaded settings from ${file.name}`)
    } catch (err) {
      notify(String((err as Error).message || err))
    }
  }

  const downloadLoraUrl = async () => {
    if (!loraUrl.trim()) {
      notify('Paste a Hugging Face LoRA URL or owner/repo first.')
      return
    }
    setBusy(true)
    try {
      const r = await api.engineLorasDownloadUrl(loraUrl.trim())
      notify(`LoRA download started: ${r.hf_id}`)
      await onRefreshLoras()
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wan-advanced">
      <label className="wan-advanced-toggle">
        <input type="checkbox" checked={open} onChange={onToggle} />
        <strong>Advanced Mode</strong>
        <span className="muted tiny">Wan2GP-style tabs — LoRAs, quality, sliding window, configs…</span>
      </label>

      {open ? (
        <>
          <div className="wan-adv-tabs" role="tablist">
            {ADV_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`wan-adv-tab ${tab === t.id ? 'active' : ''}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="wan-adv-body">
            {tab === 'general' && (
              <>
                <p className="muted tiny">Core overrides for this run. Memory + attention live under Configs too.</p>
                <Box label="Override Memory Profile" hint="More aggressive profiles help short videos / images.">
                  <select
                    value={settings.memory_profile}
                    onChange={(e) => set('memory_profile', e.target.value)}
                  >
                    <option value="default">Default (global profile)</option>
                    <option value="vram-4">Profile LowRAM</option>
                    <option value="vram-12">Profile Mid VRAM</option>
                    <option value="vram-16">Profile High VRAM</option>
                    <option value="vram-24">Profile Max VRAM (GPU-resident)</option>
                  </select>
                </Box>
                <Box label="Override Attention Mode" hint="Change attention for quality / compatibility.">
                  <select
                    value={settings.attention_mode}
                    onChange={(e) => set('attention_mode', e.target.value)}
                  >
                    <option value="default">Default Attention Mode</option>
                    <option value="sdpa">SDPA</option>
                    <option value="eager">Eager</option>
                    <option value="sage">Sage (if installed)</option>
                  </select>
                </Box>
              </>
            )}

            {tab === 'loras' && (
              <>
                <p className="muted tiny">
                  LoRAs create special effects when you mention a trigger word in the prompt. Save
                  combinations as multipliers below.
                </p>
                <Box label="Activated LoRAs">
                  <textarea
                    rows={3}
                    value={settings.activated_loras}
                    onChange={(e) => set('activated_loras', e.target.value)}
                    placeholder="Comma-separated LoRA names or paths (optional notes)"
                  />
                </Box>
                <Box label="LoRA Multipliers">
                  <textarea
                    rows={2}
                    value={settings.lora_multipliers}
                    onChange={(e) => set('lora_multipliers', e.target.value)}
                    placeholder="e.g. 0.8,1.0  or  name=0.8"
                  />
                </Box>
                {loras.length > 0 ? (
                  <div className="muted tiny" style={{ marginTop: 6 }}>
                    {loras.length} LoRA file(s) available in Generate dropdown.
                  </div>
                ) : null}
              </>
            )}

            {tab === 'steps' && (
              <>
                <p className="muted tiny">
                  Step-skipping accelerators avoid selected full transformer evaluations. More skipped
                  evaluations may reduce output quality.
                </p>
                <p className="muted tiny">Keep an initial warmup so the accelerator can establish a stable history.</p>
                <Box label="Skip Steps Cache Type">
                  <select
                    value={settings.skip_cache_type}
                    onChange={(e) => set('skip_cache_type', e.target.value)}
                  >
                    <option value="none">None</option>
                    <option value="tea">TeaCache</option>
                    <option value="mag">MagCache</option>
                    <option value="fb">FB Cache</option>
                  </select>
                </Box>
                <SliderRow
                  label="Skip Steps starting moment in % of generation"
                  min={0}
                  max={100}
                  value={settings.skip_start_pct}
                  onChange={(n) => set('skip_start_pct', n)}
                />
              </>
            )}

            {tab === 'post' && (
              <>
                <Box label="Postprocess Remux Audio">
                  <select value={settings.remux_audio} onChange={(e) => set('remux_audio', e.target.value)}>
                    <option value="none">None</option>
                    <option value="keep">Keep original audio bed</option>
                    <option value="replace">Replace with attached audio</option>
                  </select>
                </Box>
                <Box label="Replace Voice">
                  <select
                    value={settings.replace_voice}
                    onChange={(e) => set('replace_voice', e.target.value)}
                  >
                    <option value="none">None</option>
                    <option value="clone">Voice clone (when available)</option>
                  </select>
                </Box>
              </>
            )}

            {tab === 'audio' && (
              <p className="muted tiny">
                Attach an audio bed in the main Generate form. Remux / replace voice options are under
                Post Processing.
              </p>
            )}

            {tab === 'quality' && (
              <>
                <Box
                  label="Perturbation"
                  hint="Improves video quality (requires guidance > 1)."
                >
                  <select
                    value={settings.perturbation}
                    onChange={(e) => set('perturbation', e.target.value)}
                  >
                    <option value="off">OFF</option>
                    <option value="on">ON</option>
                  </select>
                </Box>
                <Box label="Perturbation Layers">
                  <input
                    value={settings.perturbation_layers}
                    onChange={(e) => set('perturbation_layers', e.target.value)}
                  />
                </Box>
                <div className="wan-two-col">
                  <SliderRow
                    label="Denoising Steps % start"
                    min={0}
                    max={100}
                    value={settings.denoise_start_pct}
                    onChange={(n) => set('denoise_start_pct', n)}
                  />
                  <SliderRow
                    label="Denoising Steps % end"
                    min={0}
                    max={100}
                    value={settings.denoise_end_pct}
                    onChange={(n) => set('denoise_end_pct', n)}
                  />
                </div>
                <Box
                  label="Adaptive Projected Guidance"
                  hint="Correct progressive color saturation on long videos (guidance > 1)."
                >
                  <select value={settings.apg} onChange={(e) => set('apg', e.target.value)}>
                    <option value="off">OFF</option>
                    <option value="on">ON</option>
                  </select>
                </Box>
                <Box
                  label="Classifier-Free Guidance Star"
                  hint="Better text-prompt adherence (guidance > 1)."
                >
                  <select value={settings.cfg_star} onChange={(e) => set('cfg_star', e.target.value)}>
                    <option value="off">OFF</option>
                    <option value="on">ON</option>
                  </select>
                </Box>
                <SliderRow
                  label="CFG Zero below this Layer"
                  hint="(Extra process)"
                  min={-1}
                  max={39}
                  value={settings.cfg_zero_layer}
                  onChange={(n) => set('cfg_zero_layer', n)}
                />
                <Box label="Self Refiner" hint="Self-refining video sampling (PnP) for motion quality.">
                  <select
                    value={settings.self_refiner}
                    onChange={(e) => set('self_refiner', e.target.value)}
                  >
                    <option value="disabled">Disabled</option>
                    <option value="enabled">Enabled</option>
                  </select>
                </Box>
                <div className="wan-two-col">
                  <SliderRow
                    label="Uncertainty Threshold"
                    min={0}
                    max={1}
                    step={0.01}
                    value={settings.uncertainty}
                    onChange={(n) => set('uncertainty', n)}
                  />
                  <SliderRow
                    label="Certainty Percentage Skip"
                    min={0}
                    max={1}
                    step={0.001}
                    value={settings.certainty_skip}
                    onChange={(n) => set('certainty_skip', n)}
                  />
                </div>
              </>
            )}

            {tab === 'sliding' && (
              <>
                <p className="muted tiny">
                  A Sliding Window lets you generate video longer than the model’s native window. It
                  turns on automatically when frames exceed Window Size.
                </p>
                <SliderRow
                  label="Sliding Window Size"
                  min={5}
                  max={257}
                  value={settings.sliding_window_size}
                  onChange={(n) => set('sliding_window_size', n)}
                />
                <SliderRow
                  label="Windows Frames Overlap"
                  hint="(continuity between windows)"
                  min={1}
                  max={64}
                  value={settings.window_overlap}
                  onChange={(n) => set('window_overlap', n)}
                />
                <SliderRow
                  label="Color Correction Strength"
                  hint="(0 = disabled)"
                  min={0}
                  max={1}
                  step={0.01}
                  value={settings.color_correction}
                  onChange={(n) => set('color_correction', n)}
                />
                <SliderRow
                  label="Discard Last Frames of a Window"
                  hint="(may have bad quality)"
                  min={0}
                  max={20}
                  value={settings.discard_last_frames}
                  onChange={(n) => set('discard_last_frames', n)}
                />
                <SliderRow
                  label="Trim First Frames in First Window"
                  min={0}
                  max={10}
                  value={settings.trim_first_frames}
                  onChange={(n) => set('trim_first_frames', n)}
                />
              </>
            )}

            {tab === 'misc' && (
              <>
                <Box
                  label="RIFLEx positional embedding to generate long video"
                  hint="Generate videos longer than the ~5s default training length."
                >
                  <select value={settings.riflex} onChange={(e) => set('riflex', e.target.value)}>
                    <option value="auto">Auto (ON if Video longer than 5s)</option>
                    <option value="on">ON</option>
                    <option value="off">OFF</option>
                  </select>
                </Box>
                <Box label="Override Frames Per Second (model default)">
                  <select
                    value={settings.override_fps}
                    onChange={(e) => set('override_fps', e.target.value)}
                  >
                    <option value="model">Model Default</option>
                    <option value="8">8 fps</option>
                    <option value="12">12 fps</option>
                    <option value="16">16 fps</option>
                    <option value="24">24 fps</option>
                    <option value="30">30 fps</option>
                  </select>
                </Box>
                <Box
                  label="Output Filename (Leave Blank for Auto Naming)"
                  hint="Tokens: {date} {seed} {prompt} {num_inference_steps} {video_length} {guidance_scale}"
                >
                  <input
                    value={settings.output_filename}
                    onChange={(e) => set('output_filename', e.target.value)}
                    placeholder="{date}_{seed}_{prompt(40)}"
                  />
                </Box>
              </>
            )}

            {tab === 'configs' && (
              <>
                <Box
                  label="Override Memory Profile"
                  hint="You can set a more aggressive Memory Profile if you generate only Short Videos or Images."
                >
                  <select
                    value={settings.memory_profile}
                    onChange={(e) => set('memory_profile', e.target.value)}
                  >
                    <option value="default">Default (global profile)</option>
                    <option value="vram-4">
                      Profile 1, LowRAM — stream layers, keep footprint small
                    </option>
                    <option value="vram-12">
                      Profile 2, Balanced — partial GPU residency
                    </option>
                    <option value="vram-16">
                      Profile 3, LowRAM_HighVRAM — main models in reserved RAM; layers fill VRAM
                    </option>
                    <option value="vram-24">
                      Profile 4, Max VRAM — GPU-resident when it fits (R9700)
                    </option>
                  </select>
                </Box>
                <Box
                  label="Override Compilation"
                  hint="Override Transformer Compilation for this generation. Default uses the current Config choice."
                >
                  <select
                    value={settings.compilation}
                    onChange={(e) => set('compilation', e.target.value)}
                  >
                    <option value="default">Default</option>
                    <option value="none">None</option>
                    <option value="dynamo">torch.compile</option>
                  </select>
                </Box>
                <Box
                  label="Override Attention Mode"
                  hint="You can set a different Attention Mode to improve quality / compatibility."
                >
                  <select
                    value={settings.attention_mode}
                    onChange={(e) => set('attention_mode', e.target.value)}
                  >
                    <option value="default">Default Attention Mode</option>
                    <option value="sdpa">SDPA</option>
                    <option value="eager">Eager</option>
                    <option value="sage">Sage</option>
                  </select>
                </Box>
                <div className="wan-two-col">
                  <Box
                    label="Override Transformer Quantization"
                    hint="Other quantized weights for this generation when available."
                  >
                    <select
                      value={settings.transformer_quant}
                      onChange={(e) => set('transformer_quant', e.target.value)}
                    >
                      <option value="default">Default Transformer Quantization</option>
                      <option value="bf16">BF16</option>
                      <option value="fp8">FP8</option>
                      <option value="int8">INT8</option>
                      <option value="nvfp4">NVFP4</option>
                    </select>
                  </Box>
                  <Box label="Override Text Encoder Quantization">
                    <select
                      value={settings.text_encoder_quant}
                      onChange={(e) => set('text_encoder_quant', e.target.value)}
                    >
                      <option value="default">Default Text Encoder Quantization</option>
                      <option value="bf16">BF16</option>
                      <option value="fp8">FP8</option>
                      <option value="int8">INT8</option>
                    </select>
                  </Box>
                </div>
              </>
            )}
          </div>

          <div className="wan-settings-actions">
            <button type="button" className="btn acid tiny" onClick={setAsDefault}>
              Set Settings as Default
            </button>
            <button type="button" className="btn ghost tiny" onClick={resetSettings}>
              Reset Settings
            </button>
            <button type="button" className="btn ghost tiny" onClick={exportSettings}>
              Export Settings to File
            </button>
            <label className="wan-include-media">
              <input
                type="checkbox"
                checked={settings.include_media_export}
                onChange={(e) => set('include_media_export', e.target.checked)}
              />
              Include Media
            </label>
          </div>

          <div className="wan-load-settings">
            <div>
              <strong>Load Settings From Media File / Json / Zip</strong>
              <div className="muted tiny">Import a previously exported StudioNels / Wan2GP-style JSON.</div>
            </div>
            <button type="button" className="btn ghost tiny" onClick={() => fileRef.current?.click()}>
              Click to upload or drop files
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".json,.zip,.mp4,.webm,.png,.jpg"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) void importSettingsFile(f)
                e.target.value = ''
              }}
            />
          </div>

          <div className="wan-lora-url-row">
            <input
              type="text"
              value={loraUrl}
              onChange={(e) => setLoraUrl(e.target.value)}
              placeholder="Enter Lora URL"
              aria-label="LoRA URL"
            />
            <button type="button" className="btn acid tiny" disabled={busy} onClick={downloadLoraUrl}>
              {busy ? '…' : 'Download'}
            </button>
          </div>
        </>
      ) : null}
    </div>
  )
}

export function loadStoredAdvanced(): WanAdvancedSettings {
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY) || window.localStorage.getItem(DEFAULTS_KEY)
    if (!raw) return { ...DEFAULT_ADV }
    return { ...DEFAULT_ADV, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULT_ADV }
  }
}

export function persistAdvanced(settings: WanAdvancedSettings) {
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    /* ignore */
  }
}

export function useAdvancedSettings() {
  const [settings, setSettings] = useState<WanAdvancedSettings>(() =>
    typeof window !== 'undefined' ? loadStoredAdvanced() : { ...DEFAULT_ADV },
  )
  useEffect(() => {
    persistAdvanced(settings)
  }, [settings])
  return [settings, setSettings] as const
}
