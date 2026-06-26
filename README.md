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
# 1. Edit docker-compose.yml and set OLLAMA_MODEL to the model you want to use

# 2. Build and start
#    First run: the container will automatically pull OLLAMA_MODEL into ./weights/ollama
#    if it isn't already there (requires internet access, may take a few minutes).
docker compose up --build

# 3. Poll until ready
curl http://localhost:8000/health

# 4. Create a test job and send it
mkdir -p ./shared/test123
echo "Your transcript text here." > ./shared/test123/transcript.txt

curl -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"job_id": "test123", "job_type": "script"}'

# With a custom prompt (overrides the default template):
curl -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{
    "job_id": "test123",
    "job_type": "script",
    "prompts": "Read this transcript and respond ONLY in this JSON format:\n{{\"title\": \"<one catchy sentence>\", \"summary\": \"<one paragraph>\"}}\n\nTranscript:\n---\n{transcript}\n---"
  }'

# With a callback URL (result is POSTed there after processing):
curl -X POST http://localhost:8000/process \
  -H 'Content-Type: application/json' \
  -d '{"job_id": "test123", "job_type": "script", "callback_url": "http://orchestrator-host/jobs/test123/done"}'
```

## API

### `POST /process`

| Field | Type | Required | Description |
|---|---|---|---|
| `job_id` | string | yes | Orchestrator-assigned job identity |
| `job_type` | string | yes | Must be `"script"` |
| `language` | string | no | Response language, e.g. `"en"`, `"zh"` (default `"en"`) |
| `callback_url` | string | no | If set, result is POSTed here after `output.json` is written |
| `prompts` | string | no | Custom prompt override; must contain `{transcript}` and `{language}` slots |

**Response (HTTP 200):**
```json
{
  "job_id": "test123",
  "title": "Why Morning Routines Are Secretly Rewriting Your Brain",
  "summary": "Researchers found that habits formed before 9 AM have an outsized impact on daily productivity, driven by peak prefrontal cortex plasticity immediately after waking.",
  "model": "llama3.2:3b",
  "processing_time_ms": 4217
}
```

The same payload is written to `shared/{job_id}/output.json`.

**Error responses:**

| Status | Condition |
|---|---|
| 404 | `transcript.txt` not found for the given `job_id` |
| 413 | Transcript exceeds `MAX_TRANSCRIPT_CHARS` limit |
| 422 | `job_type` is not `"script"`, or transcript is empty |
| 503 | Ollama is not ready |

### `GET /health`

```json
{ "status": "ok", "ollama_ready": true, "model": "llama3.2:3b" }
```

Returns HTTP 503 if Ollama is not ready. Poll this before sending the first job.

## Composing with the orchestrator

Build the image once from this repo, then reference it by name in the orchestrator's `docker-compose.yml` — no source code needed on the orchestrator side.

**Step 1 — Build the image:**
```bash
docker compose build
```

**Step 2 — Add this snippet to the orchestrator's `docker-compose.yml`:**
```yaml
  transcript-processor:
    image: ai4me-transcript:latest
    container_name: transcript-processor
    ports:
      - "8000:8000"
    volumes:
      - ./weights/ollama:/root/.ollama/models
      - ./shared:/shared
    environment:
      - OLLAMA_MODEL=llama3.2:3b
      - SHARED_VOLUME_PATH=/shared
      - UVICORN_WORKERS=1
      - UVICORN_LOG_LEVEL=info
      - MAX_TRANSCRIPT_CHARS=0
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
    restart: unless-stopped
```

If distributing across machines, push to a registry first:
```bash
docker tag ai4me-transcript:latest your-registry/ai4me-transcript:latest
docker push your-registry/ai4me-transcript:latest
```
Then update `image:` in the snippet above to match the registry path.

## Configuration

All values are hardcoded in `docker-compose.yml` — no `.env` file needed. The only line you'll typically change is `OLLAMA_MODEL`.

| Variable | Default | Notes |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.2:3b` | Model tag; pulled automatically on first run if missing |
| `SHARED_VOLUME_PATH` | `/shared` | Container-side path — matches `./shared` mount |
| `MAX_TRANSCRIPT_CHARS` | `0` | Character limit per request; `0` = no limit |

## Notes

- **CPU-only**: no GPU assumed. Inference on a 3B model takes 15–90 s. Set your orchestrator's HTTP timeout above 120 s.
- **Serial processing**: one request at a time. Scale by running multiple container replicas behind a load balancer.
- **Models are not bundled in the image**: stored in `./weights/ollama`, pulled automatically on first run.
