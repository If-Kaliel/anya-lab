import { useEffect, useState } from 'react'
import { post } from './api'
import type { Comparison, PairedResult } from './types'

const percent = (value: number | null) => value == null ? '—' : `${(value * 100).toFixed(1)}%`

export default function PairedComparison({ comparisons }: { comparisons: Comparison[] }) {
  const [first, setFirst] = useState('')
  const [second, setSecond] = useState('')
  const [result, setResult] = useState<PairedResult | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const match = comparisons.find(c => c.experiment_id === first)?.match_id
  useEffect(() => { setResult(null) }, [first, second, comparisons])
  async function compare() {
    setBusy(true); setError(''); setResult(null)
    try { setResult(await post<PairedResult>('/comparison/paired', { experiment_ids: [first, second] })) }
    catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível comparar') }
    finally { setBusy(false) }
  }
  return <div className="paired-comparison"><div className="paired-controls">
    <label>Experimento A<select aria-label="Experimento A" value={first} disabled={busy} onChange={e => { setFirst(e.target.value); setSecond('') }}><option value="">Selecione</option>{comparisons.map(c => <option key={c.experiment_id} value={c.experiment_id} disabled={c.stale}>{c.experiment_id.slice(0, 8)} · {c.model_id}{c.stale ? ' · reavaliar' : ''}</option>)}</select></label>
    <label>Experimento B<select aria-label="Experimento B" value={second} disabled={busy || !first} onChange={e => setSecond(e.target.value)}><option value="">Mesma gravação</option>{comparisons.filter(c => c.match_id === match && c.experiment_id !== first).map(c => <option key={c.experiment_id} value={c.experiment_id} disabled={c.stale}>{c.experiment_id.slice(0, 8)} · {c.model_id}{c.stale ? ' · reavaliar' : ''}</option>)}</select></label>
    <button className="secondary" disabled={!first || !second || busy} onClick={compare}>{busy ? 'Comparando…' : 'Comparar nos mesmos instantes'}</button>
  </div>{error && <p className="alert error" role="alert">{error}</p>}
  {result && <><p className="helper">{result.common_windows} instantes em comum · {result.mode === 'technical_demo' ? 'Demonstração sintética' : 'Baselines não validados'}. Janelas sobrepostas e uma única partida não sustentam superioridade científica.</p><div className="table-scroll"><table><thead><tr><th>Modelo / experimento</th><th>N pareadas</th><th>Excluídas</th><th>Accuracy</th><th>Brier</th><th>Log loss</th></tr></thead><tbody>{result.results.map(r => <tr key={r.experiment_id}><td>{r.model_id} / {r.experiment_id.slice(0, 8)}</td><td>{r.metrics.evaluated}</td><td>{r.metrics.excluded}</td><td>{percent(r.metrics.accuracy)}</td><td>{r.metrics.brier_score?.toFixed(3) ?? '—'}</td><td>{r.metrics.log_loss?.toFixed(3) ?? '—'}</td></tr>)}</tbody></table></div></>}
  </div>
}
