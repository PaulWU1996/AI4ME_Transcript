# AI4ME Transcript Processor

A containerized FastAPI service that converts transcripts into shortform content. An external orchestrator sends a `job_id`, this service reads the transcript from a shared volume, runs it through a local Ollama LLM, and returns a catchy title + summary — also writing the result back to the shared volume.

## How it works

```
Orchestrator
    │  1. Writes  shared/{job_id}/transcript.txt
    │  2. POST /process  {"job_id": "...", "job_type": "script"}
    │  3. Reads   shared/{job_id}/output.json
    ▼
transcript-processor container
    ├── FastAPI :8000
    └── Ollama  :11434 (localhost only, models bind-mounted from host)
```

## Quick start

```bash
# 1. Copy and fill in your environment
cp .env.example .env

# 2. Build and start
docker compose up --build

# 3. Poll until ready
curl http://localhost:8000/health

# 4. Create a test job and send it
mkdir -p /tmp/ai4me_shared/test123
echo "Your transcript text here." > /tmp/ai4me_shared/test123/transcript.txt

curl -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"job_id": "test123", "job_type": "script"}'
```

## API

### `POST /process`

| Field | Type | Required | Description |
|---|---|---|---|
| `job_id` | string | yes | Orchestrator-assigned job identity |
| `job_type` | string | yes | Must be `"script"` |
| `language` | string | no | Response language, e.g. `"en"`, `"zh"` (default `"en"`) |
| `callback_url` | string | no | If set, result is POSTed here after `output.json` is written |
| `prompts` | string | no | Custom prompt override (must contain `{transcript}` and `{language}` slots) |

**Response (HTTP 200):**
```json
{
  "job_id": "test123",
  "title": "Why Morning Routines Are Secretly Rewriting Your Brain",
  "summary": "Three researchers found that habits formed before 9 AM have an outsized impact on daily productivity, driven by peak prefrontal cortex plasticity immediately after waking.",
  "model": "llama3.2:3b",
  "processing_time_ms": 4217
}
```

The same payload is written to `shared/{job_id}/output.json`.

### `GET /health`

```json
{ "status": "ok", "ollama_ready": true, "model": "llama3.2:3b" }
```

Returns HTTP 503 if Ollama is not ready. Poll this before sending the first job.

## Configuration

| Variable | Required | Example | Notes |
|---|---|---|---|
| `OLLAMA_MODEL` | yes | `llama3.2:3b` | Must be present on the mounted model volume |
| `OLLAMA_MODELS_PATH` | yes | `~/.ollama/models` | Host path, mounted read-only into the container |
| `SHARED_VOLUME_PATH_HOST` | yes | `/tmp/ai4me_shared` | Host path for shared job files |
| `SHARED_VOLUME_PATH` | no | `/shared` | Container-side path (default `/shared`) |
| `MAX_TRANSCRIPT_CHARS` | no | `0` | Character limit per request; `0` = no limit |

## Notes

- **CPU-only**: no GPU assumed. Inference on a 3B model takes 15–90 s. Set your orchestrator's HTTP timeout above 120 s.
- **Serial processing**: one request at a time. Scale by running multiple container replicas behind a load balancer.
- **Models are not bundled**: populate `OLLAMA_MODELS_PATH` on the host before starting the container.
