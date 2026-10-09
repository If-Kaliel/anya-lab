"""Explicit official-model download, pinned by commit, into the ignored local data directory."""
import argparse
import json
import os
import shutil
import urllib.request
from pathlib import Path

MODELS = {'design': 'Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign', 'clone': 'Qwen/Qwen3-TTS-12Hz-0.6B-Base'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--role', choices=['design', 'clone', 'both'], default='both')
    parser.add_argument('--download', action='store_true', help='Explicitly permit approximately 7GB of weights')
    parser.add_argument('--root', type=Path, default=Path('data/models'))
    args = parser.parse_args()
    print('Official weights: approximately 7GB total; reserve 15-20GB including CUDA environment.', flush=True)
    if not args.download:
        print('No download. Add --download after checking space.')
        return
    args.root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(args.root).free < 10 * 1024**3:
        raise ValueError('Reserve at least 10GB free for model download and temporary files')
    from huggingface_hub import snapshot_download
    os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    for role in MODELS if args.role == 'both' else [args.role]:
        model_id = MODELS[role]
        with urllib.request.urlopen('https://huggingface.co/api/models/' + model_id, timeout=60) as response:
            revision = json.load(response)['sha']
        destination = args.root / role
        print(f'Downloading {model_id} at {revision}', flush=True)
        snapshot_download(model_id, revision=revision, local_dir=destination, max_workers=2)
        (destination / 'anya-source.json').write_text(json.dumps({'model_id': model_id, 'revision': revision}), encoding='utf-8')
        print(f'Ready: {destination}', flush=True)


if __name__ == '__main__':
    main()
