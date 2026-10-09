export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options)
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Servidor indisponível' }))
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Dados inválidos; verifique os campos')
  }
  return response.json()
}
export const post = <T,>(path: string, data: unknown) => api<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
export const timecode = (time: number) => `${Math.floor(time / 60).toString().padStart(2, '0')}:${Math.floor(time % 60).toString().padStart(2, '0')}`
