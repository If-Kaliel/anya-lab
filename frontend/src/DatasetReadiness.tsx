import { useEffect, useState } from 'react'
import { api } from './api'
import type { Annotations } from './types'

type Readiness = { total_windows: number; eligible_windows: number; excluded_reasons: Record<string, number>; observations: number }
const reasons: Record<string, string> = { interval_not_reviewed: 'Revisão incompleta', unreliable_review_overlap: 'Intervalo incerto', ambiguous_first_event: 'Primeiro evento ambíguo', simultaneous_opposite_teams: 'Equipes eliminadas simultaneamente' }

export default function DatasetReadiness({ videoId, annotations }: { videoId: string; annotations: Annotations }) {
  const [readiness, setReadiness] = useState<Readiness | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    setReadiness(null); setError('')
    if (videoId) api<Readiness>(`/videos/${videoId}/readiness`).then(r => { if (active) setReadiness(r) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [videoId, annotations])
  if (error) return <p className="helper" role="alert">{error}</p>
  if (readiness?.total_windows == null) return null
  return <div className="dataset-readiness"><p className="eyebrow">QUALIDADE DA ANOTAÇÃO</p><strong>{readiness.eligible_windows} / {readiness.total_windows} janelas avaliáveis</strong>
    <p className="helper">Janelas de 15s a cada 5s. Isso mede a cobertura das anotações, sem validar a capacidade do modelo.</p>
    {Object.entries(readiness.excluded_reasons).map(([reason, count]) => <p className="helper" key={reason}>{reasons[reason] ?? reason}: {count}</p>)}
    {!readiness.observations && <p className="helper">Sem observações manuais: o heurístico utilizará sua regra padrão.</p>}
  </div>
}
