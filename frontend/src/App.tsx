import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Activity, ArrowRight, Check, ChevronRight, CircleDot, Database, Download, Eye, FlaskConical, Focus, Layers, LockKeyhole, Play, Plus, ShieldCheck, Square, Upload, X } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, post, timecode } from './api'
import type { Annotations, Comparison, Experiment, Prediction, Report, Video } from './types'

type Page = 'replay' | 'dataset' | 'models' | 'summary'
const labels = { ally_first: 'Aliado primeiro', enemy_first: 'Adversário primeiro', none: 'Nenhuma eliminação' }
const emptyAnnotations: Annotations = { observations: [], events: [], reviews: [] }
const percent = (n: number | null | undefined) => n == null ? '—' : `${(n * 100).toFixed(1)}%`

function Panel({ title, tag, children, className = '' }: { title: string; tag?: string; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><h2>{title}</h2>{tag && <span className="eyebrow">{tag}</span>}</div>{children}</section>
}

export default function App() {
  const [page, setPage] = useState<Page>('replay')
  const [videos, setVideos] = useState<Video[]>([])
  const [videoId, setVideoId] = useState('')
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [experiment, setExperiment] = useState<Experiment | null>(null)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [comparison, setComparison] = useState<Comparison[]>([])
  const [models, setModels] = useState<{ id: string; name: string; description: string; status: string }[]>([])
  const [annotations, setAnnotations] = useState<Annotations>(emptyAnnotations)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const [modelId, setModelId] = useState('heuristic-v1')
  const [trainingIds, setTrainingIds] = useState<string[]>([])
  const [split, setSplit] = useState('test')
  const [synthetic, setSynthetic] = useState(false)
  const [time, setTime] = useState(0)
  const [obsKind, setObsKind] = useState('ally_risk')
  const [value, setValue] = useState(0.5)
  const [confidence, setConfidence] = useState(0.8)
  const [team, setTeam] = useState('ally')
  const [reliable, setReliable] = useState(true)
  const [reviewStart, setReviewStart] = useState(0)
  const [reviewEnd, setReviewEnd] = useState(15)
  const [note, setNote] = useState('')
  const player = useRef<HTMLVideoElement>(null)
  const stop = useRef(false)
  const video = videos.find(v => v.id === videoId)
  const last = predictions.at(-1)
  const next = experiment ? experiment.config.start + predictions.length * experiment.config.step : 0
  const complete = !!(video && experiment && next + 15 > video.duration)

  useEffect(() => {
    Promise.all([api<Video[]>('/videos'), api<Experiment[]>('/experiments'), api<typeof models>('/models'), api<Comparison[]>('/comparison')])
      .then(([v, e, m, c]) => { setVideos(v); setExperiments(e); setModels(m); setComparison(c); if (v.length) setVideoId(v[0].id) })
      .catch(e => setError(e.message))
  }, [])

  useEffect(() => {
    if (!videoId) { setAnnotations(emptyAnnotations); return }
    let active = true
    api<Annotations>(`/videos/${videoId}/annotations`).then(a => { if (active) setAnnotations(a) }).catch(e => setError(e.message))
    return () => { active = false }
  }, [videoId])

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await work() } catch (e) { setError(e instanceof Error ? e.message : 'Operação falhou') } finally { setBusy(false) }
  }
  function selectVideo(id: string) {
    stop.current = true; setVideoId(id); setExperiment(null); setPredictions([]); setReport(null); setTime(0)
  }
  async function upload(file: File) {
    await action(async () => {
      const data = new FormData(); data.append('file', file); data.append('split', split); data.append('synthetic', String(synthetic))
      const v = await api<Video>('/videos', { method: 'POST', body: data })
      setVideos(old => [v, ...old]); selectVideo(v.id); setImportOpen(false); setNotice('Gravação validada e armazenada localmente.')
    })
  }
  async function createExperiment() {
    await action(async () => {
      const e = await post<Experiment>('/experiments', { video_id: videoId, model_id: modelId, training_match_ids: modelId === 'historical-v1' ? trainingIds : [], start: 0, step: 5, horizon: 15, seed: 42 })
      setExperiment(e); setExperiments(old => [e, ...old]); setPredictions([]); setReport(null)
      setNotice('Experimento criado. Observações manuais congeladas; resultados isolados da inferência.')
    })
  }
  async function resumeExperiment(id: string) {
    const selected = experiments.find(e => e.id === id)
    if (!selected) return
    await action(async () => {
      const [p, r] = await Promise.all([api<Prediction[]>(`/experiments/${id}/predictions`), api<Report | null>(`/experiments/${id}/report`)])
      setVideoId(selected.config.video_id); setExperiment(selected); setPredictions(p); setReport(r)
    })
  }
  async function predict(all = false) {
    if (!experiment || !video) return
    const activeExperiment = experiment
    await action(async () => {
      stop.current = false
      let cursor = next
      do {
        const p = await post<Prediction>(`/experiments/${activeExperiment.id}/step`, { timestamp: cursor })
        setPredictions(old => [...old, p]); setExperiment(e => e ? { ...e, frontier: p.timestamp } : e)
        cursor += activeExperiment.config.step
      } while (all && !stop.current && cursor + 15 <= video.duration)
      setNotice('Previsão registrada com integridade verificável.')
    })
  }
  async function reveal() {
    if (!experiment) return
    await action(async () => {
      setReport(await post<Report>(`/experiments/${experiment.id}/reveal`, {}))
      setComparison(await api<Comparison[]>('/comparison')); setPage('summary')
    })
  }
  async function annotate(type: 'observations' | 'events' | 'reviews') {
    if (!video) return
    await action(async () => {
      const payload = type === 'observations' ? { timestamp: time, kind: obsKind, value, confidence, note }
        : type === 'events' ? { timestamp: time, team, reliable, note }
          : { start: reviewStart, end: reviewEnd, reliable, note }
      await post(`/videos/${video.id}/${type}`, payload)
      setAnnotations(await api<Annotations>(`/videos/${video.id}/annotations`))
      setNotice(type === 'observations' ? 'Observação salva. Entre em um novo experimento para usar essa versão.' : 'Anotação de avaliação salva. Ela nunca entra na inferência.')
    })
  }
  const nav = [
    ['replay', Focus, 'Replay Workspace', '01'], ['dataset', Database, 'Dataset & anotações', '02'],
    ['models', Layers, 'Modelos & comparação', '03'], ['summary', Activity, 'Research Summary', '04'],
  ] as const

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={e => { e.preventDefault(); setPage('replay') }}><img src="/emblem.svg" alt="Emblema Anya"/><div><strong>ANYA</strong><span>RESEARCH LABORATORY</span></div></a>
      <div className="sidebar-rule"/><p className="eyebrow sidebar-label">ORACLE PROTOTYPE / PHASE 01</p>
      <nav aria-label="Áreas do laboratório">{nav.map(([id, Icon, title, number]) => <button key={id} aria-label={title} title={title} className={page === id ? 'nav-item active' : 'nav-item'} onClick={() => setPage(id)}><Icon size={18}/><span>{title}</span><small>{number}</small></button>)}</nav>
      <div className="sidebar-bottom"><div className="local-status"><span className="status-dot"/> Ambiente local</div><p>Seus vídeos e experimentos permanecem neste computador.</p><div className="version"><span>ANYA v0.1.0</span><LockKeyhole size={13}/></div></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div><span className="muted">Laboratório</span><ChevronRight size={13}/><span>{nav.find(n => n[0] === page)?.[2]}</span></div><span className="top-badge"><FlaskConical size={13}/> PESQUISA EXPERIMENTAL</span></header>
      <main>
        {error && <div className="alert error" role="alert"><span>{error}</span><button aria-label="Fechar erro" onClick={() => setError('')}><X size={16}/></button></div>}
        {notice && <div className="alert notice" role="status"><Check size={16}/>{notice}</div>}
        <section className={`hero ${page !== 'replay' ? 'compact' : ''}`}>
          <div className="hero-copy"><p className="eyebrow"><span className="tiny-cross">✦</span> COMPETITIVE INTELLIGENCE RESEARCH LAB</p><h1>{page === 'replay' ? <>Observar. Antecipar.<br/><em>Compreender.</em></> : page === 'dataset' ? <>Evidências antes de <em>certezas.</em></> : page === 'models' ? <>Hipóteses sob <em>comparação.</em></> : <>Inteligência que pode ser <em>medida.</em></>}</h1><p>{page === 'replay' ? 'Um laboratório para investigar decisões em jogos competitivos. Cada previsão registrada. Cada hipótese questionável.' : 'Dados verificáveis, controle temporal e resultados reproduzíveis.'}</p>{page === 'replay' && <button className="primary" onClick={() => setImportOpen(true)}><Plus size={16}/> Importar gravação <ArrowRight size={16}/></button>}</div>
          <div className="hero-caption"><span>ANYA / THE ORACLE</span><small>MARVEL RIVALS · PRIMEIRO ESTUDO</small></div>
        </section>
        <div className="section-title"><div><p className="eyebrow">{page === 'replay' ? 'BLIND REPLAY MODE' : page === 'dataset' ? 'DATASET WORKSPACE' : page === 'models' ? 'MODEL REGISTRY' : 'EVALUATION ENGINE'}</p><h2>{page === 'replay' ? 'O próximo evento começa no presente.' : page === 'dataset' ? 'Anotação sincronizada com a gravação' : page === 'models' ? 'Baselines e evidências' : 'Resultados do experimento'}</h2></div><span className="outline-badge">{video?.synthetic ? 'DEMONSTRAÇÃO SINTÉTICA' : 'BASELINES NÃO VALIDADOS'}</span></div>

        {(page === 'replay' || page === 'dataset') && <div className="workspace-grid">
          <div>
            <Panel title={page === 'replay' ? 'Replay Workspace' : 'Gravação & timestamps'} tag={video ? timecode(video.duration) : 'SEM GRAVAÇÃO'}>
              <div className="video-stage">
                {video ? page === 'replay' && experiment ? last ? <><img className="inference-frame" src={`/api/experiments/${experiment.id}/frame?timestamp=${last.timestamp}`} alt={`Quadro autorizado até ${timecode(last.timestamp)}`}/><div className="frame-label"><LockKeyhole size={12}/> Contexto fechado em {last.timestamp.toFixed(3)}s</div></> : <div className="empty-stage"><img src="/emblem.svg" alt=""/><h3>Contexto temporal protegido</h3><p>Registre a primeira previsão para revelar o quadro autorizado.</p></div>
                  : <video key={video.id} ref={player} controls preload="metadata" src={`/api/videos/${video.id}/media`} onTimeUpdate={e => setTime(e.currentTarget.currentTime)} aria-label="Player da gravação"/>
                  : <div className="empty-stage"><img src="/emblem.svg" alt=""/><h3>A observação começa aqui</h3><p>Importe sua gravação em MP4 ou MKV.<br/>Nenhum dado é enviado a serviços externos.</p><button className="secondary" onClick={() => setImportOpen(true)}><Upload size={14}/> Selecionar arquivo</button></div>}
              </div>
              <div className="player-footer"><span><CircleDot size={14}/>{video?.name || 'Aguardando gravação'}</span><span>{video ? `${video.width} × ${video.height} / ${video.split}` : 'MP4 · MKV / ATÉ 2 GB'}</span></div>
              {video && !experiment && <p className="helper">MKV e alguns codecs podem não tocar no navegador. Prefira MP4 H.264. A extração do backend usa FFmpeg.</p>}
            </Panel>
            {page === 'replay' && <Panel title="Prediction Timeline" tag={`${predictions.length} REGISTROS`} className="timeline-panel">
              {predictions.length ? <><div className="timeline-track">{predictions.map(p => <button key={p.id} title={`Previsão em ${p.timestamp}s`} onClick={() => document.getElementById(`prediction-${p.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })} style={{ left: `${video ? p.timestamp / video.duration * 100 : 0}%` }}><span/>{timecode(p.timestamp)}</button>)}</div><div className="prediction-list">{predictions.map(p => <article className="prediction-card" id={`prediction-${p.id}`} key={p.id}><div className="prediction-head"><strong>T + {timecode(p.timestamp)}</strong><span>HORIZONTE +15s</span><ShieldCheck size={15}/></div><div className="probability-bars">{Object.entries(p.probabilities).map(([key, v]) => <div key={key}><span>{labels[key as keyof typeof labels]}</span><div className={`bar ${key}`}><i style={{ width: `${v * 100}%` }}/></div><b>{percent(v)}</b></div>)}</div><details><summary>Evidências & integridade</summary><p>{p.explanation}</p><p>Quadro: {p.frame_timestamp.toFixed(3)}s · Latência: {p.latency_ms.toFixed(1)}ms · Desconhecidas: {percent(p.unknown_rate)}</p><code>{p.hash}</code></details></article>)}</div></>
                : <div className="empty-inline"><Activity size={24}/><p>As previsões aparecerão aqui, antes da revelação dos resultados.</p></div>}
            </Panel>}
            {page === 'dataset' && <Panel title="Registros do dataset" tag="SCHEMA 1.0"><div className="annotation-list">{annotations.observations.map((o, i) => <div key={`o${i}`}><span className="outline-badge">OBSERVAÇÃO</span><b>{o.timestamp.toFixed(3)}s</b><span>{o.kind} · {o.value.toFixed(2)} / confiança {percent(o.confidence)}</span></div>)}{annotations.events.map((e, i) => <div key={`e${i}`}><span className="outline-badge">RESULTADO</span><b>{e.timestamp.toFixed(3)}s</b><span>{e.team} · {e.reliable ? 'confiável' : 'incerto'}</span></div>)}{annotations.reviews.map((r, i) => <div key={`r${i}`}><span className="outline-badge">REVISÃO</span><b>{r.start}s → {r.end}s</b><span>{r.reliable ? 'intervalo confiável' : 'intervalo incerto'}</span></div>)}{!Object.values(annotations).some(a => a.length) && <p className="helper">Nenhuma anotação registrada.</p>}</div>{video && <a className="text-link" href={`/api/videos/${video.id}/dataset`} download="anya-dataset.json"><Download size={14}/> Exportar dataset JSON</a>}</Panel>}
          </div>
          <div className="control-column">
            <Panel title="Experiment Control" tag="LOCAL"><label>Gravação<select aria-label="Gravação" disabled={busy} value={videoId} onChange={e => selectVideo(e.target.value)}><option value="">Selecione uma gravação</option>{videos.map(v => <option key={v.id} value={v.id}>{v.name} ({v.split})</option>)}</select></label>
              {page === 'replay' && <><label>Modelo de previsão<select aria-label="Modelo de previsão" value={modelId} onChange={e => setModelId(e.target.value)} disabled={busy}><option value="heuristic-v1">Baseline B · Heurístico</option><option value="historical-v1">Baseline A · Histórico</option></select></label>
                {modelId === 'historical-v1' && <fieldset><legend>Partidas de treinamento</legend>{videos.filter(v => v.split === 'train' && v.id !== videoId).map(v => <label className="check" key={v.id}><input type="checkbox" checked={trainingIds.includes(v.id)} onChange={e => setTrainingIds(ids => e.target.checked ? [...ids, v.id] : ids.filter(id => id !== v.id))}/>{v.name}</label>)}{!videos.some(v => v.split === 'train') && <p className="helper">Importe e revise outra gravação com split train.</p>}</fieldset>}
                <div className="config-grid"><div><span>CADÊNCIA</span><strong>05<small>s</small></strong></div><div><span>HORIZONTE</span><strong>15<small>s</small></strong></div></div>
                <button className="secondary full" disabled={!video || busy} onClick={createExperiment}><FlaskConical size={15}/> Criar experimento</button>
                {experiments.filter(e => e.config.video_id === videoId).length > 0 && <label>Experimentos salvos<select aria-label="Experimentos salvos" disabled={busy} value={experiment?.id || ''} onChange={e => resumeExperiment(e.target.value)}><option value="">Retomar um experimento</option>{experiments.filter(e => e.config.video_id === videoId).map(e => <option key={e.id} value={e.id}>{e.id.slice(0, 8)} · {e.config.model_id}</option>)}</select></label>}
                {experiment && <div className="run-controls"><p className="helper">{complete ? 'Todos os instantes com horizonte completo foram processados.' : `Próximo instante: ${next.toFixed(1)}s`}</p><button className="primary full" disabled={busy || complete} onClick={() => predict()}><Play size={15}/> Registrar previsão</button><button className="secondary full" disabled={busy || complete} onClick={() => predict(true)}>Executar sequência</button>{busy && <button className="text-link" onClick={() => { stop.current = true }}><Square size={13}/> Parar após previsão atual</button>}<button className="secondary full" disabled={busy || !predictions.length} onClick={reveal}><Eye size={15}/> Revelar & avaliar</button><button className="text-link" disabled={busy} onClick={() => setPage('dataset')}>Anotar resultados <ArrowRight size={13}/></button></div>}
              </>}
            </Panel>
            {page === 'replay' && <div className="protocol-card"><LockKeyhole size={20}/><p className="eyebrow">PROTOCOLO CEGO</p><h3>O futuro fica do lado de fora.</h3><p>Modelos recebem somente observações até T. Anotações de resultados pertencem à avaliação.</p><ul><li><Check size={13}/> Snapshot temporal congelado</li><li><Check size={13}/> Previsões append-only</li><li><Check size={13}/> Cadeia de integridade SHA-256</li></ul></div>}
            {page === 'dataset' && <Panel title="Anotar evidências" tag={`${time.toFixed(3)}s`}><label>Timestamp (segundos)<input aria-label="Timestamp" type="number" min="0" max={video?.duration} step="0.001" value={time} onChange={e => { const t = Number(e.target.value); setTime(t); if (player.current) player.current.currentTime = t }}/></label><label>Nota de anotação<input value={note} maxLength={500} onChange={e => setNote(e.target.value)} placeholder="Evidência visível e perspectiva da equipe"/></label><div className="form-divider"/><p className="eyebrow">OBSERVAÇÃO PARA INFERÊNCIA</p><label>Tipo<select value={obsKind} onChange={e => setObsKind(e.target.value)}><option value="ally_risk">Risco de eliminação aliada</option><option value="enemy_risk">Risco de eliminação adversária</option><option value="visibility">Visibilidade</option></select></label><label>Valor: {value.toFixed(2)}<input type="range" min="0" max="1" step="0.05" value={value} onChange={e => setValue(Number(e.target.value))}/></label><label>Confiança: {percent(confidence)}<input type="range" min="0" max="1" step="0.05" value={confidence} onChange={e => setConfidence(Number(e.target.value))}/></label><button className="secondary full" disabled={busy || !video} onClick={() => annotate('observations')}>Salvar observação</button><p className="helper">Use apenas informações visíveis neste instante. Novas observações entram em novos experimentos.</p><div className="form-divider"/><p className="eyebrow">RESULTADO ISOLADO DA INFERÊNCIA</p><label>Equipe eliminada<select aria-label="Equipe eliminada" value={team} onChange={e => setTeam(e.target.value)}><option value="ally">Aliada (perspectiva do jogador)</option><option value="enemy">Adversária</option><option value="unknown">Desconhecida</option></select></label><label className="check"><input type="checkbox" checked={reliable} onChange={e => setReliable(e.target.checked)}/>Anotação confiável</label><button className="secondary full" disabled={busy || !video} onClick={() => annotate('events')}>Registrar eliminação</button><div className="form-divider"/><label>Intervalo revisado — início<input aria-label="Intervalo revisado início" type="number" min="0" step="0.001" value={reviewStart} onChange={e => setReviewStart(Number(e.target.value))}/></label><label>Intervalo revisado — fim<input aria-label="Intervalo revisado fim" type="number" min="0" step="0.001" value={reviewEnd} onChange={e => setReviewEnd(Number(e.target.value))}/></label><button className="secondary full" disabled={busy || !video} onClick={() => annotate('reviews')}>Confirmar revisão do intervalo</button><p className="helper">Revise todo o intervalo e anote todas as eliminações visíveis. Uma janela sem revisão completa será excluída das métricas.</p></Panel>}
          </div>
        </div>}

        {page === 'models' && <><div className="model-grid">{models.map((m, i) => <article className="model-card" key={m.id}><span className="model-number">0{i + 1}</span><Layers size={23}/><h3>{m.name}</h3><p>{m.description}</p><span className="outline-badge">{m.id === 'supervised' ? 'INTERFACE DE TREINAMENTO OFFLINE' : 'BASELINE FUNCIONAL · NÃO VALIDADO'}</span></article>)}</div><Panel title="Comparação de experimentos" tag={`${comparison.length} RELATÓRIOS`}><p className="helper">Compare modelos na mesma partida e nos mesmos instantes. Os relatórios abaixo não demonstram superioridade científica.</p><div className="table-scroll"><table><thead><tr><th>Experimento / partida</th><th>Modelo</th><th>N avaliadas</th><th>Accuracy</th><th>Brier</th><th>Log loss</th></tr></thead><tbody>{comparison.map(c => <tr key={c.experiment_id}><td>{c.experiment_id.slice(0, 8)} / {c.match_id.slice(0, 8)}<small>{c.mode === 'technical_demo' ? 'DEMONSTRAÇÃO SINTÉTICA' : 'BASELINE NÃO VALIDADO'}</small></td><td>{c.model_id}</td><td>{c.evaluated}</td><td>{percent(c.accuracy)}</td><td>{c.brier_score?.toFixed(3) ?? '—'}</td><td>{c.log_loss?.toFixed(3) ?? '—'}</td></tr>)}</tbody></table>{!comparison.length && <div className="empty-inline"><p>Revele os resultados de um experimento para iniciar a comparação.</p></div>}</div></Panel></>}

        {page === 'summary' && (report ? <><div className="summary-heading"><span className="helper">Experimento {report.experiment_id.slice(0, 8)} · Revelado em {new Date(report.revealed_at).toLocaleString('pt-BR')}</span><div className="export-actions">{['json', 'csv', 'srt'].map(format => <a key={format} className="secondary" href={`/api/experiments/${report.experiment_id}/export/${format}`} download><Download size={13}/>{format.toUpperCase()}</a>)}</div></div>{report.rows.length !== predictions.length && <p className="alert notice">Há novas previsões. Revele novamente para atualizar o relatório.</p>}<div className="metrics-grid">{[['Previsões avaliadas', String(report.metrics.evaluated)], ['Accuracy', percent(report.metrics.accuracy)], ['Brier score', report.metrics.brier_score?.toFixed(3) ?? '—'], ['Log loss', report.metrics.log_loss?.toFixed(3) ?? '—']].map(([name, v]) => <div className="metric-card" key={name}><p>{name}</p><strong>{v}</strong></div>)}</div><div className="summary-grid"><Panel title="Probabilidades ao longo do replay" tag="PREVISÕES REGISTRADAS"><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={report.rows.map(p => ({ timestamp: p.timestamp, ...p.probabilities }))}><CartesianGrid stroke="#292e35" strokeDasharray="3 3"/><XAxis dataKey="timestamp" tickFormatter={timecode} stroke="#99a6b3"/><YAxis domain={[0, 1]} tickFormatter={v => `${v * 100}%`} stroke="#99a6b3"/><Tooltip contentStyle={{ background: '#171b21', border: '1px solid #414a56' }} labelFormatter={v => `T + ${timecode(Number(v))}`}/><Area type="stepAfter" dataKey="ally_first" name="Aliado" stroke="#b7c7d9" fill="#b7c7d9" fillOpacity={0.05}/><Area type="stepAfter" dataKey="enemy_first" name="Adversário" stroke="#728ea3" fill="#728ea3" fillOpacity={0.05}/><Area type="stepAfter" dataKey="none" name="Nenhuma" stroke="#b2a49b" fill="#b2a49b" fillOpacity={0.05}/></AreaChart></ResponsiveContainer></div></Panel><Panel title="Matriz de confusão" tag="REAL × PREVISTO"><div className="table-scroll"><table className="matrix"><thead><tr><th>Real ↓ / Previsto →</th><th>Aliado</th><th>Adversário</th><th>Nenhuma</th></tr></thead><tbody>{report.metrics.confusion_matrix.map((row, i) => <tr key={i}><th>{['Aliado', 'Adversário', 'Nenhuma'][i]}</th>{row.map((n, j) => <td className={i === j ? 'diagonal' : ''} key={j}>{n}</td>)}</tr>)}</tbody></table></div><p className="helper">Excluídas: {report.metrics.excluded} · Latência média: {report.metrics.mean_latency_ms?.toFixed(1) ?? '—'}ms · Observações desconhecidas: {percent(report.metrics.unknown_rate)}</p><p className="helper">{report.metrics.calibration ? 'Calibração disponível abaixo (mínimo 30 amostras).' : 'Calibração requer ao menos 30 previsões avaliadas; esse limiar não garante validade científica.'}</p>{report.metrics.calibration && <table><thead><tr><th>N</th><th>Confiança</th><th>Accuracy</th></tr></thead><tbody>{report.metrics.calibration.map(b => <tr key={b.bin}><td>{b.count}</td><td>{percent(b.confidence)}</td><td>{percent(b.accuracy)}</td></tr>)}</tbody></table>}</Panel></div><Panel title="Relatório de acertos e erros" tag={report.mode === 'technical_demo' ? 'DEMONSTRAÇÃO SINTÉTICA' : 'BASELINE NÃO VALIDADO'}><div className="table-scroll"><table><thead><tr><th>Instante</th><th>Classe mais provável</th><th>Resultado observado</th><th>Avaliação</th></tr></thead><tbody>{report.rows.map(p => { const best = Object.entries(p.probabilities).sort((a, b) => b[1] - a[1])[0][0]; return <tr key={p.id}><td>{timecode(p.timestamp)}</td><td>{labels[best as keyof typeof labels]}</td><td>{p.label ? labels[p.label as keyof typeof labels] : 'Não confiável / não revisado'}</td><td>{p.label ? best === p.label ? 'Acerto' : 'Erro' : p.reason}</td></tr> })}</tbody></table></div></Panel></> : <Panel title="Sem relatório revelado"><div className="empty-inline"><FlaskConical size={25}/><p>Registre previsões, anote os resultados e revele a avaliação no Replay Workspace.</p><button className="secondary" onClick={() => setPage('replay')}>Abrir workspace <ArrowRight size={14}/></button></div></Panel>)}
        <footer className="main-footer"><span>ANYA / COMPETITIVE INTELLIGENCE RESEARCH LAB</span><span>OBSERVAÇÃO → PREVISÃO → EVIDÊNCIA</span></footer>
      </main>
    </div>
    {busy && <div className="processing" role="status"><span className="spinner"/> Processando operação local…</div>}
    {importOpen && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="import-title"><button className="modal-close" aria-label="Fechar importação" disabled={busy} onClick={() => setImportOpen(false)}><X size={19}/></button><Upload size={28}/><p className="eyebrow">VIDEO INGESTION</p><h2 id="import-title">Importar gravação</h2><p className="helper">Use gravações próprias ou com permissão. MP4 ou MKV, até 2 GB e 6 horas. A validação de timestamps pode levar alguns minutos.</p><label>Divisão do dataset<select aria-label="Divisão do dataset" value={split} onChange={e => setSplit(e.target.value)}><option value="test">Teste</option><option value="train">Treinamento</option><option value="validation">Validação</option></select></label><label className="check"><input type="checkbox" checked={synthetic} onChange={e => setSynthetic(e.target.checked)}/>Gravação sintética para demonstração técnica</label><label className="file-drop">{busy ? 'Validando gravação…' : 'Selecionar arquivo MP4 ou MKV'}<input aria-label="Arquivo de vídeo" type="file" accept=".mp4,.mkv" disabled={busy} onChange={e => { const file = e.target.files?.[0]; if (file) upload(file) }}/></label><p className="helper"><LockKeyhole size={12}/> Armazenamento local. GPU e APIs pagas não são necessárias.</p></section></div>}
  </div>
}
