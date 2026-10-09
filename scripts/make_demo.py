"""Generate only a deterministic synthetic video; never a gameplay dataset."""
import argparse
import os
import subprocess
from pathlib import Path


def make_demo(path: Path):
    import cv2
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    source = path.with_suffix(".source.avi")
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 360))
    if not writer.isOpened():
        raise ValueError("Cannot create synthetic video")
    try:
        for index in range(300):
            frame = np.full((360, 640, 3), (22, 17, 13), dtype=np.uint8)
            cv2.putText(frame, "ANYA / TECHNICAL DEMO", (35, 65), cv2.FONT_HERSHEY_SIMPLEX, .8, (220, 225, 230), 1)
            cv2.putText(frame, "SYNTHETIC DATA - NO GAMEPLAY", (35, 100), cv2.FONT_HERSHEY_SIMPLEX, .5, (150, 170, 190), 1)
            cv2.putText(frame, f"T + {index / 10:05.1f}s", (35, 305), cv2.FONT_HERSHEY_SIMPLEX, .8, (220, 225, 230), 1)
            cv2.circle(frame, (45 + index, 195), 18, (160, 130, 100), 1)
            writer.write(frame)
    finally:
        writer.release()
    try:
        subprocess.run([
            os.getenv("ANYA_FFMPEG", "ffmpeg"), "-v", "error", "-y", "-i", str(source),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)
        ], check=True, timeout=60)
    finally:
        source.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/demo.mp4"))
    args = parser.parse_args()
    make_demo(args.output)
    print(f"Demonstração sintética criada: {args.output.resolve()}")
