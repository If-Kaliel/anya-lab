"""Isolated Qwen runtime. JSON lines on stdout, library diagnostics on stderr."""
import contextlib
import gc
import json
import sys
from pathlib import Path


def main():
    output = sys.stdout
    model = None
    loaded = None
    prompts = {}
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                import numpy as np
                import soundfile as sf
                import torch
                from qwen_tts import Qwen3TTSModel
                role = request['role']
                if loaded != role:
                    model = None
                    prompts.clear()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    path = Path(request['model_path']).resolve()
                    if not (path / 'model.safetensors').is_file():
                        raise ValueError('Pesos locais ausentes; execute scripts/prepare_voice.py')
                    device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
                    model = Qwen3TTSModel.from_pretrained(str(path), device_map=device,
                        dtype=torch.bfloat16 if device.startswith('cuda') else torch.float32,
                        attn_implementation='sdpa', local_files_only=True)
                    loaded = role
                torch.manual_seed(request.get('seed', 42))
                if device.startswith('cuda'):
                    torch.cuda.reset_peak_memory_stats()
                with torch.inference_mode():
                    if role == 'design':
                        waves, rate = model.generate_voice_design(text=request['text'], language='English',
                            instruct=request['description'], max_new_tokens=1024)
                    else:
                        reference = request['reference']
                        key = reference['sha256']
                        if key not in prompts:
                            audio, rate = sf.read(reference['audio'], dtype='float32')
                            prompts[key] = model.create_voice_clone_prompt(
                                ref_audio=(audio, rate), ref_text=reference['text'], x_vector_only_mode=False)
                        waves, rate = model.generate_voice_clone(text=request['text'], language='English',
                            voice_clone_prompt=prompts[key], max_new_tokens=1024)
                    wave = np.asarray(waves[0], dtype=np.float32)
                    if not len(wave) or not np.isfinite(wave).all():
                        raise ValueError('O modelo retornou áudio inválido')
                    sf.write(request['output'], wave, rate)
                response = {'ok': True, 'sample_rate': rate, 'duration': len(wave) / rate,
                            'device': device, 'prompt_count': len(prompts),
                            'model_revision': json.loads((Path(request['model_path']) / 'anya-source.json').read_text())['revision'] if (Path(request['model_path']) / 'anya-source.json').is_file() else 'unrecorded_local_weights',
                            'torch_version': torch.__version__,
                            'peak_gpu_bytes': torch.cuda.max_memory_allocated() if device.startswith('cuda') else None}
        except Exception as exc:
            response = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
        output.write(json.dumps(response) + '\n')
        output.flush()


if __name__ == '__main__':
    main()
