import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import ollama_client

logger = logging.getLogger(__name__)

router = APIRouter()


def _shared_path() -> Path:
    return Path(os.environ.get("SHARED_VOLUME_PATH", "/shared"))


def _max_chars() -> int:
    return int(os.environ.get("MAX_TRANSCRIPT_CHARS", 0))


class ProcessRequest(BaseModel):
    job_id: str
    job_type: str = "script"
    callback_url: Optional[str] = None
    prompts: Optional[str] = None
    language: str = "en"


class ProcessResponse(BaseModel):
    job_id: str
    title: str
    summary: str
    model: str
    processing_time_ms: int


async def _fire_callback(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.warning("callback to %s failed: %s", url, exc)


@router.post("/process", response_model=ProcessResponse)
async def process_transcript(req: ProcessRequest):
    if req.job_type != "script":
        raise HTTPException(
            status_code=422,
            detail=f"job_type '{req.job_type}' is not handled by this service",
        )

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
        result = await ollama_client.generate(transcript, req.language, custom_prompt=req.prompts)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    output = {"job_id": req.job_id, **result}

    output_path = _shared_path() / req.job_id / "output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    if req.callback_url:
        await _fire_callback(req.callback_url, output)

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
