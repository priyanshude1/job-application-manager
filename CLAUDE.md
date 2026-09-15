# Job Application Manager (JAM) — Project Design Manifest
> This file is the single source of truth for all design decisions, architectural choices, and implementation constraints for the JAM project. All Claude Code sessions must read and adhere to this document before writing any code.

---

## Project Summary

A personal AI-powered job application management system. Handles the full job application lifecycle — from tailoring documents to tracking application statuses — using LLM pipelines, a LangGraph agent, and Gmail MCP integration. Built as a local Docker application (personal tool handling private career data — no cloud deployment needed or appropriate).

Demonstrates: LangGraph, LangSmith, MLflow, GitHub Actions CI/CD, model routing across Anthropic + OpenRouter APIs, Gmail MCP, LaTeX PDF generation, and relational database design.

---

## Goals

- Generate tailored cover letters per job description
- Tailor and recompile CV as LaTeX PDF per job description
- Score job-resume match with gap analysis
- Track all applications and statuses in one dashboard
- Auto-update application status by parsing Gmail via MCP
- Agentic chatbot interface for natural language interaction with the system
- Fill portfolio gaps: LangGraph, LangSmith, MLflow, CI/CD, model routing

---

## Non-Goals

- No cloud deployment — local Docker only (personal data, zero cost)
- No multi-user support — single user, no authentication
- No LinkedIn scraping — job descriptions entered via paste or PDF upload
- No fine-tuning — inference and prompt engineering only
- No vector search — relational DB sufficient for this use case

---

## Technology Stack

| Component | Choice | Reason |
|---|---|---|
| Agent framework | LangGraph | Production-standard, fills framework gap, graph-based |
| LLM observability | LangSmith | Free tracing + monitoring per LLM call |
| Prompt tracking | MLflow | Track prompt versions + output quality per task |
| Primary LLM | Anthropic Claude Haiku | Reliable structured output, cheap, sufficient context |
| Agent LLM | Anthropic Claude Sonnet | Large context window for multi-turn agent sessions |
| Email/simple tasks | Free OpenRouter models | Classification tasks, no spend needed |
| Email integration | Gmail MCP | Auto status tracking from inbox |
| Database | SQLite + SQLAlchemy | Simple, sufficient for personal use |
| API framework | FastAPI | Standard ML API framework |
| Frontend | Tailwind CSS, Claude Code builds | Decent UI, minimal developer time |
| Containerization | Docker + docker-compose | Local deployment, portfolio signal |
| CI/CD | GitHub Actions | Automated testing on every push |
| LaTeX compilation | tectonic (Rust-based LaTeX engine) | Lightweight (~50MB vs texlive-full ~4GB), auto-downloads packages |
| Language | Python 3.10+ | Standard |

---

## Model Routing — Critical Design Decision

Different tasks routed to different models. Never hardcode a model — always read from environment variables so swapping requires zero code changes.

| Task | Model ENV VAR | Default | Context Budget | Reason |
|---|---|---|---|---|
| Cover letter generation | HAIKU_MODEL | claude-haiku-4-5 | ~4K | Reliable long-form writing |
| LaTeX CV generation | HAIKU_MODEL | claude-haiku-4-5 | ~6K | Reliable structured output |
| Job match scoring | HAIKU_MODEL | claude-haiku-4-5 | ~4K | Structured JSON output |
| Agent reasoning | SONNET_MODEL | claude-sonnet-4-5 | ~32K | Multi-turn tool use, large context |
| Email intent parsing | OPENROUTER_MODEL | meta-llama/llama-3.2-3b-instruct:free | ~1K | Simple classification, free |

All model IDs in `.env`. Never reference a model string directly in code — always `os.getenv("HAIKU_MODEL")`.

---

## Context Window Strategy

The agent reasoning loop is the only task where context growth is a concern. Mitigations:

- Rolling conversation memory: last 8 turns maximum (same as RAG v2)
- Tool observation truncation: cap each tool result at 1000 tokens before injecting into agent context
- LaTeX template: passed as a file reference, not inline text, wherever possible
- Resume and JD text: chunked to first 1500 tokens each if longer (covers all practical cases)

Document tasks (cover letter, scoring, LaTeX) are single-turn — context resets per call. No accumulation risk.

---

## Job Description Input

Two methods, both supported:

**Paste raw text** — textarea in the UI, text stored directly in `job_descriptions.raw_text`

**Upload PDF** — parsed with PyMuPDF (same library as RAG project), text extracted and stored in `job_descriptions.raw_text`

Both methods produce the same stored artifact. Downstream LLM tasks always read from `raw_text` — input method is irrelevant after storage.

---

## LaTeX CV Strategy

User provides their existing LaTeX CV template once at setup. Stored in `./templates/cv_template.tex`.

At tailoring time:
1. LLM reads the master resume text + job description
2. LLM receives the existing LaTeX template as context
3. LLM outputs a modified version of the template with tailored content
4. tectonic compiles the `.tex` file to PDF
5. If compilation fails, retry loop: LLM receives the error message and corrects the LaTeX (max 3 retries)
6. Final PDF stored in `./outputs/` and linked in the database

The retry loop with error feedback is essential — LLM-generated LaTeX will occasionally have syntax errors. Passing the compiler error back to the LLM and asking it to fix usually resolves in 1-2 retries.

---

## LangGraph Agent Architecture

The agent is a graph with nodes for each capability. LangGraph manages state, transitions, and tool dispatch.

```
Entry node: parse_intent
        ↓
Router node: decides which tool node to activate
        ↓
Tool nodes (parallel where possible):
    generate_cover_letter_node
    tailor_cv_node
    score_match_node
    get_application_node
    update_status_node
    list_applications_node
    parse_emails_node
    search_applications_node
        ↓
Response node: format and return final answer
        ↓
Memory node: update conversation history
```

State object passed between nodes:
```python
class AgentState(TypedDict):
    messages:        list[dict]       # conversation history
    current_task:    str              # what the agent is doing
    tool_results:    list[dict]       # accumulated tool outputs this turn
    final_response:  str              # populated by response node
    error:           str | None       # populated if any node fails
```

---

## Database Schema (SQLite via SQLAlchemy)

```sql
resumes
    id              INTEGER PRIMARY KEY
    filename        TEXT
    upload_date     DATETIME
    parsed_text     TEXT
    file_path       TEXT

job_descriptions
    id              INTEGER PRIMARY KEY
    company         TEXT NOT NULL
    role            TEXT NOT NULL
    upload_date     DATETIME
    raw_text        TEXT
    file_path       TEXT (nullable — only if uploaded as PDF)
    url             TEXT (nullable — paste the job URL for reference)

applications
    id                    INTEGER PRIMARY KEY
    resume_id             INTEGER FK → resumes.id
    job_id                INTEGER FK → job_descriptions.id
    submission_method     TEXT  -- manual|automatic (automatic reserved for a future
                          automated-submission feature; no special logic yet)
    submitted_at          DATETIME NOT NULL  -- when actually submitted; defaults to
                          now at creation, can be explicitly backdated
    status                TEXT  -- Applied|Interview Scheduled|Interview Done|Offer|Rejected|Ghosted
    match_score           REAL  -- 0.0 to 1.0; denormalized snapshot copied from the latest
                          generated_documents(doc_type='score') row for this resume_id+job_id
                          at application-creation time
    notes                 TEXT
    confirmed_at          DATETIME  -- nullable; set once the submission is confirmed
    confirmation_source   TEXT  -- nullable; 'email' or 'manual'
    created_at            DATETIME
    updated_at            DATETIME

generated_documents
    id              INTEGER PRIMARY KEY
    application_id  INTEGER FK → applications.id (nullable — set once the resume/job
                    pair is actually submitted; NULL while still a pre-submission prep artifact)
    resume_id       INTEGER FK → resumes.id
    job_id          INTEGER FK → job_descriptions.id
    doc_type        TEXT  -- cover_letter|cv_latex|cv_pdf|score
    content_text    TEXT  -- raw text, LaTeX source, or (doc_type='score') gap-analysis text
    match_score     REAL  -- nullable; 0.0 to 1.0, only for doc_type='score' rows — produced
                    together with content_text's gap analysis by one score_match() call
    file_path       TEXT  -- path to compiled PDF if applicable
    prompt_version  TEXT  -- MLflow run ID for this generation
    created_at      DATETIME

email_events
    id              INTEGER PRIMARY KEY
    application_id  INTEGER FK → applications.id (nullable — may not match)
    received_at     DATETIME
    subject         TEXT
    snippet         TEXT  -- first 200 chars of email body
    detected_intent TEXT  -- interview_invite|rejection|offer|follow_up|submission_confirmation|unknown
    status_change   TEXT  -- what status was set as a result (nullable)
    raw_email_id    TEXT  -- Gmail message ID for deduplication
```

**An `applications` row exists only once you've actually submitted** — there is no earlier "considering"/"queued" stage in this table. A resume + job description existing (via `resumes`/`job_descriptions`) is enough to prepare for a job; it does not by itself mean you applied. Cover letters, tailored CVs, and match scores generated during that prep phase live in `generated_documents`, keyed directly on `(resume_id, job_id)` — not on an application, since none may exist yet. When you do submit and an `applications` row is created, any `generated_documents` rows still unlinked (`application_id IS NULL`) for that same `(resume_id, job_id)` pair are automatically backfilled onto it, and the newest `doc_type='score'` row's `match_score` is copied onto the new application as a queryable snapshot.

---

## MLflow Usage

Track every LLM generation call as an experiment run. Not just training metrics — prompt versioning.

```python
with mlflow.start_run(run_name="cover_letter_v2"):
    mlflow.log_param("prompt_template_version", "v2")
    mlflow.log_param("model", os.getenv("HAIKU_MODEL"))
    mlflow.log_param("job_id", job_id)
    mlflow.log_param("resume_id", resume_id)
    mlflow.log_text(generated_cover_letter, "output.txt")
    mlflow.log_text(prompt_used, "prompt.txt")
    mlflow.log_metric("output_length_tokens", len(output.split()))
```

The `prompt_version` field in `generated_documents` stores the MLflow run ID — linking every generated document back to the exact prompt and model that produced it. This enables:

- Comparing prompt versions side by side in MLflow UI
- Identifying which prompt version produces the best cover letters
- Full reproducibility — regenerate any document with the same inputs

MLflow tracking server runs locally via docker-compose. UI accessible at `localhost:5001`.

---

## Gmail MCP Integration

Gmail MCP is already connected in Claude Code. Used for email status auto-tracking.

Flow:
1. Agent calls `parse_emails` tool
2. Tool uses Gmail MCP to fetch recent emails (last 7 days, filtered by known company names from `job_descriptions` table)
3. Each email passed to OpenRouter free model for intent classification
4. Detected intents trigger status updates in `applications` table
5. Email event logged in `email_events` table with snippet and detected intent

Deduplication: `raw_email_id` (Gmail message ID) prevents the same email being processed twice.

Manual review: all auto-detected status changes shown in dashboard with email snippet — user can override if parsing was wrong.

Submission confirmation: a detected intent of `submission_confirmation` — a company confirming a submission actually went through — is handled distinctly from status-change intents. Since confirmation rarely arrives for every application, it isn't required to create the `applications` row (that already happened at submission time); when matched, it instead `PATCH`es the existing `/applications/{id}` with `confirmed_at`/`confirmation_source='email'`, the same endpoint a manual "no email arrived, I'm confirming it myself" action uses.

---

## GitHub Actions CI/CD

`.github/workflows/test.yml` runs on every push to any branch:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - checkout
      - setup Python 3.11
      - pip install -r requirements.txt
      - run: pytest tests/ -v
      - run: ruff check src/

  build:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - checkout
      - build Docker image
      - verify container starts and /health returns 200
```

Test coverage targets:
- Database CRUD operations
- Document parsing (PDF + text)
- LLM output parsing (cover letter, scoring, LaTeX)
- Agent tool functions (mocked LLM calls)
- FastAPI endpoints

---

## Project Structure

```
job-application-manager/
├── templates/
│   └── cv_template.tex            ← user's existing LaTeX CV template (gitignored)
├── data/
│   └── resumes/                   ← uploaded resume PDFs (gitignored)
├── outputs/
│   └── generated/                 ← compiled PDFs and generated documents (gitignored)
├── src/
│   ├── database/
│   │   ├── models.py              ← SQLAlchemy table definitions
│   │   ├── crud.py                ← all DB read/write operations
│   │   └── connection.py          ← SQLite engine + session factory
│   ├── document_processing/
│   │   ├── resume_parser.py       ← PDF → clean text
│   │   └── jd_parser.py           ← PDF or raw text → clean text
│   ├── llm/
│   │   ├── clients.py             ← Anthropic + OpenRouter client setup
│   │   ├── cover_letter.py        ← cover letter generation pipeline
│   │   ├── cv_tailoring.py        ← LaTeX modification + tectonic compilation
│   │   ├── scoring.py             ← job match scoring pipeline
│   │   └── email_parser.py        ← email intent classification
│   ├── agent/
│   │   ├── state.py               ← AgentState TypedDict
│   │   ├── tools.py               ← all 8 tool functions
│   │   ├── nodes.py               ← LangGraph node definitions
│   │   └── graph.py               ← LangGraph graph assembly + compilation
│   └── tracking/
│       └── mlflow_tracker.py      ← MLflow logging wrapper
├── api/
│   ├── main.py                    ← FastAPI app + all endpoints
│   ├── routers/
│   │   ├── applications.py        ← /applications CRUD endpoints
│   │   ├── documents.py           ← /resume, /jobs upload endpoints
│   │   ├── generate.py            ← /generate/* LLM task endpoints
│   │   └── agent.py               ← /chat agent endpoint
│   └── static/
│       └── index.html             ← Tailwind dashboard UI
├── tests/
│   ├── test_database.py
│   ├── test_document_processing.py
│   ├── test_llm_pipelines.py
│   └── test_agent_tools.py
├── .github/
│   └── workflows/
│       └── test.yml               ← CI/CD pipeline
├── mlruns/                        ← MLflow local tracking (gitignored)
├── jam.db                         ← SQLite database (gitignored)
├── Dockerfile
├── docker-compose.yml             ← JAM app + MLflow UI
├── .env.example
├── .env                           ← gitignored
├── requirements.txt
├── CLAUDE.md                      ← this file
└── README.md
```

---

## FastAPI Endpoints

```
# Documents
POST /resume/upload              → parse + store resume PDF
POST /jobs/upload                → parse + store job description PDF
POST /jobs/paste                 → store raw text job description

# Applications
POST   /applications             → create new application record (requires an actual
                                    submission — submitted_at defaults to now if omitted)
GET    /applications             → list all with filters (status, min_score, company)
GET    /applications/{id}        → single application with all documents
PATCH  /applications/{id}        → update status, notes, match_score, confirmed_at,
                                    confirmation_source
DELETE /applications/{id}        → remove application

# Generation
POST /generate/cover-letter      → body: {resume_id, job_id}
POST /generate/tailor-cv         → body: {resume_id, job_id}
POST /generate/score             → body: {resume_id, job_id}

# Email
POST /emails/sync                → trigger Gmail MCP fetch + parse + status updates
GET  /emails/{application_id}    → list email events for one application

# Agent
POST /chat                       → body: {message, session_id}
DELETE /chat/{session_id}        → clear conversation memory

# System
GET  /health                     → {status, db, mlflow, gmail_mcp}
```

---

## Environment Variables

```
# Anthropic
ANTHROPIC_API_KEY=your_key_here
HAIKU_MODEL=claude-haiku-4-5
SONNET_MODEL=claude-sonnet-4-5

# OpenRouter (free models)
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=meta-llama/llama-3.2-3b-instruct:free
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key_here
LANGCHAIN_PROJECT=job-application-manager

# MLflow
MLFLOW_TRACKING_URI=http://localhost:5001

# Database
DATABASE_URL=sqlite:///./jam.db

# Paths
TEMPLATES_DIR=./templates
OUTPUTS_DIR=./outputs
DATA_DIR=./data

# Agent
MEMORY_WINDOW_SIZE=8
MAX_AGENT_ITERATIONS=10
TOOL_RESULT_MAX_TOKENS=1000
```

---

## Docker Compose Services

```yaml
services:
  jam:
    build: .
    ports: ["8000:8000"]
    volumes:
      - ./jam.db:/app/jam.db
      - ./templates:/app/templates
      - ./outputs:/app/outputs
      - ./data:/app/data
      - ./mlruns:/app/mlruns
    env_file: .env

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    ports: ["5001:5000"]
    volumes:
      - ./mlruns:/mlflow/mlruns
    command: mlflow server --host 0.0.0.0 --port 5000 --backend-store-uri /mlflow/mlruns
```

Two services: the JAM app and a local MLflow tracking server. Both share the `mlruns/` volume.

---

## Build Phases

```
Phase 1 (2 days):   Project setup — repo, venv, Docker skeleton,
                    database models, SQLAlchemy CRUD, /health endpoint

Phase 2 (2 days):   Document processing — resume parser, JD parser
                    (paste + PDF), file storage, upload endpoints

Phase 3 (3 days):   LLM pipelines — cover letter, scoring, LaTeX CV
                    with tectonic compilation + retry loop, MLflow tracking

Phase 4 (3 days):   LangGraph agent — state, tools, nodes, graph assembly,
                    LangSmith tracing, /chat endpoint

Phase 5 (2 days):   Gmail MCP email parsing — fetch, classify,
                    auto status updates, deduplication

Phase 6 (1 day):    GitHub Actions CI/CD — test + build workflow

Phase 7 (2 days):   Frontend dashboard — Tailwind UI, Claude Code builds,
                    developer reviews and connects to endpoints

Phase 8 (1 day):    Docker polish — docker-compose final, README,
                    .env.example, deployment instructions
```

Total: ~16 days. Buffer for debugging built into each phase estimate.

---

## Known Limitations

- SQLite not suitable for concurrent writes — single user only
- LLM-generated LaTeX may fail compilation — retry loop mitigates but doesn't eliminate
- Email intent parsing may misclassify ambiguous responses — manual override available
- tectonic requires internet on first run to download LaTeX packages (~50MB)
- OpenRouter free models have rate limits and may change availability
- Anthropic model names subject to change — always configurable via env vars
- MLflow local server — not accessible outside Docker network without extra config
- `submission_method='automatic'` is reserved for a future automated-submission feature — no
  automatic-submission logic is implemented; all applications today are created with
  `submission_method='manual'`

---

## Portfolio Signal — What This Demonstrates

- LangGraph agent with typed state and graph-based tool dispatch
- LangSmith production observability — every LLM call traced
- MLflow prompt experiment tracking — prompt versioning as MLOps practice
- Model routing — different LLMs for different task types, env-var configurable
- Gmail MCP integration — real-world external service connection
- Relational database design with SQLAlchemy ORM
- LaTeX PDF generation with compiler error feedback loop
- GitHub Actions CI/CD — automated test + build on every push
- Docker multi-service deployment (app + MLflow)
- FastAPI with organised router structure
- Tailwind frontend built by Claude Code — demonstrates agentic coding workflow

---

## Claude Code Session Rules

- Before writing any new component, explain in 3-4 sentences what it does
  and why it exists in the architecture
- When introducing a new LangGraph concept (StateGraph, node, edge,
  subgraph), explain it once clearly before using it in code
- When I ask "why", stop coding and explain fully before continuing
- Never introduce a pattern without naming it
  (e.g. "this is the supervisor pattern", "this is a conditional edge")
- After each phase, summarise what was built and how it connects
  to what comes next

*Status: Full design manifest. Ready for Phase 1 implementation.*
