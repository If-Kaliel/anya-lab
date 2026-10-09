"""Local, disposable browser previews. The inference path uses original videos."""
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import RLock
from uuid import uuid4

from backend.storage import canonical


class PlaybackPreviews:
    recipe = "h264-video-zero-1"

    def __init__(self, store):
        self.store = store
        self.root = store.root / "previews"
        self.root.mkdir(exist_ok=True)
        self.lock = RLock()
        self.jobs = {}
        self.processes = {}
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="anya-preview")

    def path(self, video_id):
        self.store.video(video_id)
        return self.root / f"{video_id}.mp4"

    def status(self, video_id):
        video = self.store.video(video_id)
        marker = self.root / f"{video_id}.json"
        with self.lock:
            if marker.exists() and self.path(video_id).exists():
                try:
                    metadata = json.loads(marker.read_text(encoding="utf-8"))
                    if metadata == {"recipe": self.recipe, "source_sha256": video["sha256"]}:
                        return {"state": "ready", "video_id": video_id, "url": f"/api/videos/{video_id}/preview/media"}
                except (ValueError, OSError):
                    pass
            return {"video_id": video_id, **self.jobs.get(video_id, {"state": "missing"})}

    def prepare(self, video_id):
        video = self.store.video(video_id)
        with self.lock:
            state = self.status(video_id)
            if state["state"] in {"ready", "processing", "queued"}:
                return state
            if self.closed or sum(j["state"] in {"queued", "processing"} for j in self.jobs.values()) >= 2:
                raise ValueError("Dois vídeos já estão sendo preparados. Aguarde a conclusão.")
            self.jobs[video_id] = {"state": "queued"}
            self.pool.submit(self._prepare, video)
            return {"video_id": video_id, "state": "queued"}

    def _prepare(self, video):
        video_id = video["id"]
        temporary = self.root / f"{video_id}-{uuid4().hex}.mp4"
        process = None
        try:
            with self.lock:
                if self.closed:
                    self.jobs[video_id] = {"state": "failed", "detail": "Preparação interrompida; tente novamente"}
                    return
                self.jobs[video_id] = {"state": "processing"}
                # copyts keeps audio PTS in the original clock; both streams are
                # aligned to the first displayed video frame, dropping earlier audio.
                start_pts = float(video.get("first_frame_pts", 0))
                command = [os.getenv("ANYA_FFMPEG", "ffmpeg"), "-v", "error", "-nostdin", "-y",
                           "-copyts", "-threads", "2", "-i", str(self.store.root / "videos" / video["stored_name"]),
                           "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1",
                           "-filter_threads", "2", "-vf", "setpts=PTS-STARTPTS,scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2",
                           "-af", f"asetpts=PTS-({start_pts:.6f})/TB,aresample=async=1:first_pts=0",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                           "-fps_mode", "vfr", "-threads", "2", "-c:a", "aac", "-b:a", "128k",
                           "-t", str(video["duration"]), "-movflags", "+faststart", str(temporary)]
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.processes[video_id] = process
            _, errors = process.communicate(timeout=900)
            if process.returncode or not temporary.exists() or not temporary.stat().st_size:
                raise ValueError("FFmpeg não conseguiu preparar a reprodução compatível")
            check = subprocess.run([os.getenv("ANYA_FFPROBE", "ffprobe"), "-v", "error",
                                    "-show_entries", "format=duration", "-of", "json", str(temporary)],
                                   capture_output=True, check=True, timeout=30)
            duration = float(json.loads(check.stdout)["format"]["duration"])
            if abs(duration - video["duration"]) > 0.25:
                raise ValueError("Prévia com duração incompatível; use um trecho menor")
            with self.lock:
                if self.closed:
                    raise ValueError("Preparação interrompida; tente novamente")
                temporary.replace(self.path(video_id))
                (self.root / f"{video_id}.json").write_text(canonical({"recipe": self.recipe, "source_sha256": video["sha256"]}), encoding="utf-8")
                self.jobs[video_id] = {"state": "ready"}
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate()
            message = str(exc) if isinstance(exc, ValueError) else "Preparação falhou. Verifique FFmpeg, espaço em disco ou use um trecho menor."
            with self.lock:
                self.jobs[video_id] = {"state": "failed", "detail": message}
        finally:
            if process is not None and process.stderr:
                process.stderr.close()
            temporary.unlink(missing_ok=True)
            with self.lock:
                self.processes.pop(video_id, None)

    def close(self):
        with self.lock:
            self.closed = True
            for process in self.processes.values():
                if process.poll() is None:
                    process.terminate()
        self.pool.shutdown(wait=True)
