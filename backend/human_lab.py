"""Local blinded comparison. Participant context has no video or outcome capability."""
import hashlib
import json
import secrets
from datetime import datetime
from uuid import uuid4

from pydantic import Field, model_validator

from backend.contracts import ExperimentInput, Probabilities, StrictModel
from backend.evaluation import metrics, resolve
from backend.experiments import now
from backend.provenance import source_id
from backend.storage import canonical, digest


class StudyInput(StrictModel):
    video_id: str
    participant_id: str = Field(pattern='^[a-f0-9]{32}$')
    model_id: str = Field(default='heuristic-v1', pattern='^(heuristic-v1|historical-v1)$')
    training_match_ids: list[str] = Field(default_factory=list, max_length=100)
    start: float = Field(default=0, ge=0)
    step: float = Field(default=15, ge=1, le=60)
    count: int = Field(default=2, ge=1, le=50)
    participant_unseen_declared: bool = False
    seed: int = 42
    memory_seconds: float = Field(default=60, ge=10, le=600)


class HumanAnswer(StrictModel):
    round_index: int = Field(ge=0)
    context_hash: str = Field(pattern='^[a-f0-9]{64}$')
    probabilities: Probabilities | None = None
    abstain: bool = False

    @model_validator(mode='after')
    def decision(self):
        if self.abstain == (self.probabilities is not None):
            raise ValueError('Informe probabilidades válidas ou abstenção, exclusivamente')
        return self


class HumanLab:
    def __init__(self, store, engine, frames):
        self.store, self.engine, self.frames = store, engine, frames
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS lab_studies (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lab_tokens (hash TEXT PRIMARY KEY, study_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lab_openings (study_id TEXT, round_index INTEGER, started_at TEXT NOT NULL,
                    PRIMARY KEY(study_id,round_index));
                CREATE TABLE IF NOT EXISTS lab_answers (study_id TEXT NOT NULL, round_index INTEGER NOT NULL,
                    payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL,
                    PRIMARY KEY(study_id,round_index));
                CREATE TABLE IF NOT EXISTS lab_reports (id INTEGER PRIMARY KEY, study_id TEXT NOT NULL, payload TEXT NOT NULL);
            ''')
            for table in ('lab_studies', 'lab_tokens', 'lab_openings', 'lab_answers', 'lab_reports'):
                for action in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Human lab records are append-only'); END")

    def create(self, command: StudyInput):
        video = self.store.video(command.video_id)
        if video['split'] not in {'test', 'validation'}:
            raise ValueError('Comparação humana requer gravação de teste ou validação')
        if command.start + (command.count-1)*command.step + 15 > video['duration']:
            raise ValueError('Todos os instantes precisam de um horizonte completo de 15 segundos')
        # Validate independent training before creating any new predictions.
        for training_id in command.training_match_ids:
            train = self.store.video(training_id)
            if train['split'] != 'train' or source_id(train) == source_id(video) or train['synthetic'] != video['synthetic']:
                raise ValueError('Baseline aceita apenas outra origem train do mesmo modo real/sintético')
        config = dict(video_id=command.video_id, start=command.start, step=command.step,
                      memory_seconds=command.memory_seconds, seed=command.seed)
        ai = self.engine.create(ExperimentInput(**config, model_id=command.model_id,
            training_match_ids=command.training_match_ids if command.model_id == 'historical-v1' else []))
        baseline = ai if command.model_id == 'historical-v1' else (
            self.engine.create(ExperimentInput(**config, model_id='historical-v1', training_match_ids=command.training_match_ids))
            if command.training_match_ids else None)
        frame_records = []
        for i in range(command.count):
            timestamp = command.start + i*command.step
            prediction = self.engine.step(ai['id'], timestamp)
            if baseline and baseline['id'] != ai['id']:
                self.engine.step(baseline['id'], timestamp)
            actual, png = self.frames.frame_at(self.store.root / 'videos' / video['stored_name'], video['frame_timestamps'], timestamp)
            frame_records.append({'timestamp': actual, 'sha256': hashlib.sha256(png).hexdigest()})
        predictions = self.store.predictions(ai['id'])
        study = {'id': uuid4().hex, 'schema_version': 'human-lab-1.0', 'created_at': now(),
                 'config': command.model_dump(), 'video_id': video['id'], 'video_sha256': video['sha256'],
                 'source_match_id': source_id(video), 'split': video['split'], 'synthetic': video['synthetic'],
                 'mode': 'technical_demo' if video['synthetic'] else 'unvalidated_baseline',
                 'ai_experiment_id': ai['id'], 'baseline_experiment_id': baseline['id'] if baseline else None,
                 'prediction_hashes': [p['hash'] for p in predictions], 'frame_records': frame_records,
                 'baseline_hashes': [p['hash'] for p in self.store.predictions(baseline['id'])] if baseline else [],
                 'context_contract': 'shared_temporal_cutoff_frames_and_evidence_not_identical_semantic_capabilities'}
        study['study_hash'] = digest(study)
        with self.store.connect() as db:
            db.execute('INSERT INTO lab_studies VALUES(?,?)', (study['id'], canonical(study)))
        return study

    def study(self, study_id):
        with self.store.connect() as db:
            row = db.execute('SELECT payload FROM lab_studies WHERE id=?', (study_id,)).fetchone()
        if not row:
            raise ValueError('Estudo não encontrado')
        item = json.loads(row[0])
        if item['id'] != study_id or item.get('study_hash') != digest({k:v for k,v in item.items() if k != 'study_hash'}):
            raise ValueError('Falha de integridade no estudo')
        return item

    def studies(self):
        with self.store.connect() as db:
            ids = [row[0] for row in db.execute('SELECT id FROM lab_studies ORDER BY rowid DESC')]
        return [{**self.study(i), 'answered': len(self.answers(i)), 'has_report': self.report(i) is not None} for i in ids]

    def invite(self, study_id):
        study = self.study(study_id)
        if len(self.answers(study_id)) == study['config']['count']:
            raise ValueError('As respostas deste estudo já estão bloqueadas')
        token = secrets.token_hex(32)
        with self.store.connect() as db:
            db.execute('INSERT INTO lab_tokens VALUES(?,?)', (hashlib.sha256(token.encode()).hexdigest(), study_id))
        return token

    def authorize(self, token):
        if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Convite inválido')
        with self.store.connect() as db:
            row = db.execute('SELECT study_id FROM lab_tokens WHERE hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:
            raise ValueError('Convite inválido')
        return row[0]

    def predictions(self, study, baseline=False):
        experiment_id = study['baseline_experiment_id'] if baseline else study['ai_experiment_id']
        if not experiment_id:
            return []
        rows = self.store.predictions(experiment_id)
        expected = study['baseline_hashes'] if baseline else study['prediction_hashes']
        if not self.store.verify_predictions(rows)['valid'] or [p['hash'] for p in rows[:len(expected)]] != expected:
            raise ValueError('Previsões do estudo falharam na verificação de integridade')
        return rows[:len(expected)]

    def answers(self, study_id):
        with self.store.connect() as db:
            rows = list(db.execute('SELECT * FROM lab_answers WHERE study_id=? ORDER BY round_index', (study_id,)))
        previous, result = '0'*64, []
        for index, row in enumerate(rows):
            item = json.loads(row['payload'])
            if row['round_index'] != index or item.get('round_index') != index or item.get('study_id') != study_id or row['previous_hash'] != previous or digest({'previous_hash':previous, 'payload':item}) != row['hash']:
                raise ValueError('Falha de integridade nas respostas humanas')
            result.append({**item, 'hash':row['hash'], 'previous_hash':previous})
            previous = row['hash']
        return result

    def _context(self, study, index):
        prediction = self.predictions(study)[index]
        cutoff = prediction['timestamp']
        records = [r for r in study['frame_records'][:index+1] if r['timestamp'] >= cutoff-study['config']['memory_seconds']]
        context = {'round_index': index, 'timestamp': cutoff, 'max_accessible_timestamp': cutoff,
                   'horizon': 15, 'frames': records, 'observations': prediction['observations'],
                   'total_rounds': study['config']['count'], 'mode': study['mode'],
                   'participant_id': study['config']['participant_id'],
                   'participant_unseen_declared': study['config']['participant_unseen_declared'],
                   'semantic_perception': 'manual_risk_and_measured_pixels_only'}
        context['context_hash'] = digest(context)
        return context

    def context(self, study_id):
        study = self.study(study_id)
        index = len(self.answers(study_id))
        if index == study['config']['count']:
            return {'state': 'answers_locked', 'total_rounds': index, 'mode': study['mode']}
        context = self._context(study, index)
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO lab_openings VALUES(?,?,?)', (study_id,index,now()))
        return {'state': 'awaiting_prediction', **context}

    def frame(self, study_id, timestamp):
        study = self.study(study_id)
        index = len(self.answers(study_id))
        if index == study['config']['count']:
            raise ValueError('Coleta encerrada; contexto indisponível')
        context = self._context(study, index)
        record = next((r for r in context['frames'] if r['timestamp'] == timestamp), None)
        if record is None or timestamp > context['max_accessible_timestamp']:
            raise ValueError('Quadro futuro ou fora do contexto autorizado')
        video = self.store.video(study['video_id'])
        actual, png = self.frames.frame_at(self.store.root/'videos'/video['stored_name'], video['frame_timestamps'], timestamp)
        if actual != timestamp or hashlib.sha256(png).hexdigest() != record['sha256']:
            raise ValueError('Quadro não corresponde ao contexto congelado')
        return png

    def answer(self, study_id, command: HumanAnswer):
        study = self.study(study_id)
        # Validate existing chain before acquiring the writer lock; writers are serialized below.
        self.answers(study_id)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute('SELECT COUNT(*) FROM lab_answers WHERE study_id=?', (study_id,)).fetchone()[0]
            if count >= study['config']['count'] or command.round_index != count:
                raise ValueError('Resposta já bloqueada ou rodada futura não autorizada')
            context = self._context(study, count)
            if command.context_hash != context['context_hash']:
                raise ValueError('A resposta não corresponde ao contexto mostrado')
            opened = db.execute('SELECT started_at FROM lab_openings WHERE study_id=? AND round_index=?', (study_id,count)).fetchone()
            if not opened:
                raise ValueError('Abra o contexto antes de responder')
            submitted = now()
            item = {'study_id':study_id, 'round_index':count, 'context_hash':context['context_hash'],
                    'timestamp':context['timestamp'], 'max_accessible_timestamp':context['timestamp'],
                    'participant_id':study['config']['participant_id'], 'probabilities':command.probabilities.model_dump() if command.probabilities else None,
                    'abstain':command.abstain, 'started_at':opened[0], 'submitted_at':submitted,
                    'decision_time_ms':max(0, (datetime.fromisoformat(submitted)-datetime.fromisoformat(opened[0])).total_seconds()*1000),
                    'time_measurement':'server_elapsed_since_first_context_request_includes_inactive_time'}
            head = db.execute('SELECT hash FROM lab_answers WHERE study_id=? ORDER BY round_index DESC LIMIT 1', (study_id,)).fetchone()
            previous = head[0] if head else '0'*64
            row_hash = digest({'previous_hash':previous, 'payload':item})
            db.execute('INSERT INTO lab_answers VALUES(?,?,?,?,?)', (study_id,count,canonical(item),previous,row_hash))
        return {'state':'answer_locked', 'round_index':count, 'hash':row_hash}

    def report(self, study_id, report_id=None):
        with self.store.connect() as db:
            row = db.execute('SELECT id,payload FROM lab_reports WHERE study_id=? '+('AND id=?' if report_id else 'ORDER BY id DESC LIMIT 1'),
                (study_id,report_id) if report_id else (study_id,)).fetchone()
        if not row:
            if report_id:
                raise ValueError('Relatório não pertence ao estudo')
            return None
        item = json.loads(row['payload'])
        if item.get('report_hash') != digest({k:v for k,v in item.items() if k != 'report_hash'}) or item.get('study_id') != study_id:
            raise ValueError('Falha de integridade no relatório humano')
        return {**item, 'report_id':row['id']}

    def reveal(self, study_id):
        study = self.study(study_id)
        answers, predictions = self.answers(study_id), self.predictions(study)
        if len(answers) != study['config']['count']:
            raise ValueError('Todas as respostas humanas precisam estar bloqueadas antes de revelar')
        baseline = self.predictions(study, baseline=True)
        annotations = self.store.annotation_snapshot(study['video_id'])
        outcomes = {k:annotations[k] for k in ('events','reviews')}
        rows, human_rows, ai_rows, paired_ai, baseline_rows = [], [], [], [], []
        for index, (answer,prediction) in enumerate(zip(answers,predictions)):
            context = self._context(study,index)
            if answer['context_hash'] != context['context_hash']:
                raise ValueError('Contextos do humano e do modelo divergem')
            label, reason = resolve(outcomes['events'],outcomes['reviews'],prediction['timestamp'])
            row = {'round_index':index, 'timestamp':prediction['timestamp'], 'horizon':15,
                   'context_hash':context['context_hash'], 'label':label, 'reason':reason,
                   'ai':prediction, 'human':answer, 'baseline':baseline[index] if baseline else None}
            rows.append(row)
            ai_rows.append({**prediction,'label':label})
            if not answer['abstain']:
                human_rows.append({'probabilities':answer['probabilities'], 'label':label,
                                   'latency_ms':answer['decision_time_ms'], 'unknown_rate':0})
                paired_ai.append({**prediction,'label':label})
                if baseline:
                    baseline_rows.append({**baseline[index],'label':label})
        human_metrics = metrics(human_rows)
        human_metrics['mean_decision_time_ms'] = sum(a['decision_time_ms'] for a in answers)/len(answers)
        human_metrics.pop('mean_latency_ms')
        human_metrics.pop('unknown_rate')
        human_metrics.update(samples=len(answers), abstentions=sum(a['abstain'] for a in answers),
                             abstention_rate=sum(a['abstain'] for a in answers)/len(answers))
        report = {'schema_version':'human-lab-1.0', 'study_id':study_id, 'study_hash':study['study_hash'],
                  'video_id':study['video_id'], 'video_sha256':study['video_sha256'], 'source_match_id':study['source_match_id'],
                  'config':study['config'], 'mode':study['mode'], 'revealed_at':now(), 'rows':rows,
                  'answer_chain_head':answers[-1]['hash'], 'prediction_chain_head':predictions[-1]['hash'],
                  'annotation_hash':digest(outcomes), 'human_metrics':human_metrics, 'ai_all_metrics':metrics(ai_rows),
                  'ai_paired_metrics':metrics(paired_ai), 'baseline_paired_metrics':metrics(baseline_rows) if baseline else None,
                  'paired_evaluated':human_metrics['evaluated'], 'outcome_exclusions':sum(r['label'] is None for r in rows),
                  'limitations':['Small local sample; no claim of human or professional superiority.',
                    'Same temporal cutoff, frames and evidence; humans interpret images, baselines use manual risk and pixels.',
                    'Unseen recording is researcher/participant declaration, not independently verified.',
                    'Human elapsed decision time and machine inference latency measure different operations.',
                    'Overlapping windows and repeated participants may be correlated.']}
        report['report_hash'] = digest(report)
        with self.store.connect() as db:
            cursor = db.execute('INSERT INTO lab_reports(study_id,payload) VALUES(?,?)', (study_id,canonical(report)))
        return self.report(study_id,cursor.lastrowid)
