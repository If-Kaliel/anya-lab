import { useEffect, useState, type RefObject } from 'react'
import { api, post } from './api'
import type { Video } from './types'

type Preview = { state: 'missing' | 'queued' | 'processing' | 'ready' | 'failed'; detail?: string; url?: string }

export default function RecordingPlayer({ video, playerRef, onTime }: { video: Video; playerRef: RefObject<HTMLVideoElement | null>; onTime: (time: number) => void }) {
  const [preview, setPreview] = useState<Preview>({ state: 'missing' })
  const [error, setError] = useState('')
  const [failedPlayback, setFailedPlayback] = useState(false)
  const [requesting, setRequesting] = useState(false)
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    setPreview({ state: 'missing' }); setFailedPlayback(false); setError('')
    async function poll() {
      try {
        const status = await api<Preview>(`/videos/${video.id}/preview`)
        if (!active) return
        if (status.state) setPreview(status)
        if (status.state === 'processing' || status.state === 'queued') timer = setTimeout(poll, 1000)
      } catch (e) { if (active) setError(e instanceof Error ? e.message : 'Não foi possível consultar a reprodução') }
    }
    poll()
    return () => { active = false; clearTimeout(timer) }
  }, [video.id, requesting])
  async function prepare() {
    setError(''); setRequesting(true)
    try { setPreview(await post<Preview>(`/videos/${video.id}/preview`, {})) }
    catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível preparar a gravação') }
    finally { setRequesting(false) }
  }
  const preparing = requesting || preview.state === 'processing' || preview.state === 'queued'
  const needsPreview = video.requires_preview || failedPlayback
  const ready = preview.state === 'ready'
  return <>
    {ready || !needsPreview ? <video key={`${video.id}-${ready}`} ref={playerRef} controls preload="metadata"
      src={ready ? `/api/videos/${video.id}/preview/media` : `/api/videos/${video.id}/media`}
      onTimeUpdate={e => onTime(e.currentTarget.currentTime)} onError={() => setFailedPlayback(true)} aria-label="Player da gravação"/>
      : <div className="empty-stage"><img src="/emblem.svg" alt=""/><h3>Reprodução compatível</h3><p>A cópia MP4 mantém o início do vídeo em zero e permite anotar MKV e outros codecs no navegador.</p>
        {preparing ? <p role="status">Preparando cópia local… Isso pode levar alguns minutos.</p> : <button className="secondary" onClick={prepare}>Preparar reprodução compatível</button>}
        {(error || preview.detail) && <p role="alert">{error || preview.detail}</p>}
      </div>}
  </>
}
