import bisect
import json
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np


FRAME_FILTER = "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,format=rgb24"


def authorized_index(timestamps: list[float], cutoff: float):
    if not np.isfinite(cutoff) or cutoff < 0:
        raise ValueError("Timestamp deve ser finito e não negativo")
    index = bisect.bisect_right(timestamps, cutoff) - 1
    if index < 0:
        raise ValueError("Nenhum quadro autorizado")
    return index


def probe(path: Path):
    result = subprocess.run([
        os.getenv("ANYA_FFPROBE", "ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name:format=duration:frame=best_effort_timestamp_time",
        "-of", "json", str(path)
    ], capture_output=True, check=True, timeout=180)
    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    frames = info.get("frames", [])
    if not streams or not frames or any("best_effort_timestamp_time" not in f for f in frames):
        raise ValueError("Vídeo sem timestamps verificáveis")
    raw = [float(f["best_effort_timestamp_time"]) for f in frames]
    if not all(np.isfinite(t) for t in raw):
        raise ValueError("Timestamps não finitos na gravação")
    timestamps = [round(t - raw[0], 6) for t in raw]
    if any(b < a for a, b in zip(timestamps, timestamps[1:])):
        raise ValueError("Timestamps fora de ordem")
    duration = float(info["format"]["duration"])
    stream = streams[0]
    if not np.isfinite(duration) or duration <= 0 or duration > 6 * 3600:
        raise ValueError("Duração inválida; limite de 6 horas")
    if stream["width"] * stream["height"] > 3840 * 2160:
        raise ValueError("Resolução máxima: 3840 × 2160")
    return {"duration": duration, "width": stream["width"], "height": stream["height"],
            "codec": stream["codec_name"], "frame_timestamps": timestamps}


def frame_at(path: Path, timestamps: list[float], cutoff: float):
    index = authorized_index(timestamps, cutoff)
    result = subprocess.run([
        os.getenv("ANYA_FFMPEG", "ffmpeg"), "-v", "error", "-i", str(path),
        "-vf", f"select=eq(n\\,{index}),{FRAME_FILTER}", "-frames:v", "1",
        "-fps_mode", "vfr", "-f", "image2pipe", "-vcodec", "png", "pipe:1"
    ], capture_output=True, check=True, timeout=120)
    if not result.stdout:
        raise ValueError("Não foi possível extrair o quadro")
    return timestamps[index], result.stdout


def perceive(png: bytes, timestamp: float):
    gray = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Quadro inválido")
    return (
        {"timestamp": timestamp, "kind": "luminance", "value": float(gray.mean() / 255),
         "confidence": 1.0, "source": "pixel-measurement"},
        {"timestamp": timestamp, "kind": "semantic_state", "value": 0.0,
         "confidence": 0.0, "source": "unknown"},
    )
