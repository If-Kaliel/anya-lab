"""Compare exact extraction methods on a local video; no model performance claim."""
import argparse
import json
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from backend.frames import FrameExtractor
from backend.video import frame_at, probe


def benchmark(path):
    timestamps = probe(path)["frame_timestamps"]
    cutoffs = [t for t in (0, 5, 10, 15) if t <= timestamps[-1]]
    start = perf_counter()
    reference = [frame_at(path, timestamps, t) for t in cutoffs]
    reference_seconds = perf_counter() - start
    with FrameExtractor() as extractor:
        start = perf_counter()
        incremental = [extractor.frame_at(path, timestamps, t) for t in cutoffs]
        incremental_seconds = perf_counter() - start
        same = all(a[0] == b[0] and np.array_equal(
            cv2.imdecode(np.frombuffer(a[1], np.uint8), cv2.IMREAD_COLOR),
            cv2.imdecode(np.frombuffer(b[1], np.uint8), cv2.IMREAD_COLOR)) for a, b in zip(reference, incremental))
        if not same:
            raise ValueError("Frame equivalence failed")
        return {"cutoffs": cutoffs, "reference_seconds": reference_seconds,
                "incremental_seconds": incremental_seconds, "frames_equal": same,
                "speedup_this_run": reference_seconds / incremental_seconds,
                "decoder_stats": extractor.stats()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, nargs="?", default=Path("data/demo.mp4"))
    print(json.dumps(benchmark(parser.parse_args().video), indent=2))
