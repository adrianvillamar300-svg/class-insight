"""
ClassInsight - API Backend con FastAPI.
Expone endpoints para transcripción y análisis de clases.
"""

import os
import uuid
import shutil
import asyncio
import logging
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.pipeline import (
    get_aws_clients,
    upload_to_s3,
    start_transcription,
    download_and_extract_transcript,
    analyze_with_bedrock,
    save_output,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Estado en memoria de los jobs en progreso
jobs: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)

app = FastAPI(title="ClassInsight API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class YouTubeRequest(BaseModel):
    url: str


# ──────────────────────────────────────────────
# Frontend
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Sirve el index.html como página principal."""
    html_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok"}


# ──────────────────────────────────────────────
# Procesamiento de audio/video
# ──────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze_file(
    file: UploadFile = File(...),
    input_type: str = Form("audio"),
):
    """
    Recibe un archivo de audio o video, lo procesa y devuelve el análisis.
    input_type: 'audio' o 'video'
    """
    allowed_audio = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    allowed_video = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
    suffix = Path(file.filename).suffix.lower()

    if input_type == "video" and suffix not in allowed_video:
        raise HTTPException(400, f"Formato de video no soportado: {suffix}")
    if input_type == "audio" and suffix not in allowed_audio:
        raise HTTPException(400, f"Formato de audio no soportado: {suffix}")

    job_id = str(uuid.uuid4())[:8]
    temp_path = UPLOAD_DIR / f"{job_id}{suffix}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info("Archivo guardado temporalmente: %s", temp_path)

        audio_path = str(temp_path)

        if input_type == "video":
            audio_path = str(UPLOAD_DIR / f"{job_id}_extracted.wav")
            await extract_audio(str(temp_path), audio_path)

        result = await run_pipeline(audio_path, job_id)

        return {"status": "completed", "result": result, "job_id": job_id}

    except Exception as e:
        logger.error("Error procesando archivo: %s", e)
        raise HTTPException(500, f"Error al procesar: {str(e)}")
    finally:
        temp_path.unlink(missing_ok=True)
        extracted = UPLOAD_DIR / f"{job_id}_extracted.wav"
        extracted.unlink(missing_ok=True)


# ──────────────────────────────────────────────
# YouTube
# ──────────────────────────────────────────────

@app.post("/api/analyze-youtube")
async def analyze_youtube(req: YouTubeRequest):
    """Descarga audio de YouTube y lo procesa."""
    job_id = str(uuid.uuid4())[:8]
    output_path = str(UPLOAD_DIR / f"{job_id}_yt.wav")

    try:
        cmd = [
            "yt-dlp",
            "--cookies", "/app/cookies.txt",
            "--extract-audio",
            "--audio-format", "wav",
            "--audio-quality", "0",
            "--no-playlist",
            "-o", output_path,
            req.url,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            logger.error("yt-dlp falló: %s", error_msg)
            raise HTTPException(400, f"No se pudo descargar el video: {error_msg[:200]}")

        wav_path = Path(output_path)
        if not wav_path.exists():
            yt_dlp_output = stdout.decode("utf-8", errors="replace")
            actual_ext = Path(yt_dlp_output.strip().split("\n")[-1]).suffix if yt_dlp_output.strip() else ""
            candidates = list(UPLOAD_DIR.glob(f"{job_id}_yt.*"))
            if candidates:
                wav_path = candidates[0]
            else:
                raise HTTPException(500, "No se encontró el archivo descargado de YouTube")

        result = await run_pipeline(str(wav_path), job_id)
        return {"status": "completed", "result": result, "job_id": job_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error con YouTube: %s", e)
        raise HTTPException(500, f"Error al procesar video de YouTube: {str(e)}")
    finally:
        for f in UPLOAD_DIR.glob(f"{job_id}_yt.*"):
            f.unlink(missing_ok=True)


# ──────────────────────────────────────────────
# SSE: Stream de progreso
# ──────────────────────────────────────────────

@app.get("/api/progress/{job_id}")
async def progress_stream(job_id: str):
    """Stream SSE con el progreso del job."""
    async def event_generator():
        last_status = None
        while True:
            job = jobs.get(job_id)
            if job is None:
                yield f"data: { {'status': 'not_found'} }\n\n"
                break
            status = job.get("status", "unknown")
            if status != last_status:
                yield f"data: { {'status': status, 'message': job.get('message', ''), 'progress': job.get('progress', 0)} }\n\n"
                last_status = status
            if status in ("completed", "error"):
                break
            await asyncio.sleep(2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ──────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────

async def extract_audio(video_path: str, output_path: str) -> None:
    """Extrae audio de un video usando ffmpeg."""
    import shutil
    ffmpeg_path = shutil.which("ffmpeg")
    logger.info("ffmpeg encontrado en: %s", ffmpeg_path)
    
    cmd = [
        ffmpeg_path or "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "-y", output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falló: {stderr.decode('utf-8', errors='replace')[:200]}")
    logger.info("Audio extraído del video: %s", output_path)


async def run_pipeline(audio_path: str, job_id: str) -> str:
    """
    Ejecuta el pipeline completo de forma asíncrona:
    S3 upload → Transcribe → Bedrock analysis.
    """
    jobs[job_id] = {"status": "uploading", "message": "Subiendo archivo a S3...", "progress": 10}
    clients = get_aws_clients()

    loop = asyncio.get_event_loop()

    s3_key = await loop.run_in_executor(None, upload_to_s3, clients["s3"], audio_path)

    jobs[job_id] = {"status": "transcribing", "message": "Transcribiendo audio...", "progress": 30}
    result_uri = await loop.run_in_executor(None, start_transcription, clients["transcribe"], s3_key)

    jobs[job_id] = {"status": "extracting", "message": "Procesando transcripción...", "progress": 60}
    full_text, words = await loop.run_in_executor(
        None, download_and_extract_transcript, clients["s3"], result_uri
    )

    jobs[job_id] = {"status": "analyzing", "message": "Analizando con IA...", "progress": 80}
    analysis = await loop.run_in_executor(
        None, analyze_with_bedrock, clients["bedrock"], full_text, words
    )

    output_path = save_output(analysis)

    jobs[job_id] = {"status": "completed", "message": "Análisis completado", "progress": 100}
    return analysis


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
