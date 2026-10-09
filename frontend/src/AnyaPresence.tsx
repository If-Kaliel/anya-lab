export type PresenceState = 'dormant' | 'observing' | 'reasoning' | 'speaking' | 'uncertain' | 'reviewing'
const states = { dormant: 'Inativa', observing: 'Observando replay', reasoning: 'Processando operação', speaking: 'Reproduzindo voz', uncertain: 'Evidências insuficientes', reviewing: 'Revisando resultados' }

export default function AnyaPresence({ state }: { state: PresenceState }) {
  return <div className={`anya-presence ${state}`} role="status"><img src="/emblem.svg" alt=""/><div><span className="eyebrow">ANYA PRESENCE</span><p>{states[state]}</p></div></div>
}
