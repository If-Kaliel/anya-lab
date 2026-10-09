import { useEffect, useRef, useState } from 'react'
import { api, post } from './api'
import AnyaPresence from './AnyaPresence'
import type { Experiment } from './types'

type Identity = { id: string; text: string; backend: string; seed: number; sha256: string }
type Job = { id: string; text: string; state: string; role: string; priority: string; latency_ms?: number; error?: string; replay: { experiment_id: string; timestamp: number; expires_at: number } | null; playback_events?: { state: string }[] }
type Status = { selected_identity: string | null; active_job: string | null; backend: string; profile: string; resources: { gpu: string | null; real_time_validated: boolean } }
type Call = { id: string; timestamp: number; text: string; decision: string; reason: string | null; voice_job_id?: string; evidence: { kind: string; timestamp: number; source: string }[] }

export default function VoicePanel({ visible, experiment }: { visible: boolean; experiment: Experiment | null }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [identities, setIdentities] = useState<Identity[]>([])
  const [history, setHistory] = useState<Job[]>([])
  const [calls, setCalls] = useState<Call[]>([])
  const [enabled, setEnabled] = useState(false)
  const [comms, setComms] = useState(false)
  const [volume, setVolume] = useState(.7)
  const [frequency, setFrequency] = useState(10)
  const [seed, setSeed] = useState(42)
  const [text, setText] = useState('I am Anya. We will follow the evidence, and leave uncertainty visible.')
  const [error, setError] = useState('')
  const [speaking, setSpeaking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [deciding, setDeciding] = useState(false)
  const audio = useRef<HTMLAudioElement>(null)
  const played = useRef(new Set<string>())
  const pending = useRef(new Set<string>())
  const playing = useRef<Job | null>(null)
  const cursor = useRef('')
  const current = useRef(experiment)
  current.current = experiment
  const alive = useRef(true)

  async function refresh() {
    const [s, i, h] = await Promise.all([api<Status>('/voice/status'), api<Identity[]>('/voice/identities'), api<Job[]>('/voice/history')])
    if (alive.current) { setStatus(s); setIdentities(i); setHistory(h) }
  }
  useEffect(() => {
    alive.current = true
    refresh().catch(e => setError(e.message))
    const timer = setInterval(() => { if (visible || pending.current.size) refresh().catch(e => setError(e.message)) }, 1500)
    return () => { alive.current = false; clearInterval(timer); audio.current?.pause() }
  }, [visible])
  useEffect(() => { if (audio.current) audio.current.volume = volume }, [volume])

  async function run(task: () => Promise<void>) {
    setBusy(true); setError('')
    try { await task(); await refresh() } catch (e) { setError(e instanceof Error ? e.message : 'Falha de voz') } finally { setBusy(false) }
  }
  async function submit(role: 'design' | 'clone') {
    await run(async () => {
      const job = await post<Job>('/voice/jobs', { text, role, seed, language: 'English' })
      pending.current.add(job.id)
    })
  }
  async function play(job: Job) {
    const a = audio.current
    if (!a) return
    if (job.replay && (current.current?.id !== job.replay.experiment_id || current.current.frontier > job.replay.expires_at)) return
    if (playing.current) a.pause()
    playing.current = job
    a.src = `/api/voice/jobs/${job.id}/audio`
    a.volume = volume
    try { await a.play(); played.current.add(job.id); pending.current.delete(job.id) }
    catch { playing.current = null; setError('O navegador bloqueou a reprodução automática. Use Ouvir na mensagem pronta.') }
  }
  useEffect(() => {
    for (const j of history) if (['failed', 'expired', 'cancelled'].includes(j.state)) pending.current.delete(j.id)
    const active = playing.current
    if (active && history.some(j => j.id === active.id && ['cancelled', 'expired'].includes(j.state))) {
      audio.current?.pause(); playing.current = null
    }
    if (!enabled || speaking) return
    const rank: Record<string, number> = { critical: 0, high: 1, normal: 2, low: 3 }
    const next = history.filter(j => pending.current.has(j.id) && j.state === 'ready' && !played.current.has(j.id))
      .sort((a, b) => rank[a.priority] - rank[b.priority])[0]
    if (next && !playing.current) void play(next)
  }, [history, enabled, speaking])
  useEffect(() => {
    const j = playing.current
    if (j?.replay && (experiment?.id !== j.replay.experiment_id || experiment.frontier > j.replay.expires_at)) {
      audio.current?.pause(); playing.current = null
    }
    if (!experiment || experiment.frontier < 0) return
    post(`/experiments/${experiment.id}/comms/clock`, { timestamp: experiment.frontier }).catch(() => {})
    const key = `${experiment.id}:${experiment.frontier}`
    if (key === cursor.current) return
    const old = cursor.current; cursor.current = key
    if (!enabled || !comms || !old.startsWith(experiment.id + ':')) return
    setDeciding(true)
    post<Call>(`/experiments/${experiment.id}/comms`, { frequency }).then(c => {
      if (c.voice_job_id) pending.current.add(c.voice_job_id)
      return api<Call[]>(`/experiments/${experiment.id}/comms`)
    }).then(setCalls).catch(e => setError(e.message)).finally(() => setDeciding(false))
  }, [experiment?.id, experiment?.frontier, enabled, comms, frequency])
  function playback(state: 'started' | 'completed' | 'interrupted') {
    setSpeaking(state === 'started')
    if (playing.current) post(`/voice/jobs/${playing.current.id}/playback`, { state }).catch(() => {})
    if (state === 'completed') { playing.current = null; void refresh() }
  }

  return <section className="voice-panel panel" hidden={!visible}>
    <div className="panel-heading"><h2>Anya Speaks · voz local</h2><span className="eyebrow">QWEN3-TTS / EXPERIMENTAL</span></div>
    <div className="voice-content">
      <AnyaPresence state={speaking ? 'speaking' : status?.active_job ? 'reasoning' : deciding ? 'observing' : 'dormant'}/>
      {error && <p className="alert error" role="alert">{error}</p>}
      <p className="helper">VoiceDesign 1.7B cria referências originais. Base 0.6B reutiliza a identidade selecionada. Nenhum download automático; inglês experimental. {status?.backend === 'mock-test-tone' && <strong>MOCK DE TESTE · sem voz humana.</strong>}</p>
      <div className="voice-controls">
        <label className="check"><input type="checkbox" checked={enabled} onChange={e => { setEnabled(e.target.checked); if (!e.target.checked) audio.current?.pause() }}/>Ativar voz</label>
        <label>Volume<input aria-label="Volume da voz" type="range" min="0" max="1" step=".05" value={volume} onChange={e => setVolume(Number(e.target.value))}/></label>
        <label>Idioma<select aria-label="Idioma da voz"><option>English</option><option disabled>Português brasileiro · qualidade ainda não validada</option></select></label>
        <label>Seed da amostra<input type="number" min="0" max="4294967295" value={seed} onChange={e => setSeed(Number(e.target.value))}/></label>
      </div>
      <label>Texto para síntese<textarea aria-label="Texto para síntese" value={text} maxLength={500} onChange={e => setText(e.target.value)}/></label>
      <div className="voice-actions"><button className="secondary" disabled={busy} onClick={() => submit('design')}>Gerar amostra original</button><button className="primary" disabled={busy || !status?.selected_identity} onClick={() => submit('clone')}>Sintetizar com voz selecionada</button><button className="secondary" disabled={busy || !!status?.active_job} onClick={() => run(async () => { await post('/voice/unload', {}) })}>Liberar modelo da GPU</button></div>
      <p className="helper" role="status">{status?.active_job ? 'Síntese em andamento; latência será registrada ao concluir.' : 'Serviço ocioso.'} {status?.resources?.gpu && `GPU: ${status.resources.gpu}`}</p>
      <label>Perfil de execução<select aria-label="Perfil de execução" value={status?.profile ?? 'research'} onChange={e => run(async () => { await post('/voice/profile', { name: e.target.value }) })}><option value="research">Research Mode · geração offline</option><option value="replay_commentary">Replay Commentary · calls com expiração</option><option value="lightweight">Lightweight · libera modelo após gerar</option></select></label><h3>Comparar e selecionar referências</h3>
      {!identities.length && <p className="helper">Gere amostras com seeds diferentes. Nenhuma referência é selecionada automaticamente.</p>}
      <div className="voice-identities">{identities.map(i => <article key={i.id}><p>Seed {i.seed} · {i.id.slice(0, 8)} {status?.selected_identity === i.id && '· Selecionada'}</p><p className="helper">{i.text}</p><audio controls preload="none" src={`/api/voice/identities/${i.id}/audio`}/><button className="secondary" disabled={busy || status?.selected_identity === i.id} onClick={() => run(async () => { await post('/voice/select', { identity_id: i.id }) })}>Selecionar identidade</button></article>)}</div>
      <h3>Oracle Comms · somente replay</h3>
      <label className="check"><input type="checkbox" checked={comms} onChange={e => setComms(e.target.checked)}/>Gerar calls ao avançar novas previsões do experimento</label>
      <label>Intervalo mínimo entre intervenções (s)<input type="number" min="5" max="120" value={frequency} onChange={e => setFrequency(Number(e.target.value))}/></label>
      <p className="helper">Riscos manuais recentes e confiáveis podem gerar warnings. Posições ocultas são desconhecidas. Calls expiram após 5 segundos de replay; síntese lenta pode ser descartada. Ative aqui e avance no Replay Workspace.</p>
      {calls.map(c => <div className="call-record" key={c.id}><strong>T={c.timestamp}s · {c.decision}</strong><p>{c.text}</p><small>{c.reason}</small></div>)}
      <h3>Histórico textual e fila de reprodução</h3>{experiment && <div className="voice-actions">{['json', 'csv', 'srt'].map(f => <a className="secondary" key={f} href={`/api/experiments/${experiment.id}/director/${f}`}>Voice Timeline {f.toUpperCase()}</a>)}</div>}
      <audio ref={audio} controls={!!playing.current} onPlay={() => playback('started')} onPause={() => playback('interrupted')} onEnded={() => playback('completed')}/>
      {history.map(j => <article className="call-record" key={j.id}><p>{j.text}</p><p className="helper">{j.state} · {j.role} · {j.latency_ms?.toFixed(0) ?? '—'} ms · {j.playback_events?.some(e => e.state === 'completed') ? 'Reprodução concluída' : 'Sem reprodução concluída registrada'}</p>{j.error && <p className="helper">{j.error}</p>}<div className="voice-actions"><button className="secondary" disabled={!enabled || j.state !== 'ready'} onClick={() => play(j)}>Ouvir</button><button className="secondary" disabled={busy} onClick={() => run(async () => { const next = await post<Job>(`/voice/jobs/${j.id}/repeat`, {}); pending.current.add(next.id) })}>Repetir mensagem</button>{['queued', 'synthesizing', 'ready'].includes(j.state) && <button className="secondary" onClick={() => run(async () => { await post(`/voice/jobs/${j.id}/cancel`, {}); if (playing.current?.id === j.id) audio.current?.pause() })}>Cancelar</button>}</div></article>)}
    </div>
  </section>
}
