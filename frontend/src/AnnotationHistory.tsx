import { useEffect, useState } from 'react'
import { History, Pencil, RotateCcw, X } from 'lucide-react'
import { api, post } from './api'
import Dialog from './Dialog'
import type { AnnotationHistory as HistoryRecord, AnnotationKind, Annotations, AnnotationValue } from './types'

const kindLabels = { observations: 'Observação', events: 'Eliminação', reviews: 'Intervalo revisado' }
const teams: Record<string, string> = { ally: 'Aliada', enemy: 'Adversária', unknown: 'Desconhecida' }
const riskLabels: Record<string, string> = { ally_risk: 'Risco aliado', enemy_risk: 'Risco adversário', visibility: 'Visibilidade' }
function describe(kind: AnnotationKind, value: AnnotationValue) {
  if (kind === 'reviews') return `${value.start}s → ${value.end}s · ${value.reliable ? 'Confiável' : 'Incerto'}`
  if (kind === 'events') return `${value.timestamp?.toFixed(3)}s · ${teams[value.team ?? 'unknown']} · ${value.reliable ? 'Confiável' : 'Incerta'}`
  return `${value.timestamp?.toFixed(3)}s · ${riskLabels[value.kind ?? '']} ${value.value?.toFixed(2)} · Confiança ${((value.confidence ?? 0) * 100).toFixed(0)}%`
}

export default function AnnotationHistory({ videoId, annotations, onChanged }: {
  videoId: string; annotations: Annotations; onChanged: (kind: AnnotationKind) => Promise<void>
}) {
  const [histories, setHistories] = useState<HistoryRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<HistoryRecord | null>(null)
  const [mode, setMode] = useState<'history' | 'edit' | 'retract' | 'restore'>('history')
  const [draft, setDraft] = useState<AnnotationValue>({})
  const [reason, setReason] = useState('')
  const [target, setTarget] = useState(0)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    setSelected(null); setError(''); setLoading(true)
    if (!videoId) { setHistories([]); setLoading(false); return }
    api<HistoryRecord[]>(`/videos/${videoId}/annotation-history`)
      .then(rows => { if (active) setHistories(rows) })
      .catch(e => { if (active) setError(e.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [videoId, annotations])

  function open(record: HistoryRecord, nextMode: typeof mode, targetRevision?: number) {
    setSelected(record); setMode(nextMode); setReason(''); setError('')
    setDraft({ ...record.entries.at(-1)!.annotation })
    setTarget(targetRevision ?? record.entries.filter(e => !e.retracted).at(-1)!.revision)
  }
  function update(field: keyof AnnotationValue, value: string | number | boolean) {
    setDraft(old => ({ ...old, [field]: value }))
  }
  async function save() {
    if (!selected || !reason.trim()) return
    setSaving(true); setError('')
    const kind = selected.kind
    const common = { expected_revision: selected.current_revision, reason: reason.trim() }
    let body: unknown = common
    let operation: string = mode
    if (mode === 'edit') {
      operation = 'revise'
      const annotation = kind === 'observations'
        ? { timestamp: draft.timestamp, kind: draft.kind, value: draft.value, confidence: draft.confidence, note: draft.note ?? '' }
        : kind === 'events' ? { timestamp: draft.timestamp, team: draft.team, reliable: draft.reliable, note: draft.note ?? '' }
          : { start: draft.start, end: draft.end, reliable: draft.reliable, note: draft.note ?? '' }
      body = { ...common, annotation }
    } else if (mode === 'restore') body = { ...common, target_revision: target }
    try {
      await post(`/videos/${videoId}/annotations/${kind}/${selected.id}/${operation}`, body)
      await onChanged(kind)
      setSelected(null)
    } catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível salvar a revisão') }
    finally { setSaving(false) }
  }
  return <>
    <div className="annotation-list revised-list">
      {error && !selected && <p role="alert" className="helper">{error}</p>}
      {loading && <p className="helper" role="status">Carregando histórico…</p>}
      {!loading && !histories.length && <p className="helper">Nenhuma anotação registrada.</p>}
      {histories.map(record => <article className={`annotation-row ${record.retracted ? 'retracted' : ''}`} key={`${record.kind}-${record.id}`}>
        <div><span className="outline-badge">{kindLabels[record.kind]} · v{record.current_revision}</span><p>{describe(record.kind, record.entries.at(-1)!.annotation)}</p>
          {record.retracted && <small>Retirada da versão atual do dataset</small>}{!record.valid && <small role="alert">Falha de integridade: alterações bloqueadas.</small>}</div>
        <div className="annotation-actions">
          {!record.retracted && <button className="text-link" disabled={!record.valid} aria-label={`Corrigir ${kindLabels[record.kind]} #${record.id}`} onClick={() => open(record, 'edit')}><Pencil size={12}/>Corrigir</button>}
          <button className="text-link" aria-label={`Histórico ${kindLabels[record.kind]} #${record.id}`} onClick={() => open(record, 'history')}><History size={12}/>Histórico</button>
          {record.retracted ? <button className="text-link" disabled={!record.valid} aria-label={`Restaurar ${kindLabels[record.kind]} #${record.id}`} onClick={() => open(record, 'restore')}><RotateCcw size={12}/>Restaurar</button>
            : <button className="text-link" disabled={!record.valid} aria-label={`Retirar ${kindLabels[record.kind]} #${record.id}`} onClick={() => open(record, 'retract')}><X size={12}/>Retirar</button>}
        </div>
      </article>)}
    </div>
    {selected && <Dialog title={mode === 'edit' ? 'Corrigir anotação' : mode === 'retract' ? 'Retirar anotação' : mode === 'restore' ? 'Restaurar versão anterior' : 'Histórico da anotação'} onClose={() => { if (!saving) setSelected(null) }}>
      <p className="helper">{kindLabels[selected.kind]} #{selected.id} · versão atual {selected.current_revision}. As previsões e os registros anteriores são preservados.</p>
      {error && <div className="alert error" role="alert">{error}</div>}
      {mode === 'edit' && <div className="revision-fields">
        {selected.kind === 'reviews' ? <><label>Início corrigido<input aria-label="Início corrigido" type="number" min="0" step="0.001" value={draft.start ?? 0} onChange={e => update('start', Number(e.target.value))}/></label><label>Fim corrigido<input aria-label="Fim corrigido" type="number" min="0" step="0.001" value={draft.end ?? 0} onChange={e => update('end', Number(e.target.value))}/></label></>
          : <label>Timestamp corrigido<input aria-label="Timestamp corrigido" type="number" min="0" step="0.001" value={draft.timestamp ?? 0} onChange={e => update('timestamp', Number(e.target.value))}/></label>}
        {selected.kind === 'observations' ? <><label>Tipo de observação<select value={draft.kind} onChange={e => update('kind', e.target.value)}>{Object.entries(riskLabels).map(([k, name]) => <option key={k} value={k}>{name}</option>)}</select></label><label>Valor corrigido<input aria-label="Valor corrigido" type="number" min="0" max="1" step="0.01" value={draft.value ?? 0} onChange={e => update('value', Number(e.target.value))}/></label><label>Confiança corrigida<input aria-label="Confiança corrigida" type="number" min="0" max="1" step="0.01" value={draft.confidence ?? 0} onChange={e => update('confidence', Number(e.target.value))}/></label></>
          : <>{selected.kind === 'events' && <label>Equipe corrigida<select aria-label="Equipe corrigida" value={draft.team} onChange={e => update('team', e.target.value)}>{Object.entries(teams).map(([k, name]) => <option key={k} value={k}>{name}</option>)}</select></label>}<label className="check"><input type="checkbox" checked={draft.reliable ?? false} onChange={e => update('reliable', e.target.checked)}/>Anotação confiável</label></>}
        <label>Nota corrigida<input aria-label="Nota corrigida" value={draft.note ?? ''} maxLength={500} onChange={e => update('note', e.target.value)}/></label>
      </div>}
      {mode === 'retract' && <p className="helper">Esta anotação deixará de participar das próximas avaliações e dos novos experimentos. Você pode restaurá-la pelo histórico.</p>}
      {mode === 'restore' && <p className="helper">A versão {target} será copiada para uma nova revisão, sem apagar alterações intermediárias.</p>}
      {mode !== 'history' && <><label>Motivo da alteração<input aria-label="Motivo da alteração" value={reason} maxLength={500} onChange={e => setReason(e.target.value)} placeholder="Descreva a evidência que justifica a revisão"/></label><button className="primary full" disabled={saving || !reason.trim()} onClick={save}>{saving ? 'Salvando revisão…' : mode === 'retract' ? 'Confirmar retirada' : mode === 'restore' ? 'Confirmar restauração' : 'Salvar correção'}</button></>}
      <ol className="revision-journal">{selected.entries.slice().reverse().map(entry => <li key={entry.revision}><div><b>Versão {entry.revision}{entry.retracted ? ' · retirada' : ''}</b><small>{entry.recorded_at ? new Date(entry.recorded_at).toLocaleString('pt-BR') : 'Registro anterior à atualização'}</small></div><p>{describe(selected.kind, entry.annotation)}</p><p>{entry.reason}</p>{entry.annotation.note && <p className="helper">{entry.annotation.note}</p>}{mode === 'history' && !entry.retracted && entry.revision !== selected.current_revision && <button className="text-link" disabled={!selected.valid} onClick={() => open(selected, 'restore', entry.revision)}>Restaurar versão {entry.revision}</button>}</li>)}</ol>
    </Dialog>}
  </>
}
