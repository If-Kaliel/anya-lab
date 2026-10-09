import { lazy, Suspense, useEffect, useState } from 'react'
import ParticipantPage from './ParticipantPage'

const App = lazy(() => import('./App'))
export default function Entry() {
  const [mode, setMode] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    fetch('/api/health').then(async r => { if (!r.ok) throw new Error('Servidor indisponível'); return r.json() })
      .then(h => { if (active) { if (!['participant','research'].includes(h.mode)) throw new Error('Modo local desconhecido'); setMode(h.mode) } })
      .catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [])
  if (error) return <main><p role="alert">{error}</p></main>
  if (!mode) return <main><p role="status">Abrindo laboratório local…</p></main>
  return mode === 'participant' ? <ParticipantPage/> : <Suspense fallback={<main>Carregando laboratório…</main>}><App/></Suspense>
}
