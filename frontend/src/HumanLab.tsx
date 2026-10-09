import { useEffect, useRef, useState } from 'react'
import { api, post, timecode } from './api'
import RecordingPlayer from './RecordingPlayer'
import type { Metrics, Prediction, Probabilities, Video } from './types'

type Study = { id: string; video_id: string; mode: string; answered: number; config: { count: number; participant_id: string; model_id: string; participant_unseen_declared: boolean } }
type Human = { probabilities: Probabilities | null; abstain: boolean; hash: string; submitted_at: string }
export type DuelRow = { round_index: number; timestamp: number; horizon: number; label: string | null; reason: string; context_hash: string; human: Human; ai: Prediction }
type HumanMetrics = Metrics & { samples: number; abstentions: number; abstention_rate: number; mean_decision_time_ms: number }
export type DuelReport = { study_id: string; report_id: number; revealed_at: string; mode: string; rows: DuelRow[]; human_metrics: HumanMetrics; ai_paired_metrics: Metrics; ai_all_metrics: Metrics; baseline_paired_metrics: Metrics | null; paired_evaluated: number; outcome_exclusions: number; limitations: string[] }
const labels: Record<string,string> = { ally_first:'Aliado primeiro', enemy_first:'Adversário primeiro', none:'Nenhuma eliminação' }
const number = (n: number | null | undefined) => n == null ? '—' : n.toFixed(3)

export function DuelOverlay({ row, time, mode, outcomeRow }: { row: DuelRow; time: number; mode: string; outcomeRow?: DuelRow }) {
  const probabilities = (p: Probabilities | null) => p ? Object.entries(p).map(([c,v]) => <p key={c}>{labels[c]} <b>{(v*100).toFixed(1)}%</b></p>) : <p>Abstenção registrada</p>
  const resolved = outcomeRow || (time >= row.timestamp+row.horizon ? row : null)
  return <div className="duel-overlay"><p className="eyebrow">{mode === 'technical_demo' ? 'DEMONSTRAÇÃO SINTÉTICA' : 'BASELINES NÃO VALIDADOS'} · PREVISÕES REGISTRADAS EM T = {row.timestamp}s · +{row.horizon}s</p>
    <div className="duel-columns"><article><h3>Human</h3>{probabilities(row.human.probabilities)}</article><article><h3>Anya</h3>{probabilities(row.ai.probabilities)}</article></div>
    <p className="duel-result">{resolved && time >= resolved.timestamp+resolved.horizon ? `Resultado anotado posterior: ${resolved.label ? labels[resolved.label] : resolved.reason} · previsão em ${resolved.timestamp}s` : `Resultado será revelado no replay em ${timecode(row.timestamp+row.horizon)}`}</p>
  </div>
}

export default function HumanLab({ videos }: { videos: Video[] }) {
  const eligible = videos.filter(v => ['test','validation'].includes(v.split))
  const [videoId, setVideoId] = useState(eligible[0]?.id || '')
  const [participant, setParticipant] = useState(() => crypto.randomUUID().replaceAll('-',''))
  const [model, setModel] = useState('heuristic-v1')
  const [training, setTraining] = useState<string[]>([])
  const [start, setStart] = useState(0)
  const [step, setStep] = useState(15)
  const [count, setCount] = useState(2)
  const [unseen, setUnseen] = useState(false)
  const [studies, setStudies] = useState<Study[]>([])
  const [studyId, setStudyId] = useState('')
  const [report, setReport] = useState<DuelReport | null>(null)
  const [reports, setReports] = useState<{ report_id: number; revealed_at: string }[]>([])
  const [stale, setStale] = useState(false)
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [time, setTime] = useState(0)
  const player = useRef<HTMLVideoElement>(null)
  const study = studies.find(s => s.id === studyId)
  const selectedVideo = videos.find(v => v.id === videoId)
  const duelVideo = videos.find(v => v.id === study?.video_id)
  const row = report?.rows.filter(r => r.timestamp <= time).at(-1)
  const outcomeRow = report?.rows.filter(r => r.timestamp+r.horizon <= time).at(-1)
  const independent = videos.filter(v => v.split === 'train' && v.synthetic === selectedVideo?.synthetic && (v.source_match_id || v.id) !== (selectedVideo?.source_match_id || selectedVideo?.id))

  async function refresh() { setStudies(await api<Study[]>('/lab/studies')) }
  useEffect(() => { refresh().catch(e => setError(e.message)) }, [])
  useEffect(() => { if (!videoId && eligible.length) setVideoId(eligible[0].id) }, [videos, videoId])
  useEffect(() => {
    setInvite(''); setReport(null); setReports([]); setTime(0); setStale(false)
    if (!studyId) return
    let active = true
    Promise.all([api<DuelReport | null>(`/lab/studies/${studyId}/report`), api<typeof reports>(`/lab/studies/${studyId}/reports`), api<{stale:boolean}>(`/lab/studies/${studyId}/report-status`)])
      .then(([r,versions,status]) => { if (active) { setReport(r); setReports(versions); setStale(status.stale) } }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [studyId])
  async function action(work: () => Promise<void>) { setBusy(true); setError(''); try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Operação falhou') } finally { setBusy(false) } }
  async function create() {
    await action(async () => {
      const study = await post<Study>('/lab/studies', { video_id:videoId, participant_id:participant, model_id:model, training_match_ids:training, start, step, count, participant_unseen_declared:unseen })
      await refresh(); setStudyId(study.id)
    })
  }
  async function reveal() {
    await action(async () => {
      setReport(await post<DuelReport>(`/lab/studies/${studyId}/reveal`, {})); setStale(false)
      setReports(await api<typeof reports>(`/lab/studies/${studyId}/reports`)); await refresh()
    })
  }
  async function selectReport(id: number) { await action(async () => { setReport(await api<DuelReport>(`/lab/studies/${studyId}/report?report_id=${id}`)); setTime(0); if (player.current) player.current.currentTime=0 }) }

  return <>
    {error && <p className="error-banner" role="alert">{error}</p>}
    <div className="workspace-grid">
      <section className="panel lab-content"><h2>Preparar comparação cega</h2><p className="helper">Escolha uma gravação que o participante ainda não viu. Anote evidências e revise resultados na área Dataset antes de preparar. A coleta usa quadros congelados; o vídeo completo só aparece na revisão do pesquisador.</p>
        <label>Gravação elegível<select aria-label="Gravação elegível" value={videoId} disabled={busy} onChange={e => { setVideoId(e.target.value); setTraining([]) }}><option value="">Selecione</option>{eligible.map(v => <option key={v.id} value={v.id}>{v.name} · {v.split} · {v.synthetic ? 'sintética' : 'real'}</option>)}</select></label>
        <label>Identificador pseudônimo local<input value={participant} maxLength={32} disabled={busy} onChange={e => setParticipant(e.target.value)}/></label>
        <label>Modelo de Anya<select aria-label="Modelo de Anya" value={model} disabled={busy} onChange={e => setModel(e.target.value)}><option value="heuristic-v1">Heurístico · não validado</option><option value="historical-v1">Histórico · não validado</option></select></label>
        <fieldset><legend>Baseline estatístico: origens train independentes</legend>{independent.length ? independent.map(v => <label className="check" key={v.id}><input type="checkbox" checked={training.includes(v.id)} disabled={busy} onChange={e => setTraining(old => e.target.checked ? [...old,v.id] : old.filter(id => id!==v.id))}/>{v.name}</label>) : <p className="helper">Importe e revise outra origem train do mesmo modo real/sintético. Sem seleção, a comparação heurística informa baseline indisponível.</p>}</fieldset>
        <div className="lab-config"><label>Início (s)<input type="number" min="0" value={start} disabled={busy} onChange={e => setStart(Number(e.target.value))}/></label><label>Passo (s)<input type="number" min="1" max="60" value={step} disabled={busy} onChange={e => setStep(Number(e.target.value))}/></label><label>Rodadas<input type="number" min="1" max="50" value={count} disabled={busy} onChange={e => setCount(Number(e.target.value))}/></label></div>
        <label className="check"><input type="checkbox" checked={unseen} disabled={busy} onChange={e => setUnseen(e.target.checked)}/>Participante declara não ter visto esta gravação</label>
        <button className="primary" disabled={busy || !videoId || !/^[a-f0-9]{32}$/.test(participant) || (model==='historical-v1' && !training.length)} onClick={create}>{busy ? 'Processando…' : 'Preparar estudo e previsões'}</button>
      </section>
      <section className="panel lab-content"><h2>Coleta local</h2><label>Estudo<select aria-label="Estudo" value={studyId} disabled={busy} onChange={e => setStudyId(e.target.value)}><option value="">Selecione</option>{studies.map(s => <option key={s.id} value={s.id}>{s.id.slice(0,8)} · {s.answered}/{s.config.count} respostas</option>)}</select></label>
        <button className="secondary" disabled={busy} onClick={() => action(refresh)}>Atualizar coleta</button>
        {study && <><p>{study.answered} / {study.config.count} respostas bloqueadas</p><p className="helper">{study.config.participant_unseen_declared ? 'Gravação inédita: declarada, não verificada.' : 'Gravação inédita não declarada; trate como demonstração exploratória.'}</p>
          <button className="secondary full" disabled={busy || study.answered===study.config.count} onClick={() => action(async () => setInvite((await post<{url:string}>(`/lab/studies/${studyId}/invite`, {})).url))}>Gerar convite local</button>
          {invite && <label>Link do participante<input readOnly value={invite} onFocus={e => e.target.select()}/></label>}
          <p className="helper">Guarde o convite. Encerre Anya na porta 8000 com Ctrl+C e abra “Iniciar Avaliação Humana.cmd”. Cole o convite na porta 8001. Após a coleta, encerre o participante e abra “Iniciar Anya.cmd” para revelar.</p>
          <button className="primary full" disabled={busy || study.answered!==study.config.count} onClick={reveal}>Revelar comparação</button>
        </>}
      </section>
    </div>
    {report && <>
      <section className="panel lab-content"><div className="summary-heading"><div><h2>Comparação registrada</h2><span className="outline-badge">{report.mode==='technical_demo' ? 'DEMONSTRAÇÃO SINTÉTICA' : 'BASELINES NÃO VALIDADOS'} · {report.paired_evaluated} PARES AVALIADOS</span></div><div className="export-actions">{['json','csv','srt'].map(f => <a className="secondary" key={f} href={`/api/lab/studies/${studyId}/export/${f}?report_id=${report.report_id}`} download>{f.toUpperCase()}</a>)}</div></div>
        <label>Versão da comparação<select aria-label="Versão da comparação" value={report.report_id} disabled={busy} onChange={e => selectReport(Number(e.target.value))}>{reports.map(r => <option key={r.report_id} value={r.report_id}>Relatório #{r.report_id} · {new Date(r.revealed_at).toLocaleString()}</option>)}</select></label>
        {stale && <p className="notice-banner">As anotações mudaram após a última revelação. Revele novamente para criar outro relatório; versões anteriores permanecem preservadas.</p>}
        <div className="table-scroll"><table><thead><tr><th>Participante / modelo</th><th>N</th><th>Accuracy</th><th>Brier</th><th>Log Loss</th></tr></thead><tbody>{[['Human', report.human_metrics], ['Anya · mesmas janelas', report.ai_paired_metrics], ['Histórico · mesmas janelas', report.baseline_paired_metrics], ['Anya · todas as janelas', report.ai_all_metrics]].map(([name,m]) => { const metrics = m as Metrics | null; return <tr key={name as string}><td>{name as string}</td><td>{metrics?.evaluated ?? 'Indisponível'}</td><td>{number(metrics?.accuracy)}</td><td>{number(metrics?.brier_score)}</td><td>{number(metrics?.log_loss)}</td></tr> })}</tbody></table></div>
        <p className="helper">Abstenções humanas: {report.human_metrics.abstentions}/{report.human_metrics.samples} ({(report.human_metrics.abstention_rate*100).toFixed(1)}%). Latência média de Anya (pares): {number(report.ai_paired_metrics.mean_latency_ms)}ms. Tempo humano médio: {(report.human_metrics.mean_decision_time_ms/1000).toFixed(2)}s, incluindo pausas. Resultados excluídos por revisão insuficiente/ambiguidade: {report.outcome_exclusions}. Calibração: {report.human_metrics.calibration ? 'disponível abaixo' : 'amostra insuficiente (mínimo 30)'}. Amostras pequenas não demonstram superioridade.</p>
        {report.human_metrics.calibration && <table><thead><tr><th>Calibração humana · bin</th><th>N</th><th>Confiança</th><th>Accuracy</th></tr></thead><tbody>{report.human_metrics.calibration.map(b => <tr key={b.bin}><td>{b.bin}</td><td>{b.count}</td><td>{number(b.confidence)}</td><td>{number(b.accuracy)}</td></tr>)}</tbody></table>}
        <details><summary>Limites do protocolo & integridade</summary><p>Mesmo corte temporal, quadros e evidências. Humanos interpretam imagens; os baselines usam riscos manuais e estatísticas de pixels. Não são capacidades semânticas equivalentes. Identificador humano: {study?.config.participant_id}. Modelo: {study?.config.model_id}.</p>{report.limitations.map(l => <p key={l}>{l}</p>)}{report.rows.map(r => <p key={r.round_index}>T={r.timestamp}s · Human <code>{r.human.hash}</code> · Anya <code>{r.ai.hash}</code> · contexto <code>{r.context_hash}</code></p>)}</details>
      </section>
      {duelVideo && <section className="panel"><div className="panel-heading"><h2>Prediction Duel · revisão após coleta</h2><span className="eyebrow">{timecode(time)}</span></div><div className="video-stage"><RecordingPlayer video={duelVideo} playerRef={player} onTime={setTime}/></div><div className="lab-content">{row ? <DuelOverlay row={row} time={time} mode={report.mode} outcomeRow={outcomeRow}/> : <p>Aguardando o instante da primeira previsão registrada.</p>}<p className="helper">Overlays mostram respostas bloqueadas e separam o resultado anotado posterior. JSON/CSV/SRT mantêm timestamps e origem sintética/real para edição.</p></div></section>}
    </>}
  </>
}
