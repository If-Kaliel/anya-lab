import { createRef } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, test, vi } from 'vitest'
import PairedComparison from './PairedComparison'
import RecordingPlayer from './RecordingPlayer'
import ReportArchive from './ReportArchive'
import DatasetReadiness from './DatasetReadiness'
import type { Comparison, Report } from './types'

const metrics = { evaluated: 3, excluded: 0, accuracy: .5, brier_score: .3, log_loss: .4, mean_latency_ms: 1, unknown_rate: .5, confusion_matrix: [[0,0,0],[0,0,0],[0,0,0]], calibration: null }

test('requests a local compatible preview and switches the player only when ready', async () => {
  let ready = false
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    if (options?.method === 'POST') ready = true
    return { ok: true, json: async () => ({ state: ready ? 'ready' : 'missing' }) }
  })
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<RecordingPlayer video={{ id: 'mkv', name: 'clip.mkv', duration: 30, width: 640, height: 360, split: 'test', synthetic: true, requires_preview: true }} playerRef={createRef()} onTime={() => {}}/>)
  expect(screen.queryByLabelText('Player da gravação')).toBeNull()
  await user.click(await screen.findByRole('button', { name: 'Preparar reprodução compatível' }))
  await waitFor(() => expect(screen.getByLabelText('Player da gravação').getAttribute('src')).toBe('/api/videos/mkv/preview/media'))
  expect(fetch.mock.calls.some(([url, options]) => url === '/api/videos/mkv/preview' && options?.method === 'POST')).toBe(true)
  expect(fetch.mock.calls.some(([url]) => url.includes('/experiments/'))).toBe(false)
})

test('selects an archived report by id without substituting latest metrics', async () => {
  const current: Report = { report_id: 2, experiment_id: 'exp', revealed_at: '2026-10-09T12:00:00Z', mode: 'technical_demo', rows: [], metrics }
  const archived = { ...current, report_id: 1, metrics: { ...metrics, evaluated: 0, accuracy: null } }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/reports/1') ? archived : [{ id: 2, revealed_at: current.revealed_at, evaluated: 3, excluded: 0 }, { id: 1, revealed_at: current.revealed_at, evaluated: 0, excluded: 3 }] })))
  const selected = vi.fn()
  const user = userEvent.setup()
  render(<ReportArchive report={current} onSelected={selected}/>)
  await screen.findByRole('option', { name: /Arquivada/ })
  await user.selectOptions(screen.getByLabelText('Versão do relatório'), '1')
  await waitFor(() => expect(selected).toHaveBeenCalledWith(archived, true))
})

test('pairs reports from the same recording and sends exact experiment ids', async () => {
  const comparisons: Comparison[] = [{ ...metrics, experiment_id: 'experiment-a', model_id: 'heuristic-v1', match_id: 'one', mode: 'technical_demo' }, { ...metrics, experiment_id: 'experiment-b', model_id: 'historical-v1', match_id: 'one', mode: 'technical_demo' }, { ...metrics, experiment_id: 'experiment-c', model_id: 'heuristic-v1', match_id: 'other', mode: 'technical_demo' }]
  const fetch = vi.fn(async (_: string, options?: RequestInit) => {
    expect(JSON.parse(options?.body as string)).toEqual({ experiment_ids: ['experiment-a', 'experiment-b'] })
    return { ok: true, json: async () => ({ common_windows: 3, mode: 'technical_demo', results: comparisons.slice(0, 2).map(c => ({ experiment_id: c.experiment_id, model_id: c.model_id, metrics })) }) }
  })
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<PairedComparison comparisons={comparisons}/>)
  await user.selectOptions(screen.getByLabelText('Experimento A'), 'experiment-a')
  expect(screen.getByLabelText('Experimento B').textContent).not.toContain('experiment-c')
  await user.selectOptions(screen.getByLabelText('Experimento B'), 'experiment-b')
  await user.click(screen.getByRole('button', { name: 'Comparar nos mesmos instantes' }))
  expect((await screen.findByText(/3 instantes em comum/)).textContent).toContain('Demonstração sintética')
  expect(fetch).toHaveBeenCalledTimes(1)
})

test('shows annotation coverage without presenting it as model accuracy', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ total_windows: 4, eligible_windows: 1, observations: 0, excluded_reasons: { interval_not_reviewed: 3 } }) })))
  render(<DatasetReadiness videoId="video" annotations={{ observations: [], events: [], reviews: [] }}/>)
  expect((await screen.findByText('1 / 4 janelas avaliáveis')).textContent).toBeTruthy()
  expect(screen.getByText('Revisão incompleta: 3')).toBeTruthy()
  expect(screen.getByText(/Sem observações manuais/)).toBeTruthy()
})
