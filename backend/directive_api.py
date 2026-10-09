"""Additive Directive 002 endpoints. Existing predictions and APIs are preserved."""
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from pydantic import Field

from backend.contracts import StrictModel
from backend.intelligence import CalloutDecisionEngine, StrategicResearch
from backend.voice import AnyaVoiceService


class VoiceRequest(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    role: Literal['design', 'clone'] = 'clone'
    seed: int = Field(default=42, ge=0, le=2**32-1)
    language: Literal['English'] = 'English'


class Selection(StrictModel):
    identity_id: str = Field(pattern='^[a-f0-9]{32}$')


class CommsRequest(StrictModel):
    frequency: float = Field(default=10, ge=5, le=120)


class ReplayClock(StrictModel):
    timestamp: float = Field(ge=0)


class BehaviorRequest(StrictModel):
    profile_id: str = Field(pattern='^[a-f0-9]{32}$')
    timestamp: float = Field(ge=0)
    action: Literal['advance', 'retreat', 'hold', 'alternate_route']


class PlaybackEvent(StrictModel):
    state: Literal['started', 'completed', 'interrupted']


class Profile(StrictModel):
    name: Literal['research', 'replay_commentary', 'lightweight']


def install_directive(app, store, engine, voice_backend=None):
    voice = AnyaVoiceService(store.root, voice_backend)
    research = StrategicResearch(store)
    comms = CalloutDecisionEngine(research, voice)
    app.state.voice = voice
    app.state.research = research
    router = APIRouter(prefix='/api')

    @router.get('/voice/status')
    def voice_status():
        return {'backend': voice.backend.name, 'selected_identity': voice.selected(), 'active_job': voice.active, 'profile': voice.profile,
                'resources': voice.resources.status(), 'stable_languages': ['English'],
                'queue_length': voice.pending.qsize(), 'download_automatic': False}

    @router.post('/voice/profile')
    def profile(command: Profile):
        voice.profile = command.name
        return {'profile': voice.profile, 'unload_after_generation': voice.profile == 'lightweight'}

    @router.get('/voice/identities')
    def identities():
        return voice.identities()

    @router.post('/voice/select')
    def select(command: Selection):
        return voice.select(command.identity_id)

    @router.get('/voice/identities/{identity_id}/audio')
    def reference_audio(identity_id: str):
        voice.identity(identity_id)
        return FileResponse(voice._audio(identity_id), media_type='audio/wav')

    @router.post('/voice/jobs', status_code=202)
    def synthesize(command: VoiceRequest):
        return voice.submit(command.text, role=command.role, seed=command.seed)

    @router.get('/voice/jobs/{job_id}')
    def job(job_id: str):
        return voice.job(job_id)

    @router.post('/voice/jobs/{job_id}/cancel')
    def cancel(job_id: str):
        return voice.cancel(job_id)

    @router.post('/voice/jobs/{job_id}/repeat', status_code=202)
    def repeat(job_id: str):
        return voice.repeat(job_id)

    @router.post('/voice/jobs/{job_id}/playback')
    def playback(job_id: str, command: PlaybackEvent):
        return voice.playback(job_id, command.state)

    @router.get('/voice/jobs/{job_id}/audio')
    def job_audio(job_id: str):
        return FileResponse(voice.audio(job_id), media_type='audio/wav')

    @router.get('/voice/history')
    def history():
        return voice.history()

    @router.post('/voice/unload')
    def unload():
        voice.unload()
        return {'state': 'unloaded'}

    @router.post('/experiments/{experiment_id}/comms')
    def decide(experiment_id: str, command: CommsRequest):
        return comms.decide(experiment_id, command.frequency)

    @router.get('/experiments/{experiment_id}/comms')
    def calls(experiment_id: str):
        store.experiment(experiment_id)
        return research.records('calls', experiment_id)

    @router.post('/experiments/{experiment_id}/comms/clock')
    def advance(experiment_id: str, command: ReplayClock):
        exp = store.experiment(experiment_id)
        if command.timestamp > exp['frontier']:
            raise ValueError('Relógio não pode exceder o frontier autorizado do experimento')
        voice.advance(experiment_id, command.timestamp)
        return {'timestamp': command.timestamp}

    @router.post('/experiments/{experiment_id}/hypotheses')
    def hypotheses(experiment_id: str):
        return research.propose(experiment_id)

    @router.get('/experiments/{experiment_id}/hypotheses')
    def hypothesis_history(experiment_id: str):
        store.experiment(experiment_id)
        return {'hypotheses': research.records('hypotheses', experiment_id),
                'evaluations': research.records('hypothesis_results', experiment_id)}

    @router.post('/experiments/{experiment_id}/hypotheses/evaluate')
    def evaluate(experiment_id: str):
        return research.evaluate(experiment_id, engine.report(experiment_id))

    @router.post('/experiments/{experiment_id}/memory')
    def remember(experiment_id: str, command: BehaviorRequest):
        return research.remember(experiment_id, **command.model_dump())

    @router.get('/experiments/{experiment_id}/memory')
    def memory(experiment_id: str, scope: Literal['short_term', 'session', 'long_term'] = 'short_term', profile_id: str | None = None):
        return research.memory(experiment_id, scope, profile_id)

    @router.get('/experiments/{experiment_id}/director/{format}')
    def director(experiment_id: str, format: Literal['json', 'csv', 'srt']):
        from backend.director import export_calls
        body, media_type = export_calls(store, research, voice, experiment_id, format)
        return Response(body, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="anya-voice-{experiment_id}.{format}"'})

    app.include_router(router)
    return voice
