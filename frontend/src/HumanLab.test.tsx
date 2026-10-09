import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, test, vi } from 'vitest'
import ParticipantPage from './ParticipantPage'
import Entry from './Entry'
import HumanLab, { DuelOverlay } from './HumanLab'

const context = { state:'awaiting_prediction', round_index:0, timestamp:0, max_accessible_timestamp:0, horizon:15, total_rounds:1, context_hash:'a'.repeat(64), frames:[{timestamp:0,sha256:'b'.repeat(64)}], observations:[], mode:'technical_demo' }
beforeEach(() => {
  location.hash = `trial=${'c'.repeat(64)}`
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL:vi.fn(()=>'blob:authorized'), revokeObjectURL:vi.fn() }))
})

test('participant submits exact context and reveals no original media or AI results', async () => {
  let sealed = false
  const fetch = vi.fn(async (url: string, options?: RequestInit) => {
    expect(options?.headers).toHaveProperty('Authorization', `Bearer ${'c'.repeat(64)}`)
    if (url.endsWith('/answer')) { sealed=true; return {ok:true,json:async()=>({state:'answer_locked'})} }
    if (url.includes('/frame?')) return {ok:true,blob:async()=>new Blob(['png'])}
    return {ok:true,json:async()=>sealed ? {state:'answers_locked',total_rounds:1,mode:'technical_demo'} : context}
  })
  vi.stubGlobal('fetch',fetch)
  const user = userEvent.setup()
  const {container} = render(<ParticipantPage/>)
  await waitFor(()=>expect(screen.getByRole('button',{name:'Bloquear resposta'})).toHaveProperty('disabled', false))
  await user.click(screen.getByRole('button',{name:'Bloquear resposta'}))
  expect(await screen.findByText('Respostas bloqueadas')).toBeTruthy()
  const request = fetch.mock.calls.find(([url])=>url.endsWith('/answer'))!
  expect(JSON.parse(request[1]?.body as string)).toEqual({round_index:0,context_hash:'a'.repeat(64),abstain:false,probabilities:{ally_first:.33,enemy_first:.33,none:.34}})
  expect(fetch.mock.calls.every(([url])=>url.startsWith('/api/participant/'))).toBe(true)
  expect(container.querySelector('video')).toBeNull()
  expect(container.textContent).not.toContain('Resultado anotado')
})

test('blocks invalid probability total and supports explicit abstention', async () => {
  let body: unknown
  vi.stubGlobal('fetch',vi.fn(async (url:string,options?:RequestInit)=> {
    if (url.includes('/frame?')) return {ok:true,blob:async()=>new Blob(['png'])}
    if (url.endsWith('/answer')) body=JSON.parse(options?.body as string)
    return {ok:true,json:async()=>context}
  }))
  const user=userEvent.setup()
  render(<ParticipantPage/>)
  const input = await screen.findByLabelText('Aliado primeiro (%)')
  fireEvent.change(input,{target:{value:'80'}})
  expect(screen.getByRole('button',{name:'Bloquear resposta'})).toHaveProperty('disabled', true)
  await user.click(screen.getByLabelText('Abster-se de prever'))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Bloquear resposta'})).toHaveProperty('disabled', false))
  await user.click(screen.getByRole('button',{name:'Bloquear resposta'}))
  expect(body).toEqual({round_index:0,context_hash:'a'.repeat(64),abstain:true,probabilities:null})
})

test('entry in participant mode never mounts research or voice requests',async()=> {
  vi.stubGlobal('fetch',vi.fn(async (url:string)=> url.endsWith('/health') ? {ok:true,json:async()=>({mode:'participant'})} : {ok:true,json:async()=>({state:'answers_locked',total_rounds:1,mode:'technical_demo'})}))
  render(<Entry/>)
  expect(await screen.findByText('Respostas bloqueadas')).toBeTruthy()
  expect(screen.queryByRole('navigation')).toBeNull()
  const calls = vi.mocked(fetch).mock.calls.map(([url])=>String(url))
  expect(calls.every(url=>url==='/api/health' || url==='/api/participant/context')).toBe(true)
})

test('duel separates sealed predictions from post-horizon outcome',()=> {
  const row = {round_index:0,timestamp:5,horizon:15,label:'enemy_first',reason:'visible_first_event',context_hash:'hash',
    human:{abstain:false,hash:'hash',submitted_at:'date',probabilities:{ally_first:.1,enemy_first:.8,none:.1}},
    ai:{id:1,timestamp:5,frame_timestamp:5,horizon:15,probabilities:{ally_first:.2,enemy_first:.7,none:.1},observations:[],evidence:[],explanation:'',hash:'hash',unknown_rate:0,latency_ms:2}}
  const {rerender} = render(<DuelOverlay row={row} time={19.99} mode="technical_demo"/>)
  expect(screen.queryByText(/Resultado anotado posterior/)).toBeNull()
  expect(screen.getByText(/Resultado será revelado/)).toBeTruthy()
  rerender(<DuelOverlay row={row} time={20} mode="technical_demo"/>)
  expect(screen.getByText('Resultado anotado posterior: Adversário primeiro · previsão em 5s')).toBeTruthy()
  expect(screen.getByText(/DEMONSTRAÇÃO SINTÉTICA/)).toBeTruthy()
})


test('duel keeps the prior outcome visible when the next forecast starts',()=> {
  const previous = {round_index:0,timestamp:0,horizon:15,label:'ally_first',reason:'visible_first_event',context_hash:'hash',
    human:{abstain:true,hash:'hash',submitted_at:'date',probabilities:null},
    ai:{id:1,timestamp:0,frame_timestamp:0,horizon:15,probabilities:{ally_first:.25,enemy_first:.25,none:.5},observations:[],evidence:[],explanation:'',hash:'hash',unknown_rate:0,latency_ms:2}}
  const next = {...previous, round_index:1, timestamp:15, label:'enemy_first'}
  render(<DuelOverlay row={next} time={15} mode="technical_demo" outcomeRow={previous}/>)
  expect(screen.getByText('Resultado anotado posterior: Aliado primeiro · previsão em 0s')).toBeTruthy()
  expect(screen.queryByText(/Resultado anotado posterior: Adversário/)).toBeNull()
})


test('researcher reveal stays disabled until all human answers are sealed',async()=> {
  let answered = 0
  const study = {id:'study',video_id:'video',mode:'technical_demo',answered:0,config:{count:2,participant_id:'pseudonym',model_id:'heuristic-v1',participant_unseen_declared:false}}
  const requests = vi.fn(async (url:string) => ({ok:true,json:async()=> {
    if (url === '/api/lab/studies') return [{...study,answered}]
    if (url.endsWith('/reports')) return []
    if (url.endsWith('/report-status')) return {stale:false}
    return null
  }}))
  vi.stubGlobal('fetch',requests)
  const user = userEvent.setup()
  render(<HumanLab videos={[{id:'video',name:'demo.mp4',duration:30,width:640,height:360,split:'test',synthetic:true}]}/>)
  await screen.findByRole('option',{name:'study · 0/2 respostas'})
  await user.selectOptions(screen.getByLabelText('Estudo'),'study')
  expect(await screen.findByRole('button',{name:'Revelar comparação'})).toHaveProperty('disabled',true)
  answered=2
  await user.click(screen.getByRole('button',{name:'Atualizar coleta'}))
  await waitFor(()=>expect(screen.getByRole('button',{name:'Revelar comparação'})).toHaveProperty('disabled',false))
  expect(requests.mock.calls.some(([url])=>url.endsWith('/reveal'))).toBe(false)
})
