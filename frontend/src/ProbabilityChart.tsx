import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { timecode } from './api'
import type { Prediction } from './types'

export default function ProbabilityChart({ rows }: { rows: Prediction[] }) {
  return <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={rows.map(p => ({ timestamp: p.timestamp, ...p.probabilities }))}>
    <CartesianGrid stroke="#292e35" strokeDasharray="3 3"/>
    <XAxis dataKey="timestamp" tickFormatter={timecode} stroke="#99a6b3"/>
    <YAxis domain={[0, 1]} tickFormatter={v => `${v * 100}%`} stroke="#99a6b3"/>
    <Tooltip contentStyle={{ background: '#171b21', border: '1px solid #414a56' }} labelFormatter={v => `T + ${timecode(Number(v))}`} formatter={v => `${(Number(v) * 100).toFixed(1)}%`}/>
    <Area type="stepAfter" dataKey="ally_first" name="Aliado" stroke="#b7c7d9" fill="#b7c7d9" fillOpacity={0.05}/>
    <Area type="stepAfter" dataKey="enemy_first" name="Adversário" stroke="#728ea3" fill="#728ea3" fillOpacity={0.05}/>
    <Area type="stepAfter" dataKey="none" name="Nenhuma" stroke="#b2a49b" fill="#b2a49b" fillOpacity={0.05}/>
  </AreaChart></ResponsiveContainer></div>
}
