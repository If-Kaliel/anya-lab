"""Generate candidates and benchmark design→clone, without approving an identity."""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from backend.voice import AnyaVoiceService, VOICE_DESCRIPTION


def wait(service, job):
    while True:
        state = service.job(job['id'])
        if state['state'] not in {'queued', 'synthesizing'}:
            if state['state'] != 'ready':
                raise ValueError(state.get('error', state['state']))
            return state
        time.sleep(.5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--output', type=Path, default=Path('exports/voice-benchmark.json'))
    args = parser.parse_args()
    voice = AnyaVoiceService(args.data)
    results = []
    try:
        for seed in (42, 43):
            job = wait(voice, voice.submit('I am Anya. We will follow the evidence, and leave uncertainty visible.', role='design', seed=seed))
            results.append(job)
            print(json.dumps({'role': 'design', 'seed': seed, 'id': job['id'], 'latency_ms': job['latency_ms'], 'measurement': job['measurement']}), flush=True)
        # Explicit benchmark candidate, never writes selected.json.
        candidate = voice.identity(results[0]['id'])
        for text in ('The current evidence is uncertain.', 'An elimination is possible, but not confirmed.', 'The current evidence is uncertain.'):
            output = voice.root / (uuid4().hex + '.wav')
            request = {'role': 'clone', 'text': text, 'seed': 42, 'description': VOICE_DESCRIPTION,
                       'model_path': str(Path('data/models/clone').resolve()), 'output': str(output.resolve()),
                       'reference': {**candidate, 'audio': str(voice._audio(candidate['id']))}}
            started = time.perf_counter()
            result = voice.backend.synthesize(request)
            result = {'role': 'clone', 'text': text, 'audio': str(output), 'identity_id': candidate['id'],
                      'latency_ms': (time.perf_counter()-started)*1000, 'measurement': result}
            results.append(result)
            print(json.dumps(result), flush=True)
    finally:
        voice.close()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'results': results, 'selected_automatically': False,
            'scope': 'Local hardware benchmark; voice identity quality requires human approval.'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
