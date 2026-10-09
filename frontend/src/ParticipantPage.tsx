import { useEffect, useState } from 'react'
import { LockKeyhole, ShieldCheck } from 'lucide-react'
import { timecode } from './api'
import type { Observation } from './types'

export type TrialContext = { state: 'awaiting_prediction' | 'answers_locked'; round_index?: number; total_rounds: number; timestamp?: number; horizon?: number; max_accessible_timestamp?: number; context_hash?: string; frames?: { timestamp: number; sha256: string }[]; observations?: Observation[]; mode: string }
const classes = ['ally_first', 'enemy_first', 'none'] as const
const labels = ['Aliado primeiro', 'Adversário primeiro', 'Nenhuma eliminação']

export async function participantRequest<T>(path: string, token: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/participant/${path}`, { method: body ? 'POST' : 'GET',
    headers: { Authorization: `Bearer ${token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}) })
  if (!response.ok) { const error = await response.json(); throw new Error(typeof error.detail === 'string' ? error.detail : 'Resposta inválida') }
  return response.json()
}

export default function ParticipantPage() {
  const [token, setToken] = useState(() => new URLSearchParams(location.hash.slice(1)).get('trial') || '')
  const [invite, setInvite] = useState('')
  const [context, setContext] = useState<TrialContext | null>(null)
  const [image, setImage] = useState('')
  const [frame, setFrame] = useState<number | null>(null)
  const [values, setValues] = useState([33, 33, 34])
  const [abstain, setAbstain] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const total = values.reduce((a,b) => a+b, 0)

  useEffect(() => {
    if (!token) return
    let active = true
    setBusy(true); setError(''); setContext(null)
    participantRequest<TrialContext>('context', token).then(c => { if (active) { setContext(c); setFrame(c.frames?.at(-1)?.timestamp ?? null) } })
      .catch(e => { if (active) setError(e.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [token])

  useEffect(() => {
    setImage('')
    if (!context || frame == null || context.state === 'answers_locked') return
    let active = true
    let url = ''
    fetch(`/api/participant/frame?timestamp=${frame}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async response => { if (!response.ok) throw new Error('Quadro indisponível'); return response.blob() })
      .then(blob => { if (active) { url = URL.createObjectURL(blob); setImage(url) } })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false; if (url) URL.revokeObjectURL(url) }
  }, [token, frame, context])

  function enter() {
    const match = invite.match(/(?:trial=)?([a-f0-9]{64})(?:$|&)/)
    if (!match) { setError('Cole um convite válido do laboratório.'); return }
    setToken(match[1]); setError('')
  }
  async function submit() {
    if (!context || context.state !== 'awaiting_prediction') return
    setBusy(true); setError('')
    try {
      await participantRequest('answer', token, { round_index: context.round_index, context_hash: context.context_hash, abstain,
        probabilities: abstain ? null : Object.fromEntries(classes.map((c,i) => [c, values[i]/100])) })
      setNotice('Resposta bloqueada. Ela não pode ser alterada.')
      setContext(null); setFrame(null)
      const next = await participantRequest<TrialContext>('context',token)
      setContext(next); setFrame(next.frames?.at(-1)?.timestamp ?? null); setValues([33,33,34]); setAbstain(false)
    } catch (e) { setError(e instanceof Error ? e.message : 'Falha ao registrar') }
    finally { setBusy(false) }
  }

  return <main className="participant-shell">
    <header className="participant-header"><img src="/emblem.svg" alt=""/><div><p className="eyebrow">ANYA / AVALIAÇÃO LOCAL</p><h1>Human vs Anya</h1></div><LockKeyhole size={22}/></header>
    <p className="helper">Preveja a primeira eliminação visível nos próximos 15 segundos. Use a perspectiva da equipe definida pelo pesquisador. O contexto termina em T.</p>
    {(!token || (error && !context)) && <section className="panel lab-content"><label>Convite local<input value={invite} onChange={e => setInvite(e.target.value)} placeholder="Cole o link de participação"/></label><button className="primary" onClick={enter}>Abrir avaliação</button></section>}
    {error && <p className="error-banner" role="alert">{error}</p>}{notice && <p className="notice-banner" role="status"><ShieldCheck size={16}/>{notice}</p>}
    {busy && !context && <p role="status">Carregando contexto autorizado…</p>}
    {context?.state === 'answers_locked' && <section className="panel lab-content"><h2>Respostas bloqueadas</h2><p>{context.total_rounds} respostas registradas. Encerre esta coleta e volte ao pesquisador para revelar o resultado.</p><span className="outline-badge">{context.mode === 'technical_demo' ? 'DEMONSTRAÇÃO SINTÉTICA' : 'AVALIAÇÃO LOCAL'}</span></section>}
    {context?.state === 'awaiting_prediction' && <div className="workspace-grid">
      <section className="panel"><div className="panel-heading"><h2>Rodada {(context.round_index ?? 0)+1} de {context.total_rounds}</h2><span className="eyebrow">T = {context.timestamp?.toFixed(3)}s · +15s</span></div>
        <div className="video-stage">{image ? <img className="inference-frame" src={image} alt={`Quadro autorizado em ${frame}s`}/> : <p>Carregando quadro…</p>}</div>
        <div className="lab-content"><div className="voice-actions">{context.frames?.map((f,i) => <button className="secondary" key={i} disabled={busy || frame === f.timestamp} onClick={() => setFrame(f.timestamp)}>Quadro {timecode(f.timestamp)}</button>)}</div>
          <p className="helper">{context.mode === 'technical_demo' ? 'Demonstração sintética.' : 'Gravação real; baselines não validados.'} Quadros e evidências autorizados até {context.max_accessible_timestamp?.toFixed(3)}s. Sem controles para avançar o vídeo.</p>
          <details><summary>Evidências disponíveis</summary>{context.observations?.length ? <table><thead><tr><th>T</th><th>Observação</th><th>Valor</th><th>Confiança</th></tr></thead><tbody>{context.observations.map((o,i) => <tr key={i}><td>{o.timestamp.toFixed(3)}s</td><td>{o.kind} · {o.source}</td><td>{o.value.toFixed(3)}</td><td>{(o.confidence*100).toFixed(0)}%</td></tr>)}</tbody></table> : <p>Sem evidências registradas.</p>}</details>
        </div>
      </section>
      <section className="panel lab-content"><h2>Sua previsão</h2><p className="helper">Distribua 100% entre os três resultados, ou abstenha-se se o contexto for insuficiente.</p>
        <label className="check"><input type="checkbox" checked={abstain} disabled={busy} onChange={e => setAbstain(e.target.checked)}/>Abster-se de prever</label>
        {!abstain && classes.map((c,i) => <label key={c}>{labels[i]} (%)<input type="number" min="0" max="100" step="1" value={values[i]} disabled={busy} onChange={e => setValues(old => old.map((n,j) => i===j ? Number(e.target.value) : n))}/></label>)}
        {!abstain && <p className="helper">Total: {total}%</p>}
        <button className="primary full" disabled={busy || !image || (!abstain && (Math.abs(total-100)>1e-6 || values.some(n => !Number.isFinite(n) || n<0 || n>100)))} onClick={submit}>Bloquear resposta</button>
        <p className="helper">O registro é definitivo. A IA e os resultados permanecem ocultos durante a coleta.</p>
      </section>
    </div>}
  </main>
}
