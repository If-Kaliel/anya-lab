"""One local voice worker owns one model at a time; no distributed scheduling."""
import subprocess
import time
from contextlib import contextmanager
from threading import Lock


class ResourceCoordinator:
    def __init__(self):
        self.lock = Lock()
        self.active = None
        self.timings = {}

    @contextmanager
    def component(self, name):
        with self.lock:
            self.active = name
            started = time.perf_counter()
            try:
                yield
            finally:
                self.timings[name] = (time.perf_counter() - started) * 1000
                self.active = None

    def status(self):
        gpu = None
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used',
                                     '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                gpu = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return {'active_component': self.active, 'last_latency_ms': dict(self.timings),
                'gpu': gpu, 'policy': 'one_voice_model_at_a_time', 'real_time_validated': False}
