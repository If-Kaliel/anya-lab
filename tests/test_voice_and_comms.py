import json
import threading
import time

import pytest

from backend.contracts import ExperimentInput
from backend.experiments import ExperimentEngine
from backend.intelligence import CalloutDecisionEngine, StrategicResearch
from backend.voice import AnyaVoiceService, MockBackend


def completed(voice, item):
    for _ in range(200):
        job = voice.job(item['id'])
        if job['state'] not in {'queued', 'synthesizing'}:
            return job
        time.sleep(.01)
    raise AssertionError('Voice job did not finish')


def identity(voice):
    job = completed(voice, voice.submit('Original test reference.', role='design'))
    assert job['state'] == 'ready'
    assert voice.selected() is None
    voice.select(job['id'])
    return job['id']


def test_reference_selection_reuse_cache_and_restart(tmp_path):
    voice = AnyaVoiceService(tmp_path, MockBackend())
    try:
        selected = identity(voice)
        first = completed(voice, voice.submit('Same identity.'))
        second = completed(voice, voice.submit('Same identity.'))
        assert first['identity_id'] == second['identity_id'] == selected
        assert second['cache_hit']
        assert voice.audio(first['id']).read_bytes() == voice.audio(second['id']).read_bytes()
        voice.playback(second['id'], 'completed')
        assert voice.job(second['id'])['playback_events'][0]['state'] == 'completed'
    finally:
        voice.close()
    resumed = AnyaVoiceService(tmp_path, MockBackend())
    try:
        assert resumed.selected() == selected
        assert len(resumed.history()) == 3
        assert resumed.audio(first['id']).is_file()
        assert completed(resumed, resumed.submit('Another sentence.'))['identity_id'] == selected
        resumed._audio(selected).write_bytes(b'tampered')
        with pytest.raises(ValueError, match='alterada'):
            resumed.select(selected)
    finally:
        resumed.close()


def test_model_failure_is_explicit_and_does_not_select_voice(tmp_path):
    class Unavailable(MockBackend):
        def synthesize(self, request):
            raise RuntimeError('weights unavailable')
    voice = AnyaVoiceService(tmp_path, Unavailable())
    try:
        job = completed(voice, voice.submit('Test.', role='design'))
        assert job['state'] == 'failed'
        assert 'weights unavailable' in job['error']
        assert voice.identities() == [] and voice.selected() is None
        with pytest.raises(ValueError):
            voice.audio(job['id'])
        with pytest.raises(ValueError):
            voice.submit('No selection.')
        with pytest.raises(ValueError):
            voice.submit('\x00')
    finally:
        voice.close()


def test_replay_expiry_during_generation_and_critical_priority(tmp_path):
    gate = threading.Event()
    entered = threading.Event()
    class Slow(MockBackend):
        def synthesize(self, request):
            if request['role'] == 'clone':
                entered.set()
                assert gate.wait(5)
            return super().synthesize(request)
    voice = AnyaVoiceService(tmp_path, Slow())
    try:
        identity(voice)
        replay = {'experiment_id': 'e', 'timestamp': 10, 'expires_at': 15}
        a = voice.submit('Normal.', replay=replay)
        assert entered.wait(2)
        low = voice.submit('Low.', priority='low', replay=replay)
        critical = voice.submit('Critical.', priority='critical', replay=replay)
        assert voice.job(a['id'])['state'] == voice.job(low['id'])['state'] == 'cancelled'
        voice.advance('e', 16)
        gate.set()
        assert completed(voice, critical)['state'] == 'expired'
        with pytest.raises(ValueError):
            voice.audio(critical['id'])
        with pytest.raises(ValueError):
            voice.repeat(critical['id'])
        with pytest.raises(ValueError):
            voice.advance('e', 9)
    finally:
        gate.set()
        voice.close()


def experiment(client, imported, risks=True):
    if risks:
        client.post(f'/api/videos/{imported["id"]}/observations', json={'timestamp': 0, 'kind': 'ally_risk', 'value': .9, 'confidence': .9})
    client.post(f'/api/videos/{imported["id"]}/observations', json={'timestamp': 10, 'kind': 'enemy_risk', 'value': 1, 'confidence': 1})
    exp = client.post('/api/experiments', json={'video_id': imported['id']}).json()
    p = client.post(f'/api/experiments/{exp["id"]}/step', json={'timestamp': 0})
    assert p.status_code == 201
    return exp['id'], p.json()


def test_comms_temporal_isolation_hidden_information_and_failure(client, imported):
    eid, p = experiment(client, imported)
    research = client.app.state.research
    call = client.post(f'/api/experiments/{eid}/comms', json={}).json()
    assert call['max_accessible_timestamp'] == 0
    assert all(o['timestamp'] <= 0 for o in call['evidence'])
    assert not any(o['kind'] == 'enemy_risk' for o in call['evidence'])
    assert 'hidden_enemy_positions' in call['awareness']['unknown']
    assert call['category'] == 'warning' and 'possible' in call['text']
    assert call['decision'] == 'voice_unavailable'
    assert call['prediction_hash'] == p['hash']
    assert client.post(f'/api/experiments/{eid}/comms', json={}).json()['state'] == 'suppressed'
    assert client.post(f'/api/experiments/{eid}/comms/clock', json={'timestamp': 10}).status_code == 400
    assert client.app.state.store.verify(eid)['valid']


def test_hypotheses_abstention_immutable_and_outcomes_separate(client, imported):
    eid, p = experiment(client, imported)
    proposed = client.post(f'/api/experiments/{eid}/hypotheses').json()
    assert proposed[0]['type'] == 'heuristic_hypothesis'
    assert proposed[0]['probability'] is None
    assert proposed[0]['confirm_if'] == 'ally_first'
    assert client.post(f'/api/experiments/{eid}/hypotheses/evaluate').status_code == 400
    client.post(f'/api/videos/{imported["id"]}/reviews', json={'start': 0, 'end': 30})
    client.post(f'/api/videos/{imported["id"]}/events', json={'timestamp': 8, 'team': 'ally'})
    client.post(f'/api/experiments/{eid}/reveal')
    assert client.post(f'/api/experiments/{eid}/hypotheses/evaluate').json()[0]['verdict'] == 'confirmed'
    assert client.post(f'/api/experiments/{eid}/hypotheses').json() == proposed
    with client.app.state.store.connect() as db:
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('UPDATE hypotheses SET payload=?', ('{}',))
    # Future manual observations cannot rescue insufficient evidence at T=0.
    eid2, _ = experiment(client, imported, risks=False)
    # Existing t=0 ally annotation is frozen in this video; use an experiment at T=15 where it is stale.
    client.post(f'/api/experiments/{eid2}/step', json={'timestamp': 5})
    client.post(f'/api/experiments/{eid2}/step', json={'timestamp': 10})
    # High confidence enemy evidence becomes legitimately available only at T=10.
    known = client.post(f'/api/experiments/{eid2}/hypotheses').json()
    assert any(h.get('confirm_if') == 'enemy_first' for h in known)


def test_strategic_memory_persistence_and_temporal_queries(client, imported):
    eid, _ = experiment(client, imported)
    profile = 'a' * 32
    body = {'profile_id': profile, 'timestamp': 0, 'action': 'advance'}
    assert client.post(f'/api/experiments/{eid}/memory', json=body).status_code == 200
    assert client.post(f'/api/experiments/{eid}/memory', json={**body, 'timestamp': 5}).status_code == 400
    assert client.post(f'/api/experiments/{eid}/memory', json={**body, 'profile_id': 'real-name'}).status_code == 422
    memory = client.get(f'/api/experiments/{eid}/memory?scope=session').json()
    assert memory['observations'] == memory['frequencies']['advance'] == 1
    assert 0 < memory['wilson_95']['advance'][0] < 1
    resumed = StrategicResearch(client.app.state.store)
    assert resumed.memory(eid, 'session') == memory
    assert resumed.memory(eid, 'long_term')['observations'] == 0


def test_abstention_with_no_recent_risk(client, imported):
    eid, _ = experiment(client, imported, risks=False)
    assert client.post(f'/api/experiments/{eid}/hypotheses').json()[0]['type'] == 'abstention'
    call = client.post(f'/api/experiments/{eid}/comms', json={}).json()
    assert call['reason'] == 'insufficient_evidence'
    assert not call.get('voice_job_id')


def test_priority_order_and_lightweight_unload(tmp_path):
    entered, gate = threading.Event(), threading.Event()
    calls = []
    class Ordered(MockBackend):
        unloaded = 0
        def synthesize(self, request):
            calls.append(request['text'])
            if request['text'] == 'Blocking reference.':
                entered.set()
                assert gate.wait(5)
            return super().synthesize(request)
        def unload(self):
            self.unloaded += 1
    backend = Ordered()
    voice = AnyaVoiceService(tmp_path, backend)
    try:
        voice.profile = 'lightweight'
        first = voice.submit('Blocking reference.', role='design')
        assert entered.wait(2)
        normal = voice.submit('Normal candidate.', role='design')
        high = voice.submit('Critical candidate.', role='design', priority='critical')
        gate.set()
        assert completed(voice, first)['state'] == 'ready'
        assert completed(voice, high)['state'] == completed(voice, normal)['state'] == 'ready'
        assert calls == ['Blocking reference.', 'Critical candidate.', 'Normal candidate.']
        assert backend.unloaded >= 2
    finally:
        gate.set()
        voice.close()


def test_voice_api_roundtrip_and_director_playback(tmp_path, demo_video):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    app = create_app(tmp_path / 'data', voice_backend=MockBackend())
    with TestClient(app) as client:
        created = client.post('/api/voice/jobs', json={'text': 'Original.', 'role': 'design'})
        assert created.status_code == 202
        candidate = completed(app.state.voice, created.json())
        assert client.post('/api/voice/select', json={'identity_id': candidate['id']}).status_code == 200
        clone = completed(app.state.voice, client.post('/api/voice/jobs', json={'text': 'Same voice.'}).json())
        assert client.get(f'/api/voice/jobs/{clone["id"]}/audio').headers['content-type'].startswith('audio/wav')
        assert client.post('/api/voice/jobs', json={'text': 'Oi', 'language': 'Portuguese'}).status_code == 422
        imported = client.post('/api/videos', files={'file': ('demo.mp4', demo_video.read_bytes(), 'video/mp4')}, data={'synthetic': 'true'}).json()
        eid, _ = experiment(client, imported)
        call = client.post(f'/api/experiments/{eid}/comms', json={}).json()
        assert call['decision'] == 'queued'
        speech = completed(app.state.voice, {'id': call['voice_job_id']})
        assert speech['state'] == 'ready'
        assert client.get(f'/api/experiments/{eid}/director/srt').text == ''
        assert client.post(f'/api/voice/jobs/{speech["id"]}/playback', json={'state': 'started'}).status_code == 200
        assert '00:00:00,000' in client.get(f'/api/experiments/{eid}/director/srt').text
        exported = client.get(f'/api/experiments/{eid}/director/json').json()
        assert exported['mode'] == 'technical_demo'
        assert exported['calls'][0]['phase'] == 'pre_outcome_decision'
        client.post(f'/api/experiments/{eid}/step', json={'timestamp': 5})
        client.post(f'/api/experiments/{eid}/step', json={'timestamp': 10})
        client.post(f'/api/experiments/{eid}/comms/clock', json={'timestamp': 10})
        assert client.get(f'/api/voice/jobs/{speech["id"]}/audio').status_code == 400
        assert client.post(f'/api/voice/jobs/{speech["id"]}/repeat').status_code == 400


def test_research_record_tamper_is_refused(client, imported):
    eid, _ = experiment(client, imported)
    client.post(f'/api/experiments/{eid}/hypotheses')
    with client.app.state.store.connect() as db:
        db.execute('DROP TRIGGER hypotheses_no_update')
        original = json.loads(db.execute('SELECT payload FROM hypotheses').fetchone()[0])
        original['timestamp'] = 100
        db.execute('UPDATE hypotheses SET payload=?', (json.dumps(original),))
    assert client.get(f'/api/experiments/{eid}/hypotheses').status_code == 400


def test_voice_atomic_json_retries_only_transient_windows_locks(tmp_path, monkeypatch):
    from pathlib import Path
    from backend.voice import publish_json
    original = Path.replace
    source, destination = tmp_path / 'new.tmp', tmp_path / 'job.json'
    source.write_text('{"state":"ready"}')
    attempts = []
    def locked_once(path, target):
        attempts.append(True)
        if len(attempts) == 1:
            error = PermissionError('transient indexer lock')
            error.winerror = 5
            raise error
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', locked_once)
    publish_json(source, destination)
    assert len(attempts) == 2 and json.loads(destination.read_text())['state'] == 'ready'
    def permanent(path, target):
        raise OSError('persistent failure')
    monkeypatch.setattr(Path, 'replace', permanent)
    with pytest.raises(OSError, match='persistent'):
        publish_json(source, destination)
