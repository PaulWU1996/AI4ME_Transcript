import json
import os
import re
import time
from pathlib import Path

import httpx

OLLAMA_BASE_URL = "http://localhost:11434"

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_DEFAULT_REQUIREMENTS = (_PROMPTS_DIR / "transcript.txt").read_text()
_OUTPUT_STRUCTURE = (_PROMPTS_DIR / "output_structure.txt").read_text()


async def is_ready() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


def _build_prompt(transcript: str, language: str, custom_requirements: str | None) -> str:
    requirements = custom_requirements if custom_requirements is not None else _DEFAULT_REQUIREMENTS
    # format_map only on requirements — keeps {language} slot; transcript is concatenated
    # directly to avoid KeyError if transcript text contains { } characters
    rendered_requirements = requirements.format_map({"language": language})
    return (
        "<system>\n"
        + rendered_requirements
        + "\n"
        + _OUTPUT_STRUCTURE
        + "</system>\n\n"
        "<user>\n"
        "Transcript:\n"
        "---\n"
        + transcript
        + "\n---\n\n"
        "Produce the JSON output now.\n"
        "</user>"
    )


async def generate(transcript: str, language: str = "en", custom_prompt: str | None = None) -> dict:
    model = os.environ["OLLAMA_MODEL"]
    prompt = _build_prompt(transcript, language, custom_prompt)

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
        "summary": data["summary"],
        "model": model,
        "processing_time_ms": elapsed_ms,
    }
