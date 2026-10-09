import { useState } from 'react'
import { api, post } from './api'
import AnyaPresence from './AnyaPresence'
import type { Experiment } from './types'

type Hypothesis = { id: string; timestamp: number; type: string; description: string; probability: number | null; evidence: { kind: string; timestamp: number; value: number; confidence: number }[]; awareness: { unknown: string[] }; model_id: string }
type Result = { hypothesis_id: string; verdict: string; report_id: number }
type Memory = { observations: number; frequencies: Record<string, number>; wilson_95: Record<string, number[]>; scope: string }

export default function StrategicPanel({ experiment, revealed }: { experiment: Experiment; revealed: boolean }) {
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [memory, setMemory] = useState<Memory | null>(null)
  const [scope, setScope] = useState('short_term')
  const [action, setAction] = useState('hold')
  const [profile, setProfile] = useState(() => crypto.randomUUID().replaceAll('-', ''))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function run(task: () => Promise<void>) {
    setBusy(true); setError('')
    try { await task() } catch (e) { setError(e instanceof Error ? e.message : 'Falha na pesquisa') } finally { setBusy(false) }
  }
  const base = `/experiments/${experiment.id}`
  async function loadMemory() { setMemory(await api<Memory>(`${base}/memory?scope=${scope}&profile_id=${profile}`)) }
  return <section className="panel"><div className="panel-heading"><h2>Strategic Intelligence</h2><span className="eyebrow">HIPÓTESES / MEMÓRIA MANUAL</span></div><div className="voice-content">
    <AnyaPresence state={busy ? 'reasoning' : results.length ? 'reviewing' : hypotheses.some(h => h.type === 'abstention') ? 'uncertain' : 'dormant'}/>
    {error && <p className="alert error" role="alert">{error}</p>}
    <p className="helper">Somente o snapshot da última previsão registrada. Hipóteses heurísticas não são probabilidades calibradas. Posições ocultas e intenções continuam desconhecidas.</p>
    <div className="voice-actions"><button className="secondary" disabled={busy || experiment.frontier < 0} onClick={() => run(async () => { await post(`${base}/hypotheses`, {}); const h = await api<{ hypotheses: Hypothesis[]; evaluations: Result[] }>(`${base}/hypotheses`); setHypotheses(h.hypotheses); setResults(h.evaluations) })}>Registrar / consultar hipóteses</button><button className="secondary" disabled={busy || !revealed} onClick={() => run(async () => setResults(await post<Result[]>(`${base}/hypotheses/evaluate`, {})))}>Avaliar após revelação</button></div>
    {hypotheses.map(h => <article className="call-record" key={h.id}><strong>T={h.timestamp}s · {h.type}</strong><p>{h.description}</p><p className="helper">{h.model_id} · Probabilidade: {h.probability ?? 'não calibrada / não atribuída'}</p><details><summary>Evidências disponíveis</summary>{h.evidence.map((e, i) => <p key={i}>{e.kind} · T={e.timestamp}s · valor {e.value.toFixed(2)} · confiança {e.confidence.toFixed(2)}</p>)}<p>Desconhecido: {h.awareness.unknown.join(', ')}</p></details>{results.filter(r => r.hypothesis_id === h.id).map((r, i) => <p className="helper" key={i}>Após revelação · relatório {r.report_id}: {r.verdict}</p>)}</article>)}
    <h3>Memória de comportamento observado</h3><p className="helper">Cadastre uma ação vista até T={experiment.frontier}s. O identificador é um pseudônimo local; não use nome, conta ou dado biométrico. As frequências descrevem anotações, sem inferir motivação.</p>
    <div className="voice-controls"><label>Perfil local<input aria-label="Perfil local" value={profile} maxLength={32} onChange={e => setProfile(e.target.value)}/></label><label>Ação observada<select aria-label="Ação observada" value={action} onChange={e => setAction(e.target.value)}><option value="hold">Manter posição</option><option value="advance">Avançar</option><option value="retreat">Recuar</option><option value="alternate_route">Rota alternativa</option></select></label><label>Escopo<select aria-label="Escopo da memória" value={scope} onChange={e => setScope(e.target.value)}><option value="short_term">Curto prazo (60s)</option><option value="session">Sessão experimental</option><option value="long_term">Pesquisa histórica (somente train)</option></select></label></div>
    <div className="voice-actions"><button className="secondary" disabled={busy || experiment.frontier < 0} onClick={() => run(async () => { await post(`${base}/memory`, { profile_id: profile, timestamp: experiment.frontier, action }); await loadMemory() })}>Registrar ação em T</button><button className="secondary" disabled={busy || experiment.frontier < 0} onClick={() => run(loadMemory)}>Consultar frequências</button></div>
    {memory && <><p className="helper">{memory.observations} observações · {memory.scope}</p><table><thead><tr><th>Ação</th><th>Contagem</th><th>Intervalo Wilson 95%</th></tr></thead><tbody>{Object.entries(memory.frequencies).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td><td>{memory.wilson_95[k].map(n => `${(n*100).toFixed(1)}%`).join(' – ')}</td></tr>)}</tbody></table></>}
  </div></section>
}
