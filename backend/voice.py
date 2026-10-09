"""Auditable local speech, explicit identities and a replay-aware priority queue."""
import hashlib
import json
import os
import queue
import re
import subprocess
import threading
import time
import wave
from pathlib import Path
from uuid import uuid4

from backend.resources import ResourceCoordinator
from backend.storage import canonical, digest

DESIGN_MODEL = 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign'
BASE_MODEL = 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'
VOICE_DESCRIPTION = ('A young adult woman with a soft, delicate British English accent. Her voice is intimate, '
    'ethereal, and quietly melancholic, with a gentle mid-high pitch and natural breathiness. She speaks calmly, '
    'with measured pacing, subtle warmth, and an almost supernatural serenity. Her delivery is articulate and '
    'intelligent, never theatrical or robotic. During moments of urgency, her voice becomes focused and firm '
    'without shouting. Maintain a natural, distinctly feminine timbre and restrained emotional expression.')
PRIORITIES = {'critical': 0, 'high': 1, 'normal': 2, 'low': 3}


def publish_json(temporary, target):
    """Windows indexers can briefly lock a JSON file; genuine failures still raise."""
    for attempt in range(5):
        try:
            temporary.replace(target)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in {5, 32, 33} or attempt == 4:
                raise
            time.sleep(.05 * 2**attempt)


def valid_text(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 500 or any(ord(c) < 32 and c not in '\n\t' for c in text):
        raise ValueError('Texto deve conter entre 1 e 500 caracteres legíveis')
    return text.strip()


class QwenBackend:
    name = 'qwen3-local'

    def __init__(self, root):
        self.root = root
        self.process = None
        self.log = None

    def synthesize(self, request):
        if self.process is None or self.process.poll() is not None:
            executable = Path(os.getenv('ANYA_VOICE_PYTHON', '.venv-voice/Scripts/python.exe')).resolve()
            if not executable.is_file():
                raise ValueError('Ambiente Qwen indisponível; consulte docs/voice.md')
            self.log = (self.root / 'worker.log').open('a', encoding='utf-8')
            self.process = subprocess.Popen([str(executable), '-m', 'backend.voice_worker'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, text=True, encoding='utf-8',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.process.stdin.write(canonical(request) + '\n')
        self.process.stdin.flush()
        timer = threading.Timer(900, self.unload)
        timer.daemon = True
        timer.start()
        try:
            line = self.process.stdout.readline()
        finally:
            timer.cancel()
        if not line:
            raise ValueError('Worker de voz terminou; consulte data/voice/worker.log')
        result = json.loads(line)
        if not result.get('ok'):
            raise ValueError(result.get('error', 'Falha de síntese'))
        return result

    def unload(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        self.process = None
        if self.log:
            self.log.close()
            self.log = None


class MockBackend:
    """CI only: a deterministic tone, never presented as a character voice."""
    name = 'mock-test-tone'

    def synthesize(self, request):
        with wave.open(request['output'], 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(24000)
            out.writeframes(b'\0\0' * 2400)
        return {'ok': True, 'duration': .1, 'sample_rate': 24000, 'device': 'mock'}

    def unload(self):
        pass


class AnyaVoiceService:
    def __init__(self, data_root, backend=None):
        self.root = data_root / 'voice'
        self.root.mkdir(parents=True, exist_ok=True)
        self.backend = backend or QwenBackend(self.root)
        self.resources = ResourceCoordinator()
        self.lock = threading.RLock()
        self.pending = queue.PriorityQueue()
        self.jobs = {}
        self.clocks = {}
        self.cache = {}
        self.sequence = 0
        self.closed = False
        self.active = None
        self.profile = 'research'
        for path in self.root.glob('job-*.json'):
            item = json.loads(path.read_text(encoding='utf-8'))
            self._audio(item['id'])  # Validate all restored identifiers before serving paths.
            if item['state'] in {'queued', 'synthesizing'}:
                item['state'] = 'interrupted'
                self._save(item)
            elif item['replay'] and item['state'] == 'ready':
                item['state'] = 'expired'
                self._save(item)
            self.jobs[item['id']] = item
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def identities(self):
        result = []
        for path in self.root.glob('identity-*.json'):
            item = json.loads(path.read_text(encoding='utf-8'))
            if self._audio(item['id']).is_file():
                result.append(item)
        return sorted(result, key=lambda x: x['created_at'])

    def selected(self):
        path = self.root / 'selected.json'
        return json.loads(path.read_text(encoding='utf-8'))['identity_id'] if path.is_file() else None

    def _audio(self, item_id):
        if not re.fullmatch('[a-f0-9]{32}', item_id):
            raise ValueError('Identificador de voz inválido')
        return self.root / (item_id + '.wav')

    def identity(self, item_id):
        self._audio(item_id)
        path = self.root / f'identity-{item_id}.json'
        if not path.is_file():
            raise ValueError('Identidade vocal não encontrada')
        item = json.loads(path.read_text(encoding='utf-8'))
        if item.get('manifest_hash') != digest({k: v for k, v in item.items() if k != 'manifest_hash'}):
            raise ValueError('Manifesto da referência vocal foi alterado')
        if hashlib.sha256(self._audio(item_id).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('A referência vocal foi alterada; seleção recusada')
        return item

    def select(self, item_id):
        with self.lock:
            item = self.identity(item_id)
            from backend.experiments import now
            selection = {'identity_id': item_id, 'sha256': item['sha256'], 'selected_at': now()}
            (self.root / f'selection-{uuid4().hex}.json').write_text(canonical(selection), encoding='utf-8')
            temporary = self.root / 'selected.tmp'
            temporary.write_text(canonical(selection), encoding='utf-8')
            publish_json(temporary, self.root / 'selected.json')
            return selection

    def repeat(self, item_id):
        item = self.job(item_id)
        if item['replay'] and (self._expired(item) or item['state'] in {'expired', 'interrupted', 'cancelled'}):
            raise ValueError('Call obsoleta não pode ser repetida como atual')
        return self.submit(item['text'], priority=item['priority'], replay=item['replay'])

    def playback(self, item_id, state):
        with self.lock:
            item = self.jobs.get(item_id)
            if not item or state not in {'started', 'completed', 'interrupted'}:
                raise ValueError('Registro de reprodução inválido')
            if state == 'started':
                self.audio(item_id)
            from backend.experiments import now
            item.setdefault('playback_events', []).append({'state': state, 'at': now(),
                'replay_timestamp': self.clocks.get(item['replay']['experiment_id']) if item['replay'] else None})
            self._save(item)
            return dict(item)

    def submit(self, text, role='clone', seed=42, priority='normal', replay=None):
        text = valid_text(text)
        if role not in {'clone', 'design'} or priority not in PRIORITIES:
            raise ValueError('Contrato de voz inválido')
        with self.lock:
            if self.closed:
                raise ValueError('Serviço de voz encerrado')
            if self.pending.qsize() >= 12:
                raise ValueError('Fila de voz cheia; aguarde ou cancele mensagens')
            identity = self.identity(self.selected()) if role == 'clone' and self.selected() else None
            if role == 'clone' and identity is None:
                raise ValueError('Gere e selecione uma referência vocal primeiro')
            from backend.experiments import now
            item = {'id': uuid4().hex, 'text': text, 'language': 'English', 'role': role,
                    'seed': seed, 'priority': priority, 'identity_id': identity['id'] if identity else None,
                    'identity_sha256': identity['sha256'] if identity else None,
                    'model_id': BASE_MODEL if role == 'clone' else DESIGN_MODEL,
                    'backend': self.backend.name, 'state': 'queued', 'created_at': now(),
                    'replay': replay, 'cache_hit': False, 'text_origin': 'user_text' if not replay else 'deterministic_callout_v1'}
            if priority == 'critical' and replay:
                for old in self.jobs.values():
                    if old['replay'] and old['replay']['experiment_id'] == replay['experiment_id'] and old['priority'] != 'critical' and old['state'] in {'queued', 'synthesizing', 'ready'}:
                        old['state'] = 'cancelled'
                        self._save(old)
            self.jobs[item['id']] = item
            self.sequence += 1
            self.pending.put((PRIORITIES[priority], self.sequence, item['id']))
            self._save(item)
            return dict(item)

    def _save(self, item):
        temporary = self.root / f'job-{item["id"]}.tmp'
        temporary.write_text(canonical(item), encoding='utf-8')
        publish_json(temporary, self.root / f'job-{item["id"]}.json')

    def _expired(self, item):
        replay = item['replay']
        return replay is not None and self.clocks.get(replay['experiment_id'], replay['timestamp']) > replay['expires_at']

    def advance(self, experiment_id, timestamp):
        with self.lock:
            if timestamp < self.clocks.get(experiment_id, -1):
                raise ValueError('Relógio do replay não pode retroceder; abra outra sessão')
            self.clocks[experiment_id] = timestamp
            for item in self.jobs.values():
                if item['state'] in {'queued', 'synthesizing', 'ready'} and self._expired(item):
                    item['state'] = 'expired'
                    self._save(item)

    def cancel(self, item_id):
        with self.lock:
            item = self.job(item_id)
            if item['state'] not in {'failed', 'expired'}:
                self.jobs[item_id]['state'] = 'cancelled'
                self._save(self.jobs[item_id])
            return self.job(item_id)

    def job(self, item_id):
        with self.lock:
            if item_id not in self.jobs:
                raise ValueError('Mensagem ausente nesta sessão do serviço')
            return dict(self.jobs[item_id])

    def audio(self, item_id):
        item = self.job(item_id)
        if item['state'] != 'ready' or self._expired(item):
            raise ValueError('Áudio indisponível, cancelado ou obsoleto')
        return self._audio(item_id)

    def history(self):
        # Previous sessions are retained as records, never silently replayed.
        return sorted((json.loads(p.read_text(encoding='utf-8')) for p in self.root.glob('job-*.json')),
                      key=lambda x: x['created_at'], reverse=True)[:100]

    def _run(self):
        while not self.closed:
            try:
                _, _, item_id = self.pending.get(timeout=.2)
            except queue.Empty:
                continue
            with self.lock:
                item = self.jobs[item_id]
                if item['state'] != 'queued' or self._expired(item):
                    if item['state'] == 'queued':
                        item['state'] = 'expired'
                        self._save(item)
                    continue
                item['state'] = 'synthesizing'
                self.active = item_id
                self._save(item)
            started = time.perf_counter()
            try:
                key = hashlib.sha256(canonical({k: item[k] for k in ('text', 'language', 'identity_sha256', 'model_id', 'seed', 'backend')}).encode()).hexdigest()
                output = self._audio(item_id)
                if item['role'] == 'clone' and key in self.cache and self.cache[key].is_file():
                    output.write_bytes(self.cache[key].read_bytes())
                    result = {'cache_hit': True}
                else:
                    request = {'role': item['role'], 'text': item['text'], 'seed': item['seed'],
                               'description': VOICE_DESCRIPTION, 'output': str(output),
                               'model_path': str(Path(os.getenv('ANYA_VOICE_MODELS', 'data/models')).resolve() / item['role'])}
                    if item['identity_id']:
                        identity = self.identity(item['identity_id'])
                        request['reference'] = {**identity, 'audio': str(self._audio(identity['id']))}
                    with self.resources.component('voice_' + item['role']):
                        result = self.backend.synthesize(request)
                with self.lock:
                    item['latency_ms'] = (time.perf_counter() - started) * 1000
                    item['measurement'] = result
                    item['cache_hit'] = result.get('cache_hit', False)
                    if item['state'] == 'synthesizing':
                        item['state'] = 'expired' if self._expired(item) else 'ready'
                    if item['state'] == 'ready':
                        if item['role'] == 'design':
                            identity = {k: item[k] for k in ('id', 'text', 'seed', 'model_id', 'created_at', 'backend')}
                            identity.update(schema_version='1.0', description=VOICE_DESCRIPTION,
                                sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                                model_revision=result.get('model_revision', 'mock'))
                            identity['manifest_hash'] = digest(identity)
                            (self.root / f'identity-{item_id}.json').write_text(canonical(identity), encoding='utf-8')
                        else:
                            self.cache[key] = output
                    self._save(item)
            except Exception as exc:
                with self.lock:
                    if item['state'] == 'synthesizing':
                        item['state'] = 'failed'
                    item['error'] = str(exc)[:1500]
                    item['latency_ms'] = (time.perf_counter() - started) * 1000
                    self._save(item)
            finally:
                if self.profile == 'lightweight':
                    with self.resources.component('voice_unload'):
                        self.backend.unload()
                self.active = None

    def unload(self):
        if self.active:
            raise ValueError('Aguarde a síntese terminar antes de liberar o modelo')
        with self.resources.component('voice_unload'):
            self.backend.unload()

    def close(self):
        self.closed = True
        self.backend.unload()
        self.thread.join(timeout=12)
