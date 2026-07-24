# VoiceGuard / PaTuean — Backend

A deliberately small FastAPI backend that powers only the **genuinely-live web
features**: real user accounts and the real **Live Detector** (anti-spoof + ASR +
LLM). Everything in the "phone app" preview zone (dashboard, call history, family /
Elder Mode, settings) is **static preview data served by the frontend mock layer** —
it never touches this backend.

## Run

```bash
cd be
python3.13 -m venv .venv            # 3.11–3.13 (3.14 lacks pydantic-core wheels)
.venv/bin/pip install -r requirements.txt
cp .env.example .env                # fill in DB + the 3 detection API keys
.venv/bin/python -m app.seed        # optional: 2 demo login accounts
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Docs: http://localhost:8000/docs · Tests: `.venv/bin/python -m pytest`
Seeded logins (passwordless): `somsak@example.com`, `nok@example.com`.

> Always launch with `.venv/bin/uvicorn …` (not a bare `uvicorn`) so it uses this
> project's environment.

## Endpoints (the whole surface)

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/signup` | Create a real account → session |
| POST | `/auth/login` | Log in by phone **or** email |
| POST | `/auth/refresh` | Rotate tokens (cookie or body) |
| POST | `/demo/live-test` | **The live feature** — multipart `audio` → spoof + transcript + scam analysis. Auto-saves to the signed-in user's history. |
| GET | `/me/detector-tests` | List the user's saved Live Detector history |
| GET | `/me/detector-tests/{id}` | View one saved result (full detail) |
| DELETE | `/me/detector-tests/{id}` | Delete one history entry |
| GET | `/health` | Liveness |

There are no `/calls`, `/dashboard`, `/settings`, `/wards`, … endpoints — those
features live entirely in the frontend as static preview data.

## Database — 4 tables

SQLite for local dev, Postgres (Neon) for deploy. Tables:

| Table | What it stores |
|---|---|
| `users` | Real accounts (name, phone, email, role, consent flag) |
| `refresh_tokens` | Login sessions (rotated on refresh) |
| `anon_live_tests` | Per-IP counter for the free logged-out Live Detector limit |
| `detector_tests` | A signed-in user's saved Live Detector results (full analysis) |

The **audio is never stored** — transcoded in memory, sent to the 3 APIs, discarded.
For a **signed-in** user the *analysis* (scores, transcript, summary, intents,
reasons) is saved to `detector_tests` for their history; **anonymous** tests save
nothing but the per-IP rate-limit count.

## Detection pipeline (the 3 real models)

`app/detectors/` — one adapter per external API, orchestrated by `pipeline.py`:
webm/upload → **ffmpeg → 16 kHz mono WAV** → anti-spoof + ASR (concurrent) → LLM.

| Model | Env vars |
|---|---|
| Anti-spoof (AWS API Gateway, `x-api-key`) | `ANTISPOOF_API_URL`, `ANTISPOOF_API_KEY` |
| Typhoon ASR (OpenAI-compatible) | `ASR_API_URL`, `ASR_API_KEY`, `ASR_MODEL` |
| Thai LLM (OpenAI-compatible) | `LLM_API_URL`, `LLM_API_KEY`, `LLM_MODEL` |

Leave any `*_API_URL` blank to fall back to a deterministic stub. Empty/no-speech
transcripts short-circuit to a neutral result (no LLM hallucination on silence).

## Connect the frontend

`fe/.env`:
```
VITE_USE_MOCKS=false          # auth + live detector hit this backend
VITE_API_URL=http://localhost:8000
```
Only auth and the Live Detector call the backend; the phone preview stays on the
frontend's static mock either way. With `VITE_USE_MOCKS=true`, the Live Detector
still hits the backend (as an anonymous request) — that's why `ANON_LIVE_TEST_LIMIT`
is raised for local dev.

## Deploy (Vercel + Neon)

`api/index.py` + `vercel.json` expose the ASGI app as a serverless function. Set
Root Directory = `be`, add env vars (`DATABASE_URL` with Neon's **pooled** host,
`JWT_SECRET`, `CORS_ORIGINS`, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=none`, and the
3 detection keys). Create tables once from your machine pointed at Neon:
`.venv/bin/python -m app.seed`.
