import { useEffect, useState } from 'react'
import { api } from './api'
import type { Report } from './types'

type Version = { id: number; revealed_at: string; evaluated: number; excluded: number }

export default function ReportArchive({ report, onSelected }: { report: Report; onSelected: (report: Report, archived: boolean) => void }) {
  const [versions, setVersions] = useState<Version[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    let active = true
    api<Version[]>(`/experiments/${report.experiment_id}/reports?summary=true`).then(v => { if (active) setVersions(v) }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [report.experiment_id, report.report_id])
  async function select(id: number) {
    setLoading(true); setError('')
    try { onSelected(await api<Report>(`/experiments/${report.experiment_id}/reports/${id}`), id !== versions[0]?.id) }
    catch (e) { setError(e instanceof Error ? e.message : 'Não foi possível carregar o relatório') }
    finally { setLoading(false) }
  }
  return <div className="report-archive"><label>Versão do relatório<select aria-label="Versão do relatório" disabled={loading || !versions.length} value={report.report_id ?? ''} onChange={e => select(Number(e.target.value))}>
    {!versions.length && <option value="">Relatório atual</option>}
    {versions.map((v, i) => <option key={v.id} value={v.id}>{i === 0 ? 'Mais recente' : 'Arquivada'} · {new Date(v.revealed_at).toLocaleString('pt-BR')} · {v.evaluated} avaliadas / {v.excluded} excluídas</option>)}
  </select></label>{error && <p className="helper" role="alert">{error}</p>}</div>
}
