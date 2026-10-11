"""Bounded incremental video decoding. Models never receive a decoder capability."""
import bisect
import os
import re
import subprocess
import time
from collections import OrderedDict, deque
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Condition, Event, RLock, Thread

import cv2
import numpy as np

from backend.video import FRAME_FILTER, authorized_index

# Jumps longer than this start a keyframe seek instead of decoding every intermediate frame.
SEEK_AFTER_SECONDS = 10.0
SHOWINFO = re.compile(rb"Parsed_showinfo_\d+ @ [^\]]+\] (?:\[info\] )?n:\s*\d+\s+pts:\s*-?\d+\s+pts_time:(-?[0-9.]+)")
DECODER_ERROR = re.compile(rb"\[(?:error|fatal|panic)\]")


class SeekUnverified(ValueError):
    """A seeked decoder could not prove which frame it produced; decode sequentially instead."""


class _FrameStream:
    def __init__(self, path: Path, timestamps=None, origin=None, seek_index=None):
        seeking = seek_index is not None
        self.command = [os.getenv("ANYA_FFMPEG", "ffmpeg"), "-loglevel", "level+info" if seeking else "error",
                        "-nostdin", "-threads", "2"]
        if seeking:
            # Keyframe seek on original timestamps; showinfo reports each frame's PTS so its
            # index is verified against the import-time frame table, never inferred from a count.
            self.command += ["-copyts", "-seek_timestamp", "1", "-noaccurate_seek",
                             "-ss", f"{timestamps[seek_index] + origin:.6f}"]
        self.command += ["-i", str(path), "-map", "0:v:0", "-an", "-sn", "-dn",
                         "-vf", FRAME_FILTER + (",showinfo" if seeking else ""), "-fps_mode", "passthrough",
                         "-f", "rawvideo", "-pix_fmt", "rgb24", "-threads", "2", "pipe:1"]
        self.seeking = seeking
        self.timestamps = timestamps
        self.origin = origin
        self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.position = -1
        self.received = 0
        self.queue = Queue(maxsize=2)
        self.stopped = Event()
        self.errors = deque(maxlen=20)
        self.frame_pts = []
        self.decoder_failed = False
        self.stderr_closed = False
        self.reported = Condition()
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
            if not self.seeking:
                self.errors.append(line)
                continue
            match = SHOWINFO.search(line)
            with self.reported:
                if match:
                    self.frame_pts.append(float(match.group(1)))
                elif DECODER_ERROR.search(line):
                    self.errors.append(line)
                    self.decoder_failed = True
                self.reported.notify_all()
        with self.reported:
            self.stderr_closed = True
            self.reported.notify_all()

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

    def _seeked_index(self, received, deadline):
        with self.reported:
            ready = self.reported.wait_for(lambda: len(self.frame_pts) > received or self.decoder_failed or self.stderr_closed,
                                           timeout=max(0.001, deadline - time.monotonic()))
            if not ready:
                raise subprocess.TimeoutExpired(self.command, 120)
            if self.decoder_failed or len(self.frame_pts) <= received:
                raise SeekUnverified("Decodificação após a busca não pôde ser verificada")
            local = self.frame_pts[received] - self.origin
        index = bisect.bisect_left(self.timestamps, local - 5e-5)
        if index >= len(self.timestamps) or abs(self.timestamps[index] - local) > 5e-5:
            raise SeekUnverified("Quadro após a busca não corresponde ao índice temporal")
        if self.position >= 0 and index != self.position + 1:
            raise SeekUnverified("Sequência de quadros após a busca não é contínua")
        return index

    def next_frame(self, remaining_seconds):
        deadline = time.monotonic() + max(0.001, remaining_seconds)
        try:
            item = self.queue.get(timeout=max(0.001, remaining_seconds))
        except Empty:
            raise subprocess.TimeoutExpired(self.command, 120) from None
        if isinstance(item, BaseException):
            if self.seeking:
                raise SeekUnverified(str(item)) from item
            raise ValueError(str(item)) from item
        received, raw = item
        if received != self.received:
            raise ValueError("Ordem dos quadros do decodificador inválida")
        self.received += 1
        if self.seeking:
            self.position = self._seeked_index(received, deadline)
        else:
            self.position = received
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
        self.seeks = self.seek_fallbacks = 0

    def _open(self, source, path, timestamps, origin, index, current):
        while len(self.sessions) >= self.max_sessions:
            _, oldest = self.sessions.popitem(last=False)
            oldest.close()
        # Legacy imports without the first-frame PTS keep sequential decoding.
        seek = origin is not None and timestamps[index] - current > SEEK_AFTER_SECONDS
        session = _FrameStream(path, timestamps, origin, index) if seek else _FrameStream(path)
        self.sessions[source] = session
        self.decoder_starts += 1
        self.seeks += seek
        return session

    def frame_at(self, path: Path, timestamps: list[float], cutoff: float, origin: float | None = None):
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
            if session and (session.position >= index or (origin is not None and session.position >= 0
                            and timestamps[index] - timestamps[session.position] > SEEK_AFTER_SECONDS)):
                session.close()
                del self.sessions[source]
                session = None
            if session is None:
                session = self._open(source, path, timestamps, origin, index, 0.0)
            self.sessions.move_to_end(source)
            deadline = time.monotonic() + 120
            while True:
                try:
                    while session.position < index:
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(session.command, 120)
                        raw = session.next_frame(deadline - time.monotonic())
                        self.consumed_frames += 1
                    if session.position != index:
                        raise SeekUnverified("A busca ultrapassou o quadro autorizado")
                    break
                except SeekUnverified:
                    # Fail closed: an unverifiable seek is replaced by full sequential decoding.
                    session.close()
                    del self.sessions[source]
                    self.seek_fallbacks += 1
                    session = self._open(source, path, timestamps, None, index, 0.0)
                except Exception:
                    session.close()
                    del self.sessions[source]
                    raise
            try:
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
                    "cached_frames": len(self.cache), "seeks": self.seeks, "seek_fallbacks": self.seek_fallbacks}

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
