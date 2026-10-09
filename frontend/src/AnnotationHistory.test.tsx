import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import AnnotationHistory from './AnnotationHistory'
import type { AnnotationHistory as HistoryRecord } from './types'

const empty = { observations: [], events: [], reviews: [] }
let requests: { path: string; body: unknown }[]
let conflict: boolean
let history: HistoryRecord
beforeEach(() => {
  requests = []; conflict = false
  history = { kind: 'events', id: 7, current_revision: 0, retracted: false, valid: true,
    entries: [{ revision: 0, annotation: { timestamp: 8, team: 'ally', reliable: true, note: 'Kill feed' }, retracted: false,
      reason: 'Registro original', recorded_at: '2026-10-09T12:00:00Z', hash: 'original-hash' }] }
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    requests.push({ path: url, body: options?.body ? JSON.parse(String(options.body)) : null })
    if (options?.method === 'POST') return conflict
      ? { ok: false, json: async () => ({ detail: 'A anotação mudou em outra operação. Atualize o histórico.' }) }
      : { ok: true, json: async () => ({ revision: 1 }) }
    return { ok: true, json: async () => [history] }
  }))
})

test('edits an outcome with a reason and expected revision, without sending observations', async () => {
  const user = userEvent.setup(), changed = vi.fn(async () => {})
  render(<AnnotationHistory videoId="match" annotations={empty} onChanged={changed}/>)
  await user.click(await screen.findByRole('button', { name: 'Corrigir Eliminação #7' }))
  await user.selectOptions(screen.getByRole('combobox', { name: 'Equipe corrigida' }), 'enemy')
  expect((screen.getByRole('button', { name: 'Salvar correção' }) as HTMLButtonElement).disabled).toBe(true)
  await user.type(screen.getByRole('textbox', { name: 'Motivo da alteração' }), '  HUD confirma equipe adversária  ')
  await user.click(screen.getByRole('button', { name: 'Salvar correção' }))
  await waitFor(() => expect(changed).toHaveBeenCalledWith('events'))
  const request = requests.find(r => r.path.endsWith('/revise'))!
  expect(request.path).toBe('/api/videos/match/annotations/events/7/revise')
  expect(request.body).toEqual({ expected_revision: 0, reason: 'HUD confirma equipe adversária', annotation: { timestamp: 8, team: 'enemy', reliable: true, note: 'Kill feed' } })
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('restores a retracted record by copying its previous version', async () => {
  history.retracted = true; history.current_revision = 1
  history.entries.push({ ...history.entries[0], revision: 1, retracted: true, reason: 'Retirada por engano', hash: 'revision-hash' })
  const user = userEvent.setup(), changed = vi.fn(async () => {})
  render(<AnnotationHistory videoId="match" annotations={empty} onChanged={changed}/>)
  await user.click(await screen.findByRole('button', { name: 'Restaurar Eliminação #7' }))
  await user.type(screen.getByRole('textbox', { name: 'Motivo da alteração' }), 'Restaurar evidência revisada')
  await user.click(screen.getByRole('button', { name: 'Confirmar restauração' }))
  await waitFor(() => expect(changed).toHaveBeenCalledWith('events'))
  expect(requests.find(r => r.path.endsWith('/restore'))?.body).toEqual({ expected_revision: 1, reason: 'Restaurar evidência revisada', target_revision: 0 })
})

test('a revision conflict preserves the draft and does not report success', async () => {
  conflict = true
  const user = userEvent.setup(), changed = vi.fn(async () => {})
  render(<AnnotationHistory videoId="match" annotations={empty} onChanged={changed}/>)
  await user.click(await screen.findByRole('button', { name: 'Corrigir Eliminação #7' }))
  await user.type(screen.getByRole('textbox', { name: 'Motivo da alteração' }), 'Minha revisão')
  await user.click(screen.getByRole('button', { name: 'Salvar correção' }))
  expect((await screen.findByRole('alert')).textContent).toContain('mudou em outra operação')
  expect((screen.getByRole('textbox', { name: 'Motivo da alteração' }) as HTMLInputElement).value).toBe('Minha revisão')
  expect(changed).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog')).toBeTruthy()
})

test('Escape closes the history and returns keyboard focus to its trigger', async () => {
  const user = userEvent.setup()
  render(<AnnotationHistory videoId="match" annotations={empty} onChanged={async () => {}}/>)
  const trigger = await screen.findByRole('button', { name: 'Histórico Eliminação #7' })
  await user.click(trigger)
  expect(screen.getByRole('dialog')).toBeTruthy()
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(trigger)
})
