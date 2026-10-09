import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import App from './App'

vi.mock('./ProbabilityChart', () => ({ default: () => <div aria-label="Gráfico de probabilidades"/> }))

const video = { id: 'video-1', name: 'replay.mp4', duration: 30, width: 640, height: 360, split: 'test', synthetic: true }
let requests: { path: string; body?: unknown }[]
beforeEach(() => {
  requests = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    const path = url.replace('/api', '')
    const body = typeof options?.body === 'string' ? JSON.parse(options.body) : undefined
    requests.push({ path, body })
    let data: unknown = []
    if (path === '/videos') data = [video]
    if (path.endsWith('/annotations')) data = { observations: [], events: [], reviews: [] }
    if (path === '/experiments' && options?.method === 'POST') data = { id: 'exp-1', config: { video_id: video.id, model_id: 'heuristic-v1', start: 0, step: 5, horizon: 15 }, frontier: -1, mode: 'technical_demo' }
    if (path.endsWith('/step')) data = { id: 1, timestamp: 0, frame_timestamp: 0, horizon: 15, probabilities: { ally_first: .25, enemy_first: .25, none: .5 }, observations: [], evidence: [], explanation: 'Baseline não validado', hash: 'abc123', unknown_rate: 1, latency_ms: 2 }
    return { ok: true, json: async () => data }
  }))
})

test('creates experiment and records a genuine API prediction before showing probabilities', async () => {
  const user = userEvent.setup()
  render(<App/>)
  await screen.findByText('replay.mp4')
  expect(screen.queryByText('50.0%')).toBeNull()
  await user.click(screen.getByRole('button', { name: 'Criar experimento' }))
  await user.click(await screen.findByRole('button', { name: 'Registrar previsão' }))
  await screen.findByText('50.0%')
  expect(requests.find(r => r.path === '/experiments/exp-1/step')?.body).toEqual({ timestamp: 0 })
  expect(screen.getByAltText('Quadro autorizado até 00:00').getAttribute('src')).toContain('timestamp=0')
})

test('sends outcome annotations only to the evaluation events API', async () => {
  const user = userEvent.setup()
  render(<App/>)
  await screen.findByText('replay.mp4')
  await user.click(screen.getByRole('button', { name: /Dataset & anotações/ }))
  await user.clear(screen.getByRole('spinbutton', { name: 'Timestamp' }))
  await user.type(screen.getByRole('spinbutton', { name: 'Timestamp' }), '8')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Equipe eliminada' }), 'enemy')
  await user.click(screen.getByRole('button', { name: 'Registrar eliminação' }))
  await waitFor(() => expect(requests.some(r => r.path === '/videos/video-1/events')).toBe(true))
  expect(requests.find(r => r.path.endsWith('/events'))?.body).toMatchObject({ timestamp: 8, team: 'enemy', reliable: true })
  expect(requests.some(r => r.path.endsWith('/observations'))).toBe(false)
})

test('presents backend errors and does not show invented predictions', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({ detail: 'FFmpeg ausente' }) })))
  render(<App/>)
  expect((await screen.findByRole('alert')).textContent).toContain('FFmpeg ausente')
  expect(screen.queryByText('50.0%')).toBeNull()
})


test('records reviewed intervals in the reviews channel', async () => {
  const user = userEvent.setup()
  render(<App/>)
  await screen.findByText('replay.mp4')
  await user.click(screen.getByRole('button', { name: 'Dataset & anotações' }))
  await user.clear(screen.getByRole('spinbutton', { name: 'Intervalo revisado fim' }))
  await user.type(screen.getByRole('spinbutton', { name: 'Intervalo revisado fim' }), '30')
  await user.click(screen.getByRole('button', { name: 'Confirmar revisão do intervalo' }))
  await waitFor(() => expect(requests.some(r => r.path.endsWith('/reviews'))).toBe(true))
  expect(requests.find(r => r.path.endsWith('/reviews'))?.body).toEqual({ start: 0, end: 30, reliable: true, note: '' })
  expect(requests.some(r => r.path.endsWith('/events'))).toBe(false)
})


test('restoring an experiment marks an old report as stale after annotation revisions', async () => {
  const saved = { id: 'saved', config: { video_id: video.id, model_id: 'heuristic-v1', start: 0, step: 5, horizon: 15 }, frontier: 0, mode: 'technical_demo' }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    let data: unknown = []
    if (url === '/api/videos') data = [video]
    if (url === '/api/experiments') data = [saved]
    if (url.endsWith('/annotations')) data = { observations: [], events: [], reviews: [] }
    if (url.endsWith('/report-status')) data = { stale: true }
    if (url.endsWith('/report')) data = { experiment_id: 'saved', revealed_at: '2026-10-09T12:00:00Z', mode: 'technical_demo', rows: [],
      metrics: { evaluated: 0, excluded: 0, accuracy: null, brier_score: null, log_loss: null, mean_latency_ms: null, unknown_rate: null, confusion_matrix: [[0,0,0],[0,0,0],[0,0,0]], calibration: null } }
    return { ok: true, json: async () => data }
  }))
  const user = userEvent.setup()
  render(<App/>)
  await user.selectOptions(await screen.findByRole('combobox', { name: 'Experimentos salvos' }), 'saved')
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Experimentos salvos' }).getAttribute('disabled')).toBeNull())
  await user.click(screen.getByRole('button', { name: 'Research Summary' }))
  expect((await screen.findByRole('status')).textContent).toContain('anotações mudaram')
})
