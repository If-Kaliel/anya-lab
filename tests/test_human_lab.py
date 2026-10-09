import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.human_lab import HumanAnswer, HumanLab, StudyInput
from backend.local_boundary import exclusive_server, require_peer_closed
from backend.participant import create_participant_app
from backend.storage import canonical, digest


def prepare(client, imported, **options):
    video = imported['id']
    client.post(f'/api/videos/{video}/reviews', json={'start':0, 'end':30})
    client.post(f'/api/videos/{video}/events', json={'timestamp':8,'team':'ally'})
    client.post(f'/api/videos/{video}/events', json={'timestamp':22,'team':'enemy'})
    client.post(f'/api/videos/{video}/observations', json={'timestamp':10,'kind':'enemy_risk','value':1,'confidence':1})
    response = client.post('/api/lab/studies', json={'video_id':video,'participant_id':uuid4().hex, **options})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def trial(client, imported):
    study = prepare(client,imported)
    lab = client.app.state.lab
    token = lab.invite(study['id'])
    # ASGI transport exercises the dedicated routes without starting another
    # TCP server. Real concurrent startup is separately refused by OS lock.
    app = create_participant_app(client.app.state.store.root)
    participant = TestClient(app)
    try:
        yield study,lab,participant,{'Authorization':f'Bearer {token}'}
    finally:
        participant.close(); app.state.frames.close()


def answer(participant, headers, context=None, abstain=False):
    context = context or participant.get('/api/participant/context',headers=headers).json()
    return participant.post('/api/participant/answer',headers=headers,json={
        'round_index':context['round_index'],'context_hash':context['context_hash'],'abstain':abstain,
        'probabilities':None if abstain else {'ally_first':.8,'enemy_first':.1,'none':.1}})


def test_participant_boundary_future_cache_and_no_research_routes(trial, imported):
    study,lab,participant,headers = trial
    context = participant.get('/api/participant/context?round_index=1',headers=headers).json()
    assert context['round_index'] == context['timestamp'] == context['max_accessible_timestamp'] == 0
    assert all(o['timestamp'] <= 0 for o in context['observations'])
    assert not any(o['kind'] == 'enemy_risk' for o in context['observations'])
    assert context['context_hash'] == digest({k:v for k,v in context.items() if k not in {'context_hash','state'}})
    for secret in ('probabilities','label','video_id','experiment_id','events','reviews','note'):
        assert secret not in json.dumps(context)
    # Populate even the participant decoder cache at T=15: authorization must
    # reject it before decode, regardless of cache availability.
    video = lab.store.video(study['video_id'])
    participant.app.state.frames.frame_at(lab.store.root/'videos'/video['stored_name'],video['frame_timestamps'],15)
    assert participant.get('/api/participant/frame?timestamp=0',headers=headers).status_code == 200
    assert participant.get('/api/participant/frame?timestamp=15',headers=headers).status_code == 400
    assert participant.get('/api/participant/frame?timestamp=1',headers=headers).status_code == 400
    for path in ('/api/videos', f'/api/videos/{imported["id"]}/media', f'/api/videos/{imported["id"]}/annotations',
                 '/api/experiments','/api/lab/studies','/api/voice/status','/api/research/dataset','/docs','/openapi.json'):
        assert participant.get(path,headers={**headers,'Range':'bytes=0-100'}).status_code == 404
    assert participant.post('/api/participant/answer',headers={**headers,'Origin':'https://example.org'},json={}).status_code == 403
    assert participant.get('/api/participant/context',headers=headers).headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('timestamp',['NaN','inf','-inf','-1'])
def test_nonfinite_and_negative_frames_rejected(trial,timestamp):
    _,_,participant,headers = trial
    assert participant.get(f'/api/participant/frame?timestamp={timestamp}',headers=headers).status_code == 422


@pytest.mark.parametrize('token',[None,'bad','a'*64,'A'*64])
def test_invites_require_valid_capability(trial,token):
    _,_,participant,_ = trial
    headers = {} if token is None else {'Authorization':f'Bearer {token}'}
    assert participant.get('/api/participant/context',headers=headers).status_code == 403


def test_sealing_abstention_paired_metrics_reveal_and_restart(trial,client):
    study,lab,participant,headers = trial
    sid = study['id']
    assert client.post(f'/api/lab/studies/{sid}/reveal').status_code == 400
    context = participant.get('/api/participant/context',headers=headers).json()
    assert answer(participant,headers,context).status_code == 201
    assert answer(participant,headers,context).status_code == 400
    following = participant.get('/api/participant/context',headers=headers).json()
    assert following['timestamp'] == 15
    assert any(o['kind']=='enemy_risk' for o in following['observations'])
    assert answer(participant,headers,following,True).status_code == 201
    assert participant.get('/api/participant/context',headers=headers).json()['state'] == 'answers_locked'
    assert participant.get('/api/participant/frame?timestamp=15',headers=headers).status_code == 400
    response = client.post(f'/api/lab/studies/{sid}/reveal')
    assert response.status_code == 201,response.text
    report = response.json()
    assert report['human_metrics']['accuracy'] == 1
    assert report['human_metrics']['brier_score'] == pytest.approx(.06)
    assert report['human_metrics']['samples'] == 2
    assert report['human_metrics']['abstention_rate'] == .5
    assert report['paired_evaluated'] == report['ai_paired_metrics']['evaluated'] == 1
    assert report['ai_all_metrics']['evaluated'] == 2 and report['baseline_paired_metrics'] is None
    assert report['human_metrics']['calibration'] is None
    assert report['rows'][0]['label'] == 'ally_first' and report['rows'][1]['label'] == 'enemy_first'
    assert answer(participant,headers,following,True).status_code == 400
    assert report['answer_chain_head'] == lab.answers(sid)[-1]['hash']
    resumed = HumanLab(lab.store,lab.engine,lab.frames)
    assert resumed.report(sid) == report
    assert resumed.answers(sid) == lab.answers(sid)
    for format in ('json','csv','srt'):
        export = client.get(f'/api/lab/studies/{sid}/export/{format}?report_id={report["report_id"]}')
        assert export.status_code == 200
        assert 'technical_demo' in export.text
    subtitles = client.get(f'/api/lab/studies/{sid}/export/srt?report_id={report["report_id"]}').text
    assert '00:00:15,000 --> 00:00:17,000' in subtitles
    assert 'PREVISÕES BLOQUEADAS' in subtitles and 'RESULTADO ANOTADO POSTERIOR' in subtitles
    assert client.get(f'/api/lab/studies/{sid}/export/json').status_code == 422


def test_wrong_context_round_contract_and_opening_are_rejected(trial):
    study,lab,participant,headers = trial
    context = lab._context(study,0)
    command = HumanAnswer(round_index=0,context_hash=context['context_hash'],abstain=True)
    with pytest.raises(ValueError,match='Abra'):
        lab.answer(study['id'],command)
    opened = participant.get('/api/participant/context',headers=headers).json()
    with lab.store.connect() as db:
        started = db.execute('SELECT started_at FROM lab_openings WHERE study_id=?',(study['id'],)).fetchone()[0]
    participant.get('/api/participant/context',headers=headers)
    with lab.store.connect() as db:
        assert db.execute('SELECT started_at FROM lab_openings WHERE study_id=?',(study['id'],)).fetchone()[0] == started
    body = {'round_index':0,'context_hash':opened['context_hash'],'abstain':True}
    assert participant.post('/api/participant/answer',headers=headers,json={**body,'context_hash':'0'*64}).status_code == 400
    assert participant.post('/api/participant/answer',headers=headers,json={**body,'round_index':1}).status_code == 400
    for invalid in ({'abstain':False}, {'probabilities':{'ally_first':.8,'enemy_first':.8,'none':0}},
                    {'abstain':True,'probabilities':{'ally_first':1,'enemy_first':0,'none':0}}, {'timestamp':100}):
        assert participant.post('/api/participant/answer',headers=headers,json={**body,**invalid}).status_code == 422


def test_versioned_reports_and_append_only_storage(trial,client,imported):
    study,lab,participant,headers = trial
    for _ in range(2): assert answer(participant,headers).status_code == 201
    sid = study['id']
    old = lab.reveal(sid)
    client.post(f'/api/videos/{imported["id"]}/reviews',json={'start':0,'end':15,'reliable':False})
    assert client.get(f'/api/lab/studies/{sid}/report-status').json()['stale']
    new = lab.reveal(sid)
    assert new['report_id'] != old['report_id'] and new['outcome_exclusions'] == 1
    assert lab.report(sid,old['report_id']) == old
    for table in ('lab_studies','lab_tokens','lab_openings','lab_answers','lab_reports'):
        with lab.store.connect() as db, pytest.raises(sqlite3.IntegrityError):
            db.execute(f'DELETE FROM {table}')
    with lab.store.connect() as db, pytest.raises(sqlite3.IntegrityError):
        db.execute('UPDATE lab_answers SET hash=?',('0'*64,))
    with lab.store.connect() as db:
        token_hash = db.execute('SELECT hash FROM lab_tokens').fetchone()[0]
    assert token_hash == hashlib.sha256(headers['Authorization'][7:].encode()).hexdigest()


def test_answer_tampering_blocks_report(trial):
    study,lab,participant,headers = trial
    for _ in range(2): assert answer(participant,headers).status_code == 201
    with lab.store.connect() as db:
        db.execute('DROP TRIGGER lab_answers_no_update')
        db.execute('UPDATE lab_answers SET hash=? WHERE round_index=0',('0'*64,))
    with pytest.raises(ValueError,match='integridade'):
        lab.reveal(study['id'])


def test_study_and_prediction_tampering_blocks_context(trial):
    study,lab,participant,headers = trial
    with lab.store.connect() as db:
        db.execute('DROP TRIGGER predictions_no_update')
        db.execute('UPDATE predictions SET hash=? WHERE experiment_id=?',('0'*64,study['ai_experiment_id']))
    assert participant.get('/api/participant/context',headers=headers).status_code == 400


def test_independent_baseline_split_mode_and_metrics(client,imported):
    store = client.app.state.store
    original = store.video(imported['id'])
    training = {**original,'id':uuid4().hex,'source_match_id':'independent-train','split':'train'}
    with store.connect() as db: db.execute('INSERT INTO videos VALUES(?,?)',(training['id'],canonical(training)))
    client.post(f'/api/videos/{training["id"]}/reviews',json={'start':0,'end':30})
    study = prepare(client,imported,training_match_ids=[training['id']])
    lab = client.app.state.lab
    for _ in range(2):
        context = lab.context(study['id'])
        lab.answer(study['id'],HumanAnswer(round_index=context['round_index'],context_hash=context['context_hash'],probabilities={'ally_first':.1,'enemy_first':.1,'none':.8}))
    report = lab.reveal(study['id'])
    assert report['baseline_paired_metrics']['evaluated'] == 2
    assert all(r['baseline']['probabilities']['none'] == pytest.approx(5/7) for r in report['rows'])
    for config in ({'video_id':training['id']}, {'training_match_ids':[imported['id']]}, {'count':3}, {'start':16}):
        result = client.post('/api/lab/studies',json={'video_id':imported['id'],'participant_id':uuid4().hex,**config})
        assert result.status_code == 400
    real_train = {**training,'id':uuid4().hex,'source_match_id':'real-train','synthetic':False}
    with store.connect() as db: db.execute('INSERT INTO videos VALUES(?,?)',(real_train['id'],canonical(real_train)))
    assert client.post('/api/lab/studies',json={'video_id':imported['id'],'participant_id':uuid4().hex,'training_match_ids':[real_train['id']]}).status_code == 400
    assert client.post('/api/experiments',json={'video_id':imported['id'],'model_id':'historical-v1','training_match_ids':[real_train['id']]}).status_code == 400
    other = prepare(client,imported,count=1)
    assert client.get(f'/api/lab/studies/{other["id"]}/report?report_id={report["report_id"]}').status_code == 400


def test_invitation_is_bound_to_study(client, imported):
    lab = client.app.state.lab
    a, b = prepare(client,imported,count=1), prepare(client,imported,start=15,count=1)
    token_a, token_b = lab.invite(a['id']),lab.invite(b['id'])
    assert lab.context(lab.authorize(token_a))['timestamp'] == 0
    assert lab.context(lab.authorize(token_b))['timestamp'] == 15


def test_os_lock_closes_simultaneous_start_and_releases(tmp_path,monkeypatch):
    monkeypatch.setattr('backend.local_boundary.require_peer_closed',lambda *args:None)
    with exclusive_server(tmp_path,8000,'research'):
        with pytest.raises(RuntimeError,match='Outro servidor'):
            with exclusive_server(tmp_path,8001,'participant'): pass
    with exclusive_server(tmp_path,8000,'research'): pass


def test_legacy_peer_server_is_refused(monkeypatch):
    class Peer:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,n): return b'{"local_only":true,"mode":"participant"}'
    monkeypatch.setattr('backend.local_boundary.urlopen',lambda *args,**kwargs:Peer())
    with pytest.raises(RuntimeError,match='Encerre'):
        require_peer_closed(8001,'participant')


def test_slow_voice_allowed_only_in_paused_research(trial,client,imported):
    voice = client.app.state.voice
    voice.resources.timings['voice_clone'] = 12000
    for profile, expected in [('replay_commentary','suppressed'), ('research','voice_unavailable')]:
        voice.profile = profile
        client.post(f'/api/videos/{imported["id"]}/observations',json={'timestamp':0,'kind':'ally_risk','value':.8,'confidence':1})
        eid = client.post('/api/experiments',json={'video_id':imported['id']}).json()['id']
        client.post(f'/api/experiments/{eid}/step',json={'timestamp':0})
        call = client.post(f'/api/experiments/{eid}/comms',json={}).json()
        assert call['decision'] == expected
        assert call['execution_profile'] == profile and call['expires_at'] == 5
        if profile == 'replay_commentary': assert call['reason'] == 'estimated_synthesis_exceeds_relevance_window'
