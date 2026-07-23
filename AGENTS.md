# AGENTS.md

## Cursor Cloud specific instructions

### Overview
Single Python **FastAPI** service ("Agent Platform PoC"). One HTTP API (`POST /v1/chat`) that branches between an `echo` stub engine and a `multi_agent` rules-based pipeline (router → search → analyst → reviewer → synthesize). Fully self-contained: web search falls back to mock fixtures when `WEB_SEARCH_API_KEY` is empty, data analysis reads `samples/mini.csv`, and runs persist to a disk-backed SQLite file (`data/runs.db`, auto-created). No external DB server, no API keys required to run end-to-end.

### Environment
- The update script creates a virtualenv at `.venv/` and installs `requirements.txt`. Always use `.venv/bin/python` / `.venv/bin/uvicorn` (the base image has `python3` only — no `python` on PATH).
- Copy env template before first run: `cp .env.example .env` (the `.env` file is gitignored; empty API keys are fine — engines run in mock/rules-only mode).

### Run (dev)
- Start the server: `.venv/bin/uvicorn app.main:app --reload --port 8000`
- Health check: `GET http://127.0.0.1:8000/health` → `{"ok": true, "version": "0.1.0"}`
- Interactive API docs (Swagger): `http://127.0.0.1:8000/docs`

### Test
- No test framework/lint config exists (README lists ruff/mypy cache dirs but no configs are committed). "Tests" are two smoke scripts that require the server running on port 8000:
  - `.venv/bin/python scripts/smoke_chat.py` — verifies `/health` + echo vs multi_agent registry branching + domain errors.
  - `.venv/bin/python scripts/smoke_s1.py` — mixed web+CSV question, `tenant=internal`.

### Notes / gotchas
- README quick-start commands are Windows-style (`.venv\Scripts\activate`, `copy`); use POSIX equivalents on Linux.
- Build step: none (interpreted Python).
- Not yet implemented in v0.1: frontend, auth, real RAG, HITL approval API. LLM env vars exist but no LLM HTTP call is wired — the pipeline is rules-only regardless.
