import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import VoicePanel from './VoicePanel'
import StrategicPanel from './StrategicPanel'
import { api, post } from './api'

vi.mock('./api', () => ({ api: vi.fn(), post: vi.fn() }))
const reference = { id: 'a'.repeat(32), text: 'Original reference.', backend: 'qwen3-local', seed: 42, sha256: 'hash' }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === '/voice/status') return { selected_identity: null, backend: 'qwen3-local', active_job: null, profile: 'research', resources: { gpu: null } } as never
    if (path === '/voice/identities') return [reference] as never
    return [] as never
  })
  vi.mocked(post).mockResolvedValue({ id: 'b'.repeat(32), state: 'queued' } as never)
})

describe('voice controls', () => {
  it('does not select an identity automatically and submits real design jobs', async () => {
    render(<VoicePanel visible experiment={null}/>)
    await screen.findByText('Original reference.')
    expect(post).not.toHaveBeenCalled()
    expect((screen.getByRole('button', { name: 'Sintetizar com voz selecionada' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Texto para síntese'), { target: { value: 'A new original voice.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Gerar amostra original' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/voice/jobs', { text: 'A new original voice.', role: 'design', seed: 42, language: 'English' }))
    await waitFor(() => expect((screen.getByRole('button', { name: 'Selecionar identidade' }) as HTMLButtonElement).disabled).toBe(false))
    fireEvent.click(screen.getByRole('button', { name: 'Selecionar identidade' }))
    await waitFor(() => expect(post).toHaveBeenCalledWith('/voice/select', { identity_id: reference.id }))
  })
  it('shows unavailability and retains the original experiment', async () => {
    const exp = { id: 'e', frontier: 0, mode: 'technical_demo', config: { video_id: 'v', model_id: 'heuristic-v1', start: 0, step: 5, horizon: 15 } }
    vi.mocked(post).mockRejectedValue(new Error('Model unavailable'))
    render(<VoicePanel visible experiment={exp}/>)
    await screen.findByText('Original reference.')
    fireEvent.click(screen.getByRole('button', { name: 'Gerar amostra original' }))
    expect((await screen.findByRole('alert')).textContent).toContain('Model unavailable')
    expect(exp.frontier).toBe(0)
    expect(post).not.toHaveBeenCalledWith('/experiments/e/step', expect.anything())
  })
})

it('strategic inspection uses registered hypotheses without fabricating probabilities', async () => {
  const exp = { id: 'e', frontier: 0, mode: 'technical_demo', config: { video_id: 'v', model_id: 'heuristic-v1', start: 0, step: 5, horizon: 15 } }
  vi.mocked(api).mockResolvedValue({ hypotheses: [{ id: 'h', timestamp: 0, type: 'abstention', description: 'Insufficient evidence.', probability: null, evidence: [], awareness: { unknown: ['hidden_enemy_positions'] }, model_id: 'risk-hypotheses-v1' }], evaluations: [] } as never)
  render(<StrategicPanel experiment={exp} revealed={false}/>)
  expect((screen.getByRole('button', { name: 'Avaliar após revelação' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Registrar / consultar hipóteses' }))
  expect(await screen.findByText('Insufficient evidence.')).toBeTruthy()
  expect(screen.getByText(/não calibrada \/ não atribuída/)).toBeTruthy()
  expect(post).toHaveBeenCalledWith('/experiments/e/hypotheses', {})
})
