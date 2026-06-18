import json
import os
import re
import time
from pathlib import Path

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"
_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "transcript.txt").read_text()


async def is_ready() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def generate(transcript: str, language: str = "en") -> dict:
    model = os.environ["OLLAMA_MODEL"]
    prompt = _PROMPT_TEMPLATE.format_map({"transcript": transcript, "language": language})

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
        response.raise_for_status()

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    raw = response.json()["response"]

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"Model did not return valid JSON. Raw output: {raw!r}")

    data = json.loads(match.group())

    if "title" not in data or "summary" not in data:
        raise ValueError(f"Model JSON missing required fields. Got: {data}")

    return {
        "title": str(data["title"]),
        "summary": [str(p) for p in data["summary"]],
        "model": model,
        "processing_time_ms": elapsed_ms,
    }
