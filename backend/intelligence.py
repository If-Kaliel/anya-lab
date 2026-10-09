"""Minimal strategic records; deterministic interpretations, no hidden world state."""
import json
import math
import time
from uuid import uuid4

from backend.evaluation import resolve
from backend.experiments import now
from backend.storage import canonical, digest
from backend.temporal import snapshot
from backend.voice import PRIORITIES


class StrategicResearch:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            for table in ('calls', 'hypotheses', 'hypothesis_results', 'behavior'):
                db.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, payload TEXT NOT NULL)')
                for action in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Research records are append-only'); END")

    def records(self, table, experiment_id):
        if table not in {'calls', 'hypotheses', 'hypothesis_results', 'behavior'}:
            raise ValueError('Tabela de pesquisa inválida')
        with self.store.connect() as db:
            values = []
            for row in db.execute(f'SELECT id,payload FROM {table} WHERE experiment_id=? ORDER BY rowid', (experiment_id,)):
                item = json.loads(row['payload'])
                if item.get('id') != row['id'] or item.get('experiment_id') != experiment_id or item.get('record_hash') != digest({k: v for k, v in item.items() if k != 'record_hash'}):
                    raise ValueError('Falha de integridade no registro estratégico')
                values.append(item)
            return values

    def append(self, table, experiment_id, item):
        if table not in {'calls', 'hypotheses', 'hypothesis_results', 'behavior'}:
            raise ValueError('Tabela de pesquisa inválida')
        item = {'id': uuid4().hex, **item, 'experiment_id': experiment_id, 'created_at': now()}
        item['record_hash'] = digest(item)
        with self.store.connect() as db:
            db.execute(f'INSERT INTO {table} VALUES(?,?,?)', (item['id'], experiment_id, canonical(item)))
        return item

    def context(self, experiment_id):
        exp = self.store.experiment(experiment_id)
        predictions = self.store.predictions(experiment_id)
        if not predictions or not self.store.verify_predictions(predictions)['valid']:
            raise ValueError('Registre uma previsão íntegra antes de consultar contexto estratégico')
        prediction = predictions[-1]
        return exp, prediction, snapshot(prediction['observations'], prediction['timestamp'], exp['config'].get('memory_seconds'))

    @staticmethod
    def awareness(context):
        observed = [o for o in context.observations if o.confidence > 0]
        risks = {k: next((o for o in sorted(observed, key=lambda x: x.timestamp, reverse=True)
                         if o.kind == k and context.cutoff - o.timestamp <= 10), None)
                 for k in ('ally_risk', 'enemy_risk')}
        return {'observed': [{'kind': o.kind, 'timestamp': o.timestamp, 'value': o.value,
                              'confidence': o.confidence, 'source': o.source} for o in observed],
                'inferred': [], 'uncertain': [k for k, o in risks.items() if o is None or o.confidence < .7],
                'unknown': ['hero_positions', 'hidden_enemy_positions', 'abilities', 'player_intentions'],
                'cutoff': context.cutoff}, risks

    def propose(self, experiment_id):
        started = time.perf_counter()
        exp, prediction, context = self.context(experiment_id)
        existing = self.records('hypotheses', experiment_id)
        if any(h['prediction_hash'] == prediction['hash'] for h in existing):
            return [h for h in existing if h['prediction_hash'] == prediction['hash']]
        awareness, risks = self.awareness(context)
        result = []
        for kind, observation in risks.items():
            if observation is None or observation.confidence < .7 or observation.value < .6:
                continue
            label = 'ally_first' if kind == 'ally_risk' else 'enemy_first'
            result.append(self.append('hypotheses', experiment_id, {
                'type': 'heuristic_hypothesis', 'description': f'{label} may occur in the next 15 seconds.',
                'timestamp': context.cutoff, 'max_accessible_timestamp': context.cutoff, 'horizon': 15,
                'model_id': 'risk-hypotheses-v1', 'model_version': '1.0.0', 'probability': None,
                'confidence': observation.confidence, 'evidence': awareness['observed'], 'awareness': awareness,
                'prediction_hash': prediction['hash'], 'confirm_if': label,
                'refute_if': [k for k in ('ally_first', 'enemy_first', 'none') if k != label],
                'text_origin': 'deterministic_template_v1', 'latency_ms': (time.perf_counter()-started)*1000,
                'limitation': 'Manual risk evidence; not a calibrated probability or observed future event.'}))
        if not result:
            result.append(self.append('hypotheses', experiment_id, {
                'type': 'abstention', 'description': 'Insufficient recent risk evidence for a strategic hypothesis.',
                'timestamp': context.cutoff, 'max_accessible_timestamp': context.cutoff, 'horizon': 15,
                'model_id': 'risk-hypotheses-v1', 'model_version': '1.0.0', 'probability': None,
                'prediction_hash': prediction['hash'], 'evidence': awareness['observed'], 'awareness': awareness,
                'text_origin': 'deterministic_template_v1', 'confidence': None, 'latency_ms': (time.perf_counter()-started)*1000}))
        return result

    def evaluate(self, experiment_id, report):
        # Only after an explicit outcome reveal. Outcomes never enter propose()/call().
        if report is None:
            raise ValueError('Revele o relatório antes de avaliar hipóteses')
        rows = {r['hash']: r for r in report['rows']}
        result = []
        for hypothesis in self.records('hypotheses', experiment_id):
            row = rows.get(hypothesis['prediction_hash'])
            if not row:
                continue
            verdict = 'abstained' if hypothesis['type'] == 'abstention' else (
                'unresolved' if row['label'] is None else 'confirmed' if row['label'] == hypothesis['confirm_if'] else 'refuted')
            result.append(self.append('hypothesis_results', experiment_id, {
                'hypothesis_id': hypothesis['id'], 'report_id': report.get('report_id'),
                'outcome': row['label'], 'verdict': verdict, 'phase': 'post_reveal'}))
        return result

    def remember(self, experiment_id, profile_id, timestamp, action):
        exp, prediction, context = self.context(experiment_id)
        if timestamp > context.cutoff:
            raise ValueError('Memória futura recusada')
        return self.append('behavior', experiment_id, {'profile_id': profile_id, 'timestamp': timestamp,
            'action': action, 'source': 'manual_observation', 'video_id': exp['config']['video_id'],
            'max_accessible_timestamp': context.cutoff, 'prediction_hash': prediction['hash']})

    def memory(self, experiment_id, scope, profile_id=None):
        exp, _, context = self.context(experiment_id)
        allowed = [experiment_id]
        if scope == 'long_term':
            with self.store.connect() as db:
                ids = [r[0] for r in db.execute('SELECT id FROM experiments')]
            target = self.store.video(exp['config']['video_id'])
            from backend.provenance import source_id
            allowed = [i for i in ids if (v := self.store.video(self.store.experiment(i)['config']['video_id']))['split'] == 'train'
                       and source_id(v) != source_id(target) and v['synthetic'] == target['synthetic']]
        values = [b for i in allowed for b in self.records('behavior', i)
                  if (i != experiment_id or b['timestamp'] <= context.cutoff)
                  and (i == experiment_id or b['created_at'] <= exp['created_at'])
                  and (scope != 'short_term' or b['timestamp'] >= context.cutoff - 60)
                  and (not profile_id or b['profile_id'] == profile_id)]
        counts = {action: sum(b['action'] == action for b in values) for action in ('advance', 'retreat', 'hold', 'alternate_route')}
        n = len(values)
        def interval(count):
            if not n:
                return [0, 1]
            p, z = count / n, 1.96
            center = (p + z*z/(2*n)) / (1 + z*z/n)
            radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
            return [max(0, center-radius), min(1, center+radius)]
        return {'scope': scope, 'observations': n, 'frequencies': counts,
                'wilson_95': {k: interval(v) for k, v in counts.items()},
                'provenance_experiments': allowed, 'cutoff': context.cutoff,
                'limitation': 'Descriptive counts; repeated observations are not independent evidence of intentions.'}


class CalloutDecisionEngine:
    def __init__(self, research, voice):
        self.research, self.voice = research, voice
        self.lock = __import__('threading').Lock()

    def decide(self, experiment_id, frequency=10):
        with self.lock:
            started = time.perf_counter()
            exp, prediction, context = self.research.context(experiment_id)
            awareness, risks = self.research.awareness(context)
            history = self.research.records('calls', experiment_id)
            self.voice.advance(experiment_id, context.cutoff)
            if any(c['prediction_hash'] == prediction['hash'] for c in history):
                return {'state': 'suppressed', 'reason': 'already_decided'}
            candidates = [(o.value * o.confidence, kind, o) for kind, o in risks.items() if o and o.confidence >= .7 and o.value >= .6]
            if not candidates:
                category, priority, text, confidence = 'observation', 'low', 'The current evidence is insufficient for a tactical call. Hidden positions remain unknown.', None
                decision = 'abstained'
            else:
                score, kind, observation = max(candidates, key=lambda x: x[0])
                category, priority = 'warning', 'high' if score < .85 else 'critical'
                subject = 'allied' if kind == 'ally_risk' else 'opposing'
                text = f'Recent manual observations indicate elevated {subject} risk. An elimination is possible, but not confirmed.'
                confidence, decision = observation.confidence, 'candidate'
            last = next((c for c in reversed(history) if c['decision'] == 'queued'), None)
            estimate = self.voice.resources.timings.get('voice_clone', 0) / 1000
            reason = None
            if last and (last['text'] == text or context.cutoff - last['timestamp'] < frequency) and priority != 'critical':
                reason = 'repetition_or_frequency'
            if estimate > 5 and self.voice.profile == 'replay_commentary':
                reason = 'estimated_synthesis_exceeds_relevance_window'
            if decision == 'abstained':
                reason = 'insufficient_evidence'
            call = {'timestamp': context.cutoff, 'max_accessible_timestamp': context.cutoff, 'expires_at': context.cutoff + 5,
                    'model_id': 'callout-rules-v1', 'model_version': '1.0.0', 'prediction_model': prediction['model_id'],
                    'prediction_hash': prediction['hash'], 'category': category, 'priority': priority, 'text': text,
                    'confidence': confidence, 'evidence': awareness['observed'], 'awareness': awareness,
                    'text_origin': 'deterministic_template_v1', 'latency_ms': (time.perf_counter()-started)*1000,
                    'estimated_voice_seconds': estimate, 'execution_profile': self.voice.profile, 'decision': 'suppressed' if reason else 'queued', 'reason': reason}
            if not reason:
                try:
                    job = self.voice.submit(text, priority=priority, replay={'experiment_id': experiment_id,
                        'timestamp': context.cutoff, 'expires_at': context.cutoff + 5, 'prediction_hash': prediction['hash']})
                    call['voice_job_id'] = job['id']
                except Exception as exc:
                    call['decision'] = 'voice_unavailable'
                    call['reason'] = str(exc)
            return self.research.append('calls', experiment_id, call)
