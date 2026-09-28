# Job Application Manager (JAM)

A personal AI-powered job application tracker: tailors cover letters and CVs per job description, scores resume/job match, tracks applications through their lifecycle, auto-updates status from Gmail, and offers a LangGraph-based chat agent over all of it. See [`CLAUDE.md`](./CLAUDE.md) for the full architecture and design rationale — this file is just "how do I run it."

## Prerequisites

- Python 3.11+
- [`tectonic`](https://tectonic-typesetting.github.io/) on your `PATH` (compiles the generated LaTeX CVs/cover letters to PDF). Not always available via a package manager — the reliable fallback is downloading the prebuilt binary for your OS directly from the [releases page](https://github.com/tectonic-typesetting/tectonic/releases) and putting it somewhere on `PATH`.
- Docker + Docker Compose, only if you want the containerized setup.
- An Anthropic API key and an OpenRouter API key (free tier is fine for OpenRouter).
- A Google Cloud project with the Gmail API enabled, if you want email auto-sync (optional — everything else works without it).

## Local setup

```bash
python -m venv venv
venv\Scripts\activate        # or: source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env         # then fill in real values
```

Run it:

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **http://localhost:8000/**.

Run the tests and linter (same commands CI runs):

```bash
pytest tests/ -v
ruff check src/
```

## Gmail API setup (optional)

Email auto-sync needs a one-time OAuth consent — it can't run headlessly, so **do this locally, not inside Docker**, before you ever start the container.

1. In [Google Cloud Console](https://console.cloud.google.com): create a project, enable the **Gmail API**.
2. **APIs & Services → OAuth consent screen**: User type "External," add your own Gmail address under **Test users** (required — an account not on this list gets a 403, even for your own app), leave publishing status as "Testing."
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**, application type **Desktop app**. Download the resulting JSON as `data/gmail_credentials.json`.
4. Trigger the one-time consent flow (opens a browser):
   ```bash
   python -c "from src.integrations.gmail_client import get_gmail_service; get_gmail_service()"
   ```
   This caches a refresh token at `data/gmail_token.json`. Every call after this is silent — no browser involved.

Note: because the app is in "Testing" publishing status (required — this restricted scope can't reasonably be verified for production by Google for a personal project), the refresh token expires after about 7 days. When email sync starts failing auth, just rerun step 4.

## Docker

```bash
docker-compose up --build
```

This starts the app (port 8000) and a local MLflow tracking server (port 5001). Two things worth knowing:

- **Secrets and personal data are never baked into the image** — `.dockerignore` explicitly excludes `.env`, `data/gmail_credentials.json`, `data/gmail_token.json`, your resume, your CV template, and any generated output PDFs. They reach the running container only through `docker-compose.yml`'s `env_file: .env` and volume mounts (`./data:/app/data`, etc.), which is also exactly why the Gmail OAuth step above must happen locally first — the resulting `data/gmail_token.json` gets picked up by that volume mount, so the container reuses your already-authenticated session instead of needing (and being unable) to run the browser flow itself.
- `tectonic` is installed inside the image at build time (see the `Dockerfile`) — this was verified by actually compiling a real LaTeX document inside a built container, not just checking the binary exists.

## CI

`.github/workflows/test.yml` runs on every push: installs dependencies, runs the full test suite and `ruff`, then (if that passes) builds the Docker image and confirms the container actually starts and `/health` returns 200. None of this needs real API keys — every external call in this codebase (Anthropic, OpenRouter, Gmail, MLflow) is dependency-injected, so tests run entirely against fakes.
