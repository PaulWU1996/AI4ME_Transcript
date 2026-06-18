import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import ollama_client

router = APIRouter()


def _shared_path() -> Path:
    return Path(os.environ.get("SHARED_VOLUME_PATH", "/shared"))


def _max_chars() -> int:
    return int(os.environ.get("MAX_TRANSCRIPT_CHARS", 0))


class ProcessRequest(BaseModel):
    job_id: str
    language: str = "en"


class ProcessResponse(BaseModel):
    job_id: str
    title: str
    summary: list[str]
    model: str
    processing_time_ms: int


@router.post("/process", response_model=ProcessResponse)
async def process_transcript(req: ProcessRequest):
    transcript_path = _shared_path() / req.job_id / "transcript.txt"

    if not transcript_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"transcript not found for job {req.job_id}",
        )

    transcript = transcript_path.read_text(encoding="utf-8").strip()

    if not transcript:
        raise HTTPException(status_code=422, detail="transcript.txt is empty")

    max_chars = _max_chars()
    if max_chars and len(transcript) > max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"transcript exceeds {max_chars} characters",
        )

    if not await ollama_client.is_ready():
        raise HTTPException(status_code=503, detail="Ollama service unavailable")

    try:
        result = await ollama_client.generate(transcript, req.language)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    output = {"job_id": req.job_id, **result}

    output_path = _shared_path() / req.job_id / "output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    return output


@router.get("/health")
async def health():
    ready = await ollama_client.is_ready()
    model = os.environ.get("OLLAMA_MODEL", "")
    if not ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "ollama_ready": False, "model": model},
        )
    return {"status": "ok", "ollama_ready": True, "model": model}
