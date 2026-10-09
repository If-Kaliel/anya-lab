import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.contracts import EventInput, ExperimentInput, ObservationInput, ReviewInput, StepInput
from backend.experiments import ExperimentEngine, now
from backend.export import export_report
from backend.models import REGISTRY
from backend.storage import Store, canonical
from backend.video import frame_at, probe


def create_app(data_dir: Path | None = None):
    store = Store(data_dir or Path(os.getenv("ANYA_DATA_DIR", "data")))
    engine = ExperimentEngine(store)
    app = FastAPI(title="Anya · Oracle Prototype", version="0.1.0")
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    allowed_origins = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
    app.add_middleware(CORSMiddleware, allow_origins=list(allowed_origins), allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_origin(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin not in allowed_origins:
                return JSONResponse(status_code=403, content={"detail": "Origem não autorizada"})
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def missing_tool(request, exc):
        return JSONResponse(status_code=503, content={"detail": "Arquivo ou FFmpeg/FFprobe indisponível; verifique a instalação"})

    @app.exception_handler(subprocess.TimeoutExpired)
    async def timeout(request, exc):
        return JSONResponse(status_code=422, content={"detail": "Processamento excedeu o limite; use um trecho menor"})

    @app.exception_handler(subprocess.CalledProcessError)
    async def invalid_video(request, exc):
        return JSONResponse(status_code=422, content={"detail": "FFmpeg não conseguiu processar o vídeo; confira formato e integridade"})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0", "local_only": True,
                "ffmpeg": bool(shutil.which(os.getenv("ANYA_FFMPEG", "ffmpeg"))),
                "ffprobe": bool(shutil.which(os.getenv("ANYA_FFPROBE", "ffprobe")))}

    @app.get("/api/models")
    def models():
        return REGISTRY

    @app.get("/api/videos")
    def videos():
        with store.connect() as db:
            return [{k: v for k, v in json.loads(row[0]).items() if k not in {"stored_name", "frame_timestamps"}}
                    for row in db.execute("SELECT payload FROM videos ORDER BY rowid DESC")]

    @app.post("/api/videos", status_code=201)
    async def upload(file: UploadFile = File(...), split: Literal["train", "validation", "test"] = Form("test"), synthetic: bool = Form(False)):
        extension = Path(file.filename or "").suffix.lower()
        if extension not in {".mp4", ".mkv"}:
            raise ValueError("Importe um arquivo MP4 ou MKV")
        video_id = uuid4().hex
        path = store.root / "videos" / (video_id + extension)
        limit = int(os.getenv("ANYA_MAX_UPLOAD_MB", "2048")) * 1024 * 1024
        size = 0
        checksum = hashlib.sha256()
        try:
            with path.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Arquivo excede ANYA_MAX_UPLOAD_MB")
                    checksum.update(chunk)
                    output.write(chunk)
            # Run blocking probe outside the event loop.
            from starlette.concurrency import run_in_threadpool
            metadata = await run_in_threadpool(probe, path)
            with store.connect() as db:
                for row in db.execute("SELECT payload FROM videos"):
                    if json.loads(row[0])["sha256"] == checksum.hexdigest():
                        raise ValueError("Gravação duplicada: não é permitido dividir o mesmo arquivo entre datasets")
                payload = {"id": video_id, "name": Path(file.filename or "video").name,
                           "stored_name": path.name, "sha256": checksum.hexdigest(), "bytes": size,
                           "split": split, "synthetic": synthetic, "created_at": now(), **metadata}
                db.execute("INSERT INTO videos VALUES(?,?)", (video_id, canonical(payload)))
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {k: v for k, v in payload.items() if k not in {"stored_name", "frame_timestamps"}}

    @app.get("/api/videos/{video_id}/media")
    def media(video_id: str):
        video = store.video(video_id)
        # No user-supplied path is accepted. Browser playback and evaluation are separate from inference.
        return FileResponse(store.root / "videos" / video["stored_name"], media_type="video/mp4" if video["stored_name"].endswith(".mp4") else "video/x-matroska")

    @app.get("/api/videos/{video_id}/annotations")
    def annotations(video_id: str):
        store.video(video_id)
        return {table: store.annotations(table, video_id) for table in ("observations", "events", "reviews")}

    def annotate(table, video_id, item):
        video = store.video(video_id)
        end = item.get("timestamp", item.get("end"))
        if end > video["duration"]:
            raise ValueError("Anotação fora da duração da gravação")
        with store.connect() as db:
            cursor = db.execute(f"INSERT INTO {table}(video_id,payload) VALUES(?,?)", (video_id, canonical(item)))
            return {"id": cursor.lastrowid, **item}

    @app.post("/api/videos/{video_id}/observations", status_code=201)
    def observe(video_id: str, item: ObservationInput):
        return annotate("observations", video_id, item.model_dump())

    @app.post("/api/videos/{video_id}/events", status_code=201)
    def event(video_id: str, item: EventInput):
        return annotate("events", video_id, item.model_dump())

    @app.post("/api/videos/{video_id}/reviews", status_code=201)
    def review(video_id: str, item: ReviewInput):
        return annotate("reviews", video_id, item.model_dump())

    @app.get("/api/experiments")
    def experiments():
        with store.connect() as db:
            return [{**json.loads(row[0]), "frontier": row[1]} for row in db.execute("SELECT payload,frontier FROM experiments ORDER BY rowid DESC")]

    @app.post("/api/experiments", status_code=201)
    def create(config: ExperimentInput):
        return engine.create(config)

    @app.post("/api/experiments/{experiment_id}/step", status_code=201)
    def step(experiment_id: str, item: StepInput):
        return engine.step(experiment_id, item.timestamp)

    @app.get("/api/experiments/{experiment_id}/predictions")
    def predictions(experiment_id: str):
        store.experiment(experiment_id)
        return store.predictions(experiment_id)

    @app.get("/api/experiments/{experiment_id}/integrity")
    def integrity(experiment_id: str):
        store.experiment(experiment_id)
        return store.verify(experiment_id)

    @app.get("/api/experiments/{experiment_id}/frame")
    def frame(experiment_id: str, timestamp: float):
        exp = store.experiment(experiment_id)
        if timestamp < 0 or timestamp > exp["frontier"]:
            raise ValueError("Quadro futuro não autorizado")
        video = store.video(exp["config"]["video_id"])
        actual, png = frame_at(store.root / "videos" / video["stored_name"], video["frame_timestamps"], timestamp)
        return Response(png, media_type="image/png", headers={"X-Frame-Timestamp": str(actual)})

    @app.post("/api/experiments/{experiment_id}/reveal")
    def reveal(experiment_id: str):
        return engine.reveal(experiment_id)

    @app.get("/api/experiments/{experiment_id}/report")
    def report(experiment_id: str):
        return engine.report(experiment_id)

    @app.get("/api/experiments/{experiment_id}/export/{format}")
    def export(experiment_id: str, format: Literal["json", "csv", "srt"]):
        report = engine.report(experiment_id)
        if report is None:
            raise ValueError("Revele a avaliação para gerar o relatório")
        body, content_type = export_report(report, format)
        return Response(body, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="anya-{experiment_id}.{format}"'})

    @app.get("/api/comparison")
    def comparison():
        items = []
        with store.connect() as db:
            ids = [row[0] for row in db.execute("SELECT id FROM experiments ORDER BY rowid DESC")]
        for experiment_id in ids:
            report = engine.report(experiment_id)
            if report:
                items.append({"experiment_id": experiment_id, "match_id": report["config"]["video_id"],
                              "model_id": report["config"]["model_id"], "mode": report["mode"], **report["metrics"]})
        return items

    @app.get("/api/videos/{video_id}/dataset")
    def dataset(video_id: str):
        video = store.video(video_id)
        return {"schema_version": "1.0", "match": {k: v for k, v in video.items() if k not in {"stored_name", "frame_timestamps"}},
                "annotations": annotations(video_id)}

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app


app = create_app()
