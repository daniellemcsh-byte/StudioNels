import { useEffect, useMemo, useRef, useState } from 'react'
import { api, mediaUrl } from './api'
import {
  CAPTION_STYLES,
  DIRECTOR_FILTERS,
  TRANSITIONS,
  filterCss,
  formatTimecode,
} from './directorCatalog'
import type { AudioClip, EngineJob, Project, TimelineClip } from './types'

function clipDuration(clip: TimelineClip, shotDur: number): number {
  const tin = clip.trim_in ?? clip.start_sec ?? 0
  const tout = clip.trim_out ?? clip.end_sec ?? shotDur ?? 3
  const raw = Math.max(0.05, Number(tout) - Number(tin))
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
    caption_x: c.caption_x ?? 0,
    caption_y: c.caption_y ?? 0,
    caption_start: c.caption_start ?? 0,
    caption_end: c.caption_end ?? null,
    filter_id: c.filter_id || 'none',
    filter_intensity: c.filter_intensity ?? 1,
    director_note: c.director_note ?? '',
    scale: c.scale ?? 1,
    pan_x: c.pan_x ?? 0,
    pan_y: c.pan_y ?? 0,
    volume: c.volume ?? 1,
    fade_in: c.fade_in ?? 0,
    fade_out: c.fade_out ?? 0,
    transition: c.transition || 'none',
    transition_dur: c.transition_dur ?? 0.35,
  }
}

type Sel =
  | { kind: 'video'; id: string }
  | { kind: 'audio'; id: string }
  | { kind: 'caption'; id: string }
  | null

export default function DirectorStudio({
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
  const [sel, setSel] = useState<Sel>(null)
  const [playhead, setPlayhead] = useState(0)
  const [zoom, setZoom] = useState(48) // px per second
  const [snap, setSnap] = useState(true)
  const [audioJobs, setAudioJobs] = useState<EngineJob[]>([])
  const [editingCaption, setEditingCaption] = useState(false)
  const [captionDraft, setCaptionDraft] = useState('')
  const [dragCaption, setDragCaption] = useState(false)
  const trackRef = useRef<HTMLDivElement>(null)
  const viewerRef = useRef<HTMLDivElement>(null)
  const captionInputRef = useRef<HTMLTextAreaElement>(null)

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
        scale: 1,
        pan_x: 0,
        pan_y: 0,
        volume: 1,
        fade_in: 0,
        fade_out: 0,
      }))
  }, [project])

  const audioClips = useMemo(
    () => [...(project.audio_timeline || [])].sort((a, b) => a.order - b.order || a.timeline_start - b.timeline_start),
    [project.audio_timeline],
  )

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

  const totalSec = Math.max(
    layout.length ? layout[layout.length - 1].end : 0,
    ...audioClips.map((a) => a.timeline_start + a.duration_sec),
    project.target_duration_sec || 0,
    1,
  )

  const selectedVideo =
    sel?.kind === 'video' || sel?.kind === 'caption'
      ? clips.find((c) => c.id === sel.id) || null
      : clips.find((c) => {
          const seg = layout.find((s) => s.clip.id === c.id)
          return seg && playhead >= seg.start && playhead < seg.end
        }) ||
        clips[0] ||
        null

  const selectedAudio =
    sel?.kind === 'audio' ? audioClips.find((c) => c.id === sel.id) || null : null

  const selectedSeg = layout.find((s) => s.clip.id === selectedVideo?.id)
  const selectedTake = selectedVideo
    ? project.takes.find((t) => t.id === selectedVideo.take_id)
    : undefined

  const px = (sec: number) => sec * zoom
  const fineStep = zoom >= 80 ? 0.05 : zoom >= 40 ? 0.1 : 0.25

  useEffect(() => {
    const load = () =>
      api
        .engineJobs()
        .then((list) =>
          setAudioJobs(list.filter((j) => j.mode === 't2a' && j.status === 'done' && !!j.media_path)),
        )
        .catch(() => undefined)
    load()
    const t = window.setInterval(load, 4000)
    return () => window.clearInterval(t)
  }, [project.id])

  const persistVideo = async (next: TimelineClip[], msg?: string) => {
    setBusy(true)
    try {
      const payload = next.map((c, order) => {
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

  const persistAudio = async (next: AudioClip[], msg?: string) => {
    setBusy(true)
    try {
      const payload = next.map((c, order) => ({ ...c, order }))
      const p = await api.setAudioTimeline(project.id, payload)
      setProject(p)
      if (msg) notify(msg)
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const patchVideo = async (patch: Partial<TimelineClip>) => {
    if (!selectedVideo) return
    await persistVideo(clips.map((c) => (c.id === selectedVideo.id ? { ...c, ...patch } : c)))
  }

  const patchAudio = async (patch: Partial<AudioClip>) => {
    if (!selectedAudio) return
    await persistAudio(audioClips.map((c) => (c.id === selectedAudio.id ? { ...c, ...patch } : c)))
  }

  useEffect(() => {
    if (selectedVideo) {
      setCaptionDraft(selectedVideo.caption || '')
    }
  }, [selectedVideo?.id, selectedVideo?.caption])

  const startCaptionEdit = (seed?: string) => {
    if (!selectedVideo) {
      notify('Select a video clip first.')
      return
    }
    setSel({ kind: 'caption', id: selectedVideo.id })
    setCaptionDraft(seed ?? selectedVideo.caption ?? '')
    setEditingCaption(true)
    window.setTimeout(() => captionInputRef.current?.focus(), 50)
  }

  const saveCaption = async () => {
    if (!selectedVideo) return
    const text = captionDraft.trim()
    await patchVideo({
      caption: text,
      caption_style: selectedVideo.caption_style || 'bottom',
    })
    setEditingCaption(false)
    setSel({ kind: 'video', id: selectedVideo.id })
    notify(text ? 'Caption saved on clip.' : 'Caption cleared.')
  }

  const addCaptionAtPlayhead = async () => {
    if (!selectedVideo || !selectedSeg) {
      notify('Build the video track and select a clip first.')
      return
    }
    const local = Math.max(0, playhead - selectedSeg.start)
    await persistVideo(
      clips.map((c) =>
        c.id === selectedVideo.id
          ? {
              ...c,
              caption: c.caption || 'New caption',
              caption_start: Number(local.toFixed(2)),
              caption_style: c.caption_style || 'free',
            }
          : c,
      ),
      'Caption added — edit it on the video.',
    )
    setSel({ kind: 'caption', id: selectedVideo.id })
    setCaptionDraft(selectedVideo.caption || 'New caption')
    setEditingCaption(true)
  }

  const onCaptionPointerDown = (e: { clientX: number; clientY: number; preventDefault: () => void }) => {
    if (!selectedVideo || !viewerRef.current) return
    e.preventDefault()
    setDragCaption(true)
    setSel({ kind: 'caption', id: selectedVideo.id })
    const rect = viewerRef.current.getBoundingClientRect()
    const move = (ev: PointerEvent) => {
      const nx = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      const ny = ((ev.clientY - rect.top) / rect.height) * 2 - 1
      setCaptionDraft((d) => d) // keep draft
      // live preview via direct patch would thrash — stash on element dataset
      viewerRef.current?.style.setProperty('--cap-x', String(Math.max(-1, Math.min(1, nx))))
      viewerRef.current?.style.setProperty('--cap-y', String(Math.max(-1, Math.min(1, ny))))
    }
    const up = async (ev: PointerEvent) => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      setDragCaption(false)
      const nx = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      const ny = ((ev.clientY - rect.top) / rect.height) * 2 - 1
      await patchVideo({
        caption_x: Number(Math.max(-1, Math.min(1, nx)).toFixed(3)),
        caption_y: Number(Math.max(-1, Math.min(1, ny)).toFixed(3)),
        caption_style: 'free',
      })
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const applyTransition = async (transition: string) => {
    if (!selectedVideo) {
      notify('Select the clip that comes AFTER the cut.')
      return
    }
    await patchVideo({
      transition,
      transition_dur: selectedVideo.transition_dur ?? 0.35,
    })
    notify(
      transition === 'none'
        ? 'Hard cut.'
        : `Transition “${transition}” into this clip (${selectedVideo.transition_dur ?? 0.35}s).`,
    )
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
            scale: 1,
            pan_x: 0,
            pan_y: 0,
            volume: 1,
          },
          order,
          s.duration_sec,
        ),
      )
    await persistVideo(built, 'Video track built from pins.')
  }

  const splitAtPlayhead = async () => {
    if (!selectedVideo || !selectedSeg) return
    const local = playhead - selectedSeg.start
    if (local < 0.08 || local > selectedSeg.dur - 0.08) {
      notify('Move playhead inside the clip for a fine cut.')
      return
    }
    const tin = selectedVideo.trim_in ?? 0
    const speed = selectedVideo.speed && selectedVideo.speed > 0 ? selectedVideo.speed : 1
    const cutSrc = tin + local * speed
    const a: TimelineClip = {
      ...selectedVideo,
      id: `${selectedVideo.id}_a`,
      trim_out: cutSrc,
      end_sec: cutSrc,
    }
    const b: TimelineClip = {
      ...selectedVideo,
      id: `clip_${selectedVideo.shot_id}_${Date.now().toString(36)}`,
      trim_in: cutSrc,
      start_sec: cutSrc,
    }
    const idx = clips.findIndex((c) => c.id === selectedVideo.id)
    const next = [...clips.slice(0, idx), a, b, ...clips.slice(idx + 1)]
    setSel({ kind: 'video', id: b.id })
    await persistVideo(next, `Split at ${formatTimecode(playhead)}.`)
  }

  const nudgeTrim = async (edge: 'in' | 'out', dir: -1 | 1) => {
    if (!selectedVideo) return
    const step = fineStep * dir
    if (edge === 'in') {
      const v = Math.max(0, (selectedVideo.trim_in ?? 0) + step)
      await patchVideo({ trim_in: Number(v.toFixed(3)), start_sec: Number(v.toFixed(3)) })
    } else {
      const cur = selectedVideo.trim_out ?? selectedVideo.end_sec ?? 3
      const v = Math.max((selectedVideo.trim_in ?? 0) + 0.05, cur + step)
      await patchVideo({ trim_out: Number(v.toFixed(3)), end_sec: Number(v.toFixed(3)) })
    }
  }

  const addAudioFromJob = async (job: EngineJob) => {
    const clip: Partial<AudioClip> = {
      label: job.prompt?.slice(0, 40) || job.model_label || 'Audio',
      kind: 'music',
      media_path: job.media_path,
      timeline_start: snap ? Math.round(playhead * 10) / 10 : playhead,
      duration_sec: 8,
      volume: 0.8,
      fade_out: 0.5,
      track: 0,
    }
    setBusy(true)
    try {
      const p = await api.addAudioClip(project.id, clip)
      setProject(p)
      const last = p.audio_timeline?.[p.audio_timeline.length - 1]
      if (last) setSel({ kind: 'audio', id: last.id })
      notify('Audio bed added under the video.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const addUploadedAudio = async (file: File) => {
    setBusy(true)
    try {
      const up = await api.engineUpload(file)
      const p = await api.addAudioClip(project.id, {
        label: file.name,
        kind: 'other',
        media_path: up.path,
        timeline_start: playhead,
        duration_sec: 8,
        volume: 0.85,
        track: 1,
      })
      setProject(p)
      notify('Uploaded audio on track 2.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const addUploadedVideo = async (file: File) => {
    setBusy(true)
    try {
      // Insert after the clip under the playhead when possible
      let insertAt = clips.length
      const hit = layout.find((s) => playhead >= s.start && playhead < s.end)
      if (hit) {
        const idx = clips.findIndex((c) => c.id === hit.clip.id)
        if (idx >= 0) insertAt = idx + 1
      }
      const res = await api.importDirectorVideo(project.id, file, {
        title: file.name.replace(/\.[^.]+$/, ''),
        insert_at: insertAt,
      })
      setProject(res.project)
      setSel({ kind: 'video', id: res.clip_id })
      notify(res.message || 'Clip added to the timeline.')
    } catch (err) {
      notify(String((err as Error).message || err))
    } finally {
      setBusy(false)
    }
  }

  const onTrackClick = (e: { clientX: number; currentTarget: HTMLDivElement }) => {
    const el = trackRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const x = e.clientX - rect.left + el.scrollLeft
    let t = x / zoom
    if (snap) t = Math.round(t / fineStep) * fineStep
    t = Math.max(0, Math.min(totalSec, t))
    setPlayhead(t)
    const hit = layout.find((s) => t >= s.start && t < s.end)
    if (hit) setSel({ kind: 'video', id: hit.clip.id })
  }

  const ticks: number[] = []
  const tickEvery = zoom >= 80 ? 0.5 : zoom >= 40 ? 1 : zoom >= 20 ? 2 : 5
  for (let t = 0; t <= totalSec + 0.01; t += tickEvery) ticks.push(Number(t.toFixed(2)))

  const scale = selectedVideo?.scale ?? 1
  const panX = selectedVideo?.pan_x ?? 0
  const panY = selectedVideo?.pan_y ?? 0

  return (
    <div className="director tiktok-director">
      <p className="hint">
        TikTok-style edit bay — upload clips you already have, or build from pinned takes. Captions,
        transitions, audio under, zoom for fine cuts.
      </p>

      <div className="director-toolbar inline-actions" style={{ flexWrap: 'wrap' }}>
        <label className={`btn acid ${busy ? 'disabled' : ''}`} style={{ cursor: busy ? 'wait' : 'pointer' }}>
          Upload video
          <input
            type="file"
            accept="video/*,.mp4,.webm,.mov,.mkv,.m4v,.gif"
            hidden
            disabled={busy}
            onChange={(e) => {
              const f = e.target.files?.[0]
              e.target.value = ''
              if (f) addUploadedVideo(f)
            }}
          />
        </label>
        <button className="btn secondary" type="button" disabled={busy} onClick={buildFromPins}>
          Build video from pins
        </button>
        <button
          className="btn secondary"
          type="button"
          disabled={busy || !selectedVideo}
          onClick={splitAtPlayhead}
        >
          Split at playhead
        </button>
        <button
          className="btn secondary"
          type="button"
          disabled={busy || !selectedVideo}
          onClick={() => addCaptionAtPlayhead()}
        >
          Add caption
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy || !selectedVideo}
          onClick={() => startCaptionEdit()}
        >
          Edit on video
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const p = await api.generateCaptions(project.id, false)
              setProject(p)
              notify('Captions generated from dialogue — tap Edit on video to tweak.')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Auto captions
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={() => window.open(api.captionsSrtUrl(project.id), '_blank')}
        >
          .srt
        </button>
        <button
          className="btn secondary"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const res = await api.stitch(project.id)
              notify(res.message || 'Stitch ready')
              if (res.preview_url) window.open(res.preview_url, '_blank')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Stitch cut
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const res = await api.filmNight(project.id, 'full')
              if (res.project) setProject(res.project)
              notify(res.message || 'Film night')
              if (res.stitch?.preview_url) window.open(res.stitch.preview_url, '_blank')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Film night
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy || !project.shots.length}
          title="Continue-chain generate from the cut"
          onClick={async () => {
            setBusy(true)
            try {
              const res = await api.filmNight(project.id, 'finals')
              if (res.project) setProject(res.project)
              notify(res.message || 'Finals queued')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Continue all shots
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const pack = await api.exportPack(project.id)
              notify(pack.message || 'Look-bible pack ready')
              window.open(pack.download_url, '_blank')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Pack
        </button>
        <button
          className="btn ghost"
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              const pack = await api.exportNle(project.id)
              notify(`Exported · ${pack.clip_count} clips`)
              window.open(pack.download_url, '_blank')
            } catch (err) {
              notify(String((err as Error).message || err))
            } finally {
              setBusy(false)
            }
          }}
        >
          Export NLE
        </button>
        <label className="muted tiny" style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} />
          Snap {fineStep}s
        </label>
      </div>

      <div className="tt-stage gen-layout">
        <div className="panel tt-preview-wrap">
          <div
            className="director-viewer tt-phone"
            ref={viewerRef}
            style={{
              filter: filterCss(selectedVideo?.filter_id, selectedVideo?.filter_intensity ?? 1),
              ['--cap-x' as string]: String(selectedVideo?.caption_x ?? 0),
              ['--cap-y' as string]: String(selectedVideo?.caption_y ?? 0),
              ...(selectedVideo?.transition && selectedVideo.transition !== 'none'
                ? {
                    // subtle preview of outgoing transition at clip end
                    ...(playhead > (selectedSeg?.end || 0) - (selectedVideo.transition_dur || 0.35)
                      ? {
                          // applied via child overlay
                        }
                      : {}),
                  }
                : {}),
            }}
          >
            <div
              className="tt-frame"
              style={{
                transform: `scale(${scale}) translate(${panX * 12}%, ${panY * 12}%)`,
              }}
            >
              {mediaUrl(selectedTake?.thumb_path || selectedTake?.media_path) ? (
                <img
                  src={mediaUrl(selectedTake?.thumb_path || selectedTake?.media_path)}
                  alt=""
                />
              ) : (
                <div className="empty">Pin takes & build the video track</div>
              )}
            </div>
            {selectedVideo &&
              selectedSeg &&
              selectedVideo.transition &&
              selectedVideo.transition !== 'none' &&
              playhead >= selectedSeg.start &&
              playhead < selectedSeg.start + (selectedVideo.transition_dur || 0.35) && (
                <div
                  className={`tt-transition-fx fx-${selectedVideo.transition}`}
                  style={{
                    opacity:
                      1 -
                      (playhead - selectedSeg.start) / (selectedVideo.transition_dur || 0.35),
                  }}
                  aria-hidden
                />
              )}
            {(editingCaption || (selectedVideo?.caption && project.captions_enabled !== false)) && (
              <div
                className={`caption-overlay editable style-${selectedVideo?.caption_style || 'bottom'} ${dragCaption ? 'dragging' : ''} ${editingCaption || sel?.kind === 'caption' ? 'active-edit' : ''}`}
                style={
                  selectedVideo?.caption_style === 'free'
                    ? {
                        left: `${50 + (selectedVideo.caption_x || 0) * 42}%`,
                        top: `${50 + (selectedVideo.caption_y || 0) * 42}%`,
                        bottom: 'auto',
                        transform: 'translate(-50%, -50%)',
                      }
                    : undefined
                }
                onPointerDown={onCaptionPointerDown}
                title="Drag to reposition · click Edit on video to type"
              >
                {editingCaption ? (
                  <textarea
                    ref={captionInputRef}
                    className="caption-inline-input"
                    rows={2}
                    value={captionDraft}
                    onChange={(e) => setCaptionDraft(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onPointerDown={(e) => e.stopPropagation()}
                    onBlur={() => saveCaption()}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        saveCaption()
                      }
                      if (e.key === 'Escape') {
                        setEditingCaption(false)
                        setCaptionDraft(selectedVideo?.caption || '')
                      }
                    }}
                    placeholder="Type caption…"
                  />
                ) : (
                  <button
                    type="button"
                    className="caption-tap"
                    onClick={(e) => {
                      e.stopPropagation()
                      startCaptionEdit(selectedVideo?.caption || '')
                    }}
                  >
                    {selectedVideo?.caption || 'Tap to add caption'}
                  </button>
                )}
              </div>
            )}
            <div className="tt-timechip">{formatTimecode(playhead)}</div>
            {selectedVideo?.transition && selectedVideo.transition !== 'none' && (
              <div className="tt-trans-chip">
                {selectedVideo.transition} {selectedVideo.transition_dur ?? 0.35}s
              </div>
            )}
          </div>
          {editingCaption && (
            <div className="inline-actions" style={{ marginTop: 8, justifyContent: 'center' }}>
              <button className="btn acid tiny" type="button" disabled={busy} onClick={saveCaption}>
                Save caption
              </button>
              <button
                className="btn ghost tiny"
                type="button"
                onClick={() => {
                  setEditingCaption(false)
                  setCaptionDraft(selectedVideo?.caption || '')
                }}
              >
                Cancel
              </button>
            </div>
          )}
          {selectedAudio?.media_path && mediaUrl(selectedAudio.media_path) && (
            <audio
              key={selectedAudio.id}
              controls
              src={mediaUrl(selectedAudio.media_path)}
              style={{ width: '100%', marginTop: 10 }}
            />
          )}
        </div>

        <div className="panel">
          <h3>{selectedAudio ? 'Audio clip' : 'Video clip'}</h3>
          {selectedAudio ? (
            <>
              <div className="field">
                <label>Label</label>
                <input
                  value={selectedAudio.label}
                  onChange={(e) => patchAudio({ label: e.target.value })}
                />
              </div>
              <div className="controls-grid">
                <div className="field">
                  <label>Start on timeline</label>
                  <input
                    type="number"
                    min={0}
                    step={fineStep}
                    value={selectedAudio.timeline_start}
                    onChange={(e) => patchAudio({ timeline_start: Number(e.target.value) })}
                  />
                </div>
                <div className="field">
                  <label>Length (sec)</label>
                  <input
                    type="number"
                    min={0.2}
                    step={fineStep}
                    value={selectedAudio.duration_sec}
                    onChange={(e) => patchAudio({ duration_sec: Number(e.target.value) })}
                  />
                </div>
                <div className="field">
                  <label>Volume {Math.round(selectedAudio.volume * 100)}%</label>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={selectedAudio.volume}
                    onChange={(e) => patchAudio({ volume: Number(e.target.value) })}
                  />
                </div>
                <div className="field">
                  <label>Track</label>
                  <select
                    value={selectedAudio.track}
                    onChange={(e) => patchAudio({ track: Number(e.target.value) })}
                  >
                    <option value={0}>1 · Music bed</option>
                    <option value={1}>2 · VO / SFX</option>
                  </select>
                </div>
              </div>
              <div className="inline-actions">
                <button
                  className="btn ghost tiny"
                  type="button"
                  disabled={busy}
                  onClick={() => patchAudio({ muted: !selectedAudio.muted })}
                >
                  {selectedAudio.muted ? 'Unmute' : 'Mute'}
                </button>
                <button
                  className="btn ghost tiny"
                  type="button"
                  disabled={busy}
                  onClick={async () => {
                    const p = await api.deleteAudioClip(project.id, selectedAudio.id)
                    setProject(p)
                    setSel(null)
                    notify('Audio removed.')
                  }}
                >
                  Remove audio
                </button>
              </div>
            </>
          ) : selectedVideo ? (
            <>
              <div className="muted tiny" style={{ marginBottom: 8 }}>
                {selectedSeg?.shot?.title} · fine step {fineStep}s at this zoom
              </div>
              <div className="inline-actions" style={{ marginBottom: 8 }}>
                <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => nudgeTrim('in', -1)}>
                  In −
                </button>
                <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => nudgeTrim('in', 1)}>
                  In +
                </button>
                <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => nudgeTrim('out', -1)}>
                  Out −
                </button>
                <button className="btn ghost tiny" type="button" disabled={busy} onClick={() => nudgeTrim('out', 1)}>
                  Out +
                </button>
              </div>
              <div className="controls-grid">
                <div className="field">
                  <label>Trim in</label>
                  <input
                    type="number"
                    min={0}
                    step={fineStep}
                    value={selectedVideo.trim_in ?? 0}
                    onChange={(e) =>
                      patchVideo({
                        trim_in: Number(e.target.value),
                        start_sec: Number(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="field">
                  <label>Trim out</label>
                  <input
                    type="number"
                    min={0.05}
                    step={fineStep}
                    value={selectedVideo.trim_out ?? selectedVideo.end_sec ?? 3}
                    onChange={(e) =>
                      patchVideo({
                        trim_out: Number(e.target.value),
                        end_sec: Number(e.target.value),
                      })
                    }
                  />
                </div>
                <div className="field">
                  <label>Speed</label>
                  <select
                    value={String(selectedVideo.speed ?? 1)}
                    onChange={(e) => patchVideo({ speed: Number(e.target.value) })}
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
                <label>Zoom {((selectedVideo.scale ?? 1) * 100).toFixed(0)}%</label>
                <input
                  type="range"
                  min={1}
                  max={2.5}
                  step={0.05}
                  value={selectedVideo.scale ?? 1}
                  onChange={(e) => patchVideo({ scale: Number(e.target.value) })}
                />
              </div>
              <div className="controls-grid">
                <div className="field">
                  <label>Pan X</label>
                  <input
                    type="range"
                    min={-1}
                    max={1}
                    step={0.05}
                    value={selectedVideo.pan_x ?? 0}
                    onChange={(e) => patchVideo({ pan_x: Number(e.target.value) })}
                  />
                </div>
                <div className="field">
                  <label>Pan Y</label>
                  <input
                    type="range"
                    min={-1}
                    max={1}
                    step={0.05}
                    value={selectedVideo.pan_y ?? 0}
                    onChange={(e) => patchVideo({ pan_y: Number(e.target.value) })}
                  />
                </div>
              </div>
              <div className="field">
                <label>Filter</label>
                <select
                  value={selectedVideo.filter_id || 'none'}
                  onChange={(e) => patchVideo({ filter_id: e.target.value })}
                >
                  {DIRECTOR_FILTERS.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.label}
                    </option>
                  ))}
                </select>
              </div>
              {(selectedVideo.filter_id || 'none') !== 'none' && (
                <div className="field">
                  <label>Filter strength</label>
                  <input
                    type="range"
                    min={0.1}
                    max={1}
                    step={0.05}
                    value={selectedVideo.filter_intensity ?? 1}
                    onChange={(e) => patchVideo({ filter_intensity: Number(e.target.value) })}
                  />
                </div>
              )}
              <div className="field">
                <label>Caption</label>
                <textarea
                  rows={2}
                  value={editingCaption ? captionDraft : selectedVideo.caption || ''}
                  onChange={(e) => {
                    setCaptionDraft(e.target.value)
                    setEditingCaption(true)
                  }}
                  onBlur={() => {
                    if (editingCaption) saveCaption()
                  }}
                  placeholder="Type here or on the video…"
                />
              </div>
              <div className="field">
                <label>Caption style</label>
                <select
                  value={selectedVideo.caption_style || 'bottom'}
                  onChange={(e) => patchVideo({ caption_style: e.target.value })}
                >
                  {CAPTION_STYLES.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="inline-actions">
                <button
                  className="btn ghost tiny"
                  type="button"
                  disabled={busy}
                  onClick={() => startCaptionEdit(selectedVideo.caption || 'New caption')}
                >
                  Edit on video
                </button>
                <button
                  className="btn ghost tiny"
                  type="button"
                  disabled={busy || !selectedVideo.caption}
                  onClick={() => patchVideo({ caption: '', caption_x: 0, caption_y: 0 })}
                >
                  Clear caption
                </button>
              </div>

              <h4 style={{ margin: '14px 0 8px', fontFamily: 'var(--font-display)', color: 'var(--neon)' }}>
                Transition in
              </h4>
              <div className="muted tiny" style={{ marginBottom: 8 }}>
                How this clip arrives from the previous one.
              </div>
              <div className="provider-grid">
                {TRANSITIONS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`mode-chip ${(selectedVideo.transition || 'none') === t.id ? 'active' : ''}`}
                    disabled={busy}
                    onClick={() => applyTransition(t.id)}
                  >
                    <strong>{t.label}</strong>
                    <span>{t.blurb}</span>
                  </button>
                ))}
              </div>
              {(selectedVideo.transition || 'none') !== 'none' && (
                <div className="field" style={{ marginTop: 8 }}>
                  <label>Transition length {(selectedVideo.transition_dur ?? 0.35).toFixed(2)}s</label>
                  <input
                    type="range"
                    min={0.1}
                    max={1.5}
                    step={0.05}
                    value={selectedVideo.transition_dur ?? 0.35}
                    onChange={(e) => patchVideo({ transition_dur: Number(e.target.value) })}
                  />
                </div>
              )}
            </>
          ) : (
            <div className="empty">Select a clip on the timeline.</div>
          )}
        </div>
      </div>

      <div className="panel tt-timeline">
        <div className="inline-actions" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
          <h3 style={{ margin: 0 }}>Timeline</h3>
          <div className="inline-actions">
            <label className="muted tiny" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              Zoom
              <input
                type="range"
                min={16}
                max={160}
                step={4}
                value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))}
              />
              <span>{zoom}px/s</span>
            </label>
          </div>
        </div>

        <div className="tt-tracks" ref={trackRef} onClick={onTrackClick}>
          <div className="tt-ticks" style={{ width: px(totalSec) }}>
            {ticks.map((t) => (
              <span key={t} className="tt-tick" style={{ left: px(t) }}>
                {formatTimecode(t)}
              </span>
            ))}
          </div>

          <div className="tt-lane">
            <div className="tt-lane-label">Video</div>
            <div className="tt-lane-body" style={{ width: px(totalSec) }}>
              {layout.map((seg, i) => (
                <button
                  key={seg.clip.id}
                  type="button"
                  className={`tt-clip video ${sel?.kind === 'video' && sel.id === seg.clip.id ? 'active' : ''}`}
                  style={{ left: px(seg.start), width: Math.max(8, px(seg.dur)) }}
                  onClick={(e) => {
                    e.stopPropagation()
                    setSel({ kind: 'video', id: seg.clip.id })
                    setPlayhead(seg.start)
                  }}
                >
                  <span>
                    {i + 1}. {seg.shot?.title || 'Clip'}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="tt-lane captions">
            <div className="tt-lane-label">CC</div>
            <div className="tt-lane-body" style={{ width: px(totalSec) }}>
              {layout
                .filter((seg) => !!seg.clip.caption)
                .map((seg) => {
                  const localStart = seg.clip.caption_start ?? 0
                  const localEnd =
                    seg.clip.caption_end != null ? seg.clip.caption_end : seg.dur
                  const start = seg.start + localStart
                  const dur = Math.max(0.2, Math.min(seg.dur, localEnd) - localStart)
                  return (
                    <button
                      key={`cc-${seg.clip.id}`}
                      type="button"
                      className={`tt-clip caption ${sel?.kind === 'caption' && sel.id === seg.clip.id ? 'active' : ''}`}
                      style={{ left: px(start), width: Math.max(8, px(dur)) }}
                      onClick={(e) => {
                        e.stopPropagation()
                        setSel({ kind: 'caption', id: seg.clip.id })
                        setPlayhead(start)
                        startCaptionEdit(seg.clip.caption || '')
                      }}
                      title={seg.clip.caption}
                    >
                      <span>{seg.clip.caption}</span>
                    </button>
                  )
                })}
              {/* transition diamonds between clips */}
              {layout.slice(1).map((seg) => (
                <button
                  key={`tr-${seg.clip.id}`}
                  type="button"
                  className={`tt-trans-mark ${(seg.clip.transition || 'none') !== 'none' ? 'on' : ''}`}
                  style={{ left: px(seg.start) }}
                  title={
                    (seg.clip.transition || 'none') === 'none'
                      ? 'Hard cut — click clip to set transition'
                      : `${seg.clip.transition} ${seg.clip.transition_dur ?? 0.35}s`
                  }
                  onClick={(e) => {
                    e.stopPropagation()
                    setSel({ kind: 'video', id: seg.clip.id })
                    setPlayhead(seg.start)
                  }}
                />
              ))}
            </div>
          </div>

          <div className="tt-lane audio">
            <div className="tt-lane-label">Audio 1</div>
            <div className="tt-lane-body" style={{ width: px(totalSec) }}>
              {audioClips
                .filter((a) => a.track === 0)
                .map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className={`tt-clip audio ${sel?.kind === 'audio' && sel.id === a.id ? 'active' : ''} ${a.muted ? 'muted' : ''}`}
                    style={{ left: px(a.timeline_start), width: Math.max(8, px(a.duration_sec)) }}
                    onClick={(e) => {
                      e.stopPropagation()
                      setSel({ kind: 'audio', id: a.id })
                      setPlayhead(a.timeline_start)
                    }}
                  >
                    <span>{a.label}</span>
                  </button>
                ))}
            </div>
          </div>

          <div className="tt-lane audio">
            <div className="tt-lane-label">Audio 2</div>
            <div className="tt-lane-body" style={{ width: px(totalSec) }}>
              {audioClips
                .filter((a) => a.track !== 0)
                .map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className={`tt-clip audio sfx ${sel?.kind === 'audio' && sel.id === a.id ? 'active' : ''}`}
                    style={{ left: px(a.timeline_start), width: Math.max(8, px(a.duration_sec)) }}
                    onClick={(e) => {
                      e.stopPropagation()
                      setSel({ kind: 'audio', id: a.id })
                      setPlayhead(a.timeline_start)
                    }}
                  >
                    <span>{a.label}</span>
                  </button>
                ))}
            </div>
          </div>

          <div
            className="tt-playhead"
            style={{ left: px(playhead) }}
            title={formatTimecode(playhead)}
          />
        </div>

        <div className="tt-add-audio">
          <strong>Add clips &amp; audio</strong>
          <div className="muted tiny" style={{ marginBottom: 8 }}>
            Already have footage? Upload video onto the cut (inserts after the playhead clip). Audio
            lands at {formatTimecode(playhead)}.
          </div>
          <div className="inline-actions" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
            <label className="btn acid tiny">
              Upload video clip
              <input
                type="file"
                accept="video/*,.mp4,.webm,.mov,.mkv,.m4v,.gif"
                hidden
                disabled={busy}
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  e.target.value = ''
                  if (f) addUploadedVideo(f)
                }}
              />
            </label>
          </div>
          <div className="muted tiny" style={{ marginBottom: 8 }}>
            Music / VO / SFX under the video:
          </div>
          <div className="inline-actions" style={{ flexWrap: 'wrap' }}>
            <label className="btn ghost tiny">
              Upload audio
              <input
                type="file"
                accept="audio/*"
                hidden
                onChange={(e) => e.target.files?.[0] && addUploadedAudio(e.target.files[0])}
              />
            </label>
            {audioJobs.slice(0, 6).map((j) => (
              <button
                key={j.id}
                type="button"
                className="btn ghost tiny"
                disabled={busy}
                onClick={() => addAudioFromJob(j)}
                title={j.prompt}
              >
                + {j.model_label || 'bed'}
              </button>
            ))}
            {audioJobs.length === 0 && (
              <span className="muted tiny">No finished audio jobs yet — open Audio tab first.</span>
            )}
          </div>
        </div>
      </div>

      <div className="panel">
        <h3>Transitions</h3>
        <p className="muted tiny">
          Select the <em>incoming</em> clip, then pick how it arrives. Diamonds on the CC lane mark
          styled cuts.
        </p>
        <div className="provider-grid">
          {TRANSITIONS.map((t) => (
            <button
              key={t.id}
              type="button"
              className={`mode-chip ${(selectedVideo?.transition || 'none') === t.id ? 'active' : ''}`}
              disabled={busy || !selectedVideo}
              onClick={() => applyTransition(t.id)}
            >
              <strong>{t.label}</strong>
              <span>{t.blurb}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Filters (tap to apply on selected video)</h3>
        <div className="provider-grid">
          {DIRECTOR_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`mode-chip ${(selectedVideo?.filter_id || 'none') === f.id ? 'active' : ''}`}
              disabled={busy || !selectedVideo}
              onClick={() => patchVideo({ filter_id: f.id })}
            >
              <strong>{f.label}</strong>
              <span>{f.blurb}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
