"""Bounded incremental video decoding. Models never receive a decoder capability."""
import os
import subprocess
import time
from collections import OrderedDict, deque
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, RLock, Thread

import cv2
import numpy as np

from backend.video import FRAME_FILTER, authorized_index


class _FrameStream:
    def __init__(self, path: Path):
        self.command = [os.getenv("ANYA_FFMPEG", "ffmpeg"), "-v", "error", "-nostdin",
                        "-threads", "2", "-i", str(path), "-map", "0:v:0", "-an", "-sn", "-dn",
                        "-vf", FRAME_FILTER, "-fps_mode", "passthrough", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-threads", "2", "pipe:1"]
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.position = -1
        self.queue = Queue(maxsize=2)
        self.stopped = Event()
        self.errors = deque(maxlen=20)
        self.reader = Thread(target=self._read, daemon=True, name="anya-frame-reader")
        self.error_reader = Thread(target=self._errors, daemon=True, name="anya-ffmpeg-errors")
        self.reader.start()
        self.error_reader.start()

    def _put(self, item):
        while not self.stopped.is_set():
            try:
                self.queue.put(item, timeout=0.1)
                return
            except Full:
                continue

    def _errors(self):
        for line in iter(self.process.stderr.readline, b""):
            self.errors.append(line)

    def _read(self):
        size = 640 * 360 * 3
        try:
            index = 0
            while not self.stopped.is_set():
                raw = bytearray()
                while len(raw) < size:
                    chunk = self.process.stdout.read(size - len(raw))
                    if not chunk:
                        self._put(EOFError("Decodificador terminou antes do quadro solicitado"))
                        return
                    raw.extend(chunk)
                self._put((index, bytes(raw)))
                index += 1
        except (OSError, ValueError) as exc:
            if not self.stopped.is_set():
                self._put(exc)

    def next_frame(self, remaining_seconds):
        try:
            item = self.queue.get(timeout=max(0.001, remaining_seconds))
        except Empty:
            raise subprocess.TimeoutExpired(self.command, 120) from None
        if isinstance(item, BaseException):
            raise ValueError(str(item)) from item
        index, raw = item
        if index != self.position + 1:
            raise ValueError("Ordem dos quadros do decodificador inválida")
        self.position = index
        return raw

    def close(self):
        self.stopped.set()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.reader.join(timeout=3)
        self.error_reader.join(timeout=3)
        self.process.stdout.close()
        self.process.stderr.close()


class FrameExtractor:
    def __init__(self, max_sessions=2, cache_size=64):
        if max_sessions < 1 or cache_size < 1:
            raise ValueError("Decoder and cache capacities must be positive")
        self.max_sessions = max_sessions
        self.cache_size = cache_size
        self.sessions = OrderedDict()
        self.cache = OrderedDict()
        self.lock = RLock()
        self.decoder_starts = self.consumed_frames = self.cache_hits = 0

    def frame_at(self, path: Path, timestamps: list[float], cutoff: float):
        # Check authorization before cache lookup, including NaN/Infinity.
        index = authorized_index(timestamps, cutoff)
        path = path.resolve()
        stat = path.stat()
        source = (str(path), stat.st_size, stat.st_mtime_ns)
        key = (source, index)
        with self.lock:
            if key in self.cache:
                self.cache_hits += 1
                self.cache.move_to_end(key)
                return timestamps[index], self.cache[key]
            session = self.sessions.get(source)
            if session and session.position >= index:
                session.close()
                del self.sessions[source]
                session = None
            if session is None:
                while len(self.sessions) >= self.max_sessions:
                    _, oldest = self.sessions.popitem(last=False)
                    oldest.close()
                session = _FrameStream(path)
                self.sessions[source] = session
                self.decoder_starts += 1
            self.sessions.move_to_end(source)
            deadline = time.monotonic() + 120
            try:
                while session.position < index:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(session.command, 120)
                    raw = session.next_frame(deadline - time.monotonic())
                    self.consumed_frames += 1
                rgb = np.frombuffer(raw, dtype=np.uint8).reshape(360, 640, 3)
                ok, png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
                if not ok:
                    raise ValueError("Não foi possível codificar o quadro autorizado")
            except Exception:
                session.close()
                del self.sessions[source]
                raise
            self.cache[key] = png.tobytes()
            while len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
            return timestamps[index], self.cache[key]

    def stats(self):
        with self.lock:
            return {"decoder_starts": self.decoder_starts, "consumed_frames": self.consumed_frames,
                    "cache_hits": self.cache_hits, "active_sessions": len(self.sessions),
                    "cached_frames": len(self.cache)}

    def close(self):
        with self.lock:
            for session in self.sessions.values():
                session.close()
            self.sessions.clear()
            self.cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
