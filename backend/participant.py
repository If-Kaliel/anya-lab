"""Dedicated participant application. No media, research, voice or outcome routes."""
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.experiments import ExperimentEngine
from backend.frames import FrameExtractor
from backend.human_lab import HumanAnswer, HumanLab
from backend.local_boundary import exclusive_server
from backend.storage import Store


def create_participant_app(data_dir: Path | None = None):
    store = Store(data_dir or Path(os.getenv('ANYA_DATA_DIR', 'data')))
    frames = FrameExtractor()
    lab = HumanLab(store, ExperimentEngine(store, frames), frames)

    @asynccontextmanager
    async def lifespan(app):
        with exclusive_server(store.root, 8000, 'research'):
            try:
                yield
            finally:
                frames.close()

    app = FastAPI(title='Anya · Blinded Participant', version='0.5.0', lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lab = lab
    app.state.frames = frames
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost','127.0.0.1','testserver'])

    @app.middleware('http')
    async def local_origin(request, call_next):
        origin = request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8001','http://localhost:8001'}:
            return JSONResponse(status_code=403, content={'detail':'Origem não autorizada'})
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=400, content={'detail':str(exc)})

    @app.exception_handler(FileNotFoundError)
    async def unavailable(request, exc):
        return JSONResponse(status_code=503, content={'detail':'Quadro ou FFmpeg indisponível'})

    @app.exception_handler(subprocess.CalledProcessError)
    @app.exception_handler(subprocess.TimeoutExpired)
    async def decode_failure(request, exc):
        return JSONResponse(status_code=503, content={'detail':'Não foi possível decodificar o contexto autorizado'})

    def authorized(authorization: str | None = Header(None)):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(403, 'Convite necessário')
        try:
            return lab.authorize(authorization[7:])
        except ValueError:
            raise HTTPException(403, 'Convite inválido') from None

    @app.get('/api/health')
    def health():
        return {'status':'ok', 'version':'0.5.0', 'mode':'participant', 'local_only':True}

    @app.get('/api/participant/context')
    def context(study_id: str = Depends(authorized)):
        return lab.context(study_id)

    @app.get('/api/participant/frame')
    def frame(timestamp: float = Query(..., ge=0, allow_inf_nan=False), study_id: str = Depends(authorized)):
        return Response(lab.frame(study_id,timestamp), media_type='image/png')

    @app.post('/api/participant/answer', status_code=201)
    def answer(command: HumanAnswer, study_id: str = Depends(authorized)):
        return lab.answer(study_id,command)

    # Deliberately serve only compiled UI assets, never the data directory.
    dist = Path(__file__).resolve().parent.parent/'frontend'/'dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='participant-ui')
    return app


app = create_participant_app()
