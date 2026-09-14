# Job Application Manager (JAM) Copilot Instructions

This repository is a personal, local-first AI-powered job application management system. Read [CLAUDE.md](../CLAUDE.md) as the detailed design manifest and source of truth. These instructions translate that manifest into implementation guidance for Copilot.

## Product Context

JAM manages the full job application lifecycle:

- Store a master resume and job descriptions.
- Accept job descriptions by pasted text or uploaded PDF.
- Generate tailored cover letters.
- Tailor an existing LaTeX CV and compile it to PDF.
- Score resume-to-job fit and produce gap analysis.
- Track applications, statuses, notes, and generated documents.
- Detect application updates from Gmail through MCP and update statuses.
- Provide a natural-language agent chat interface for querying and updating the system.

This is a single-user personal tool for private career data. It runs locally with Docker. Do not add cloud deployment, authentication, multi-user behavior, LinkedIn scraping, fine-tuning, or vector search unless the project requirements explicitly change.

## Technology Decisions

Use the existing stack and patterns:

- Python 3.10+.
- FastAPI for the HTTP API.
- SQLite with SQLAlchemy for persistence.
- LangGraph for the agent graph.
- Anthropic Claude Haiku for document generation and scoring.
- Anthropic Claude Sonnet for agent reasoning.
- OpenRouter free models for simple email intent classification.
- LangSmith for LLM tracing.
- MLflow for prompt and generation tracking.
- Gmail MCP for email retrieval.
- PyMuPDF for PDF text extraction.
- tectonic for LaTeX compilation.
- Tailwind CSS for the dashboard.
- Docker and docker-compose for local deployment.
- GitHub Actions for CI.

Prefer existing modules and helpers over new abstractions. Keep changes focused and preserve public APIs unless the task requires a contract change.

## Repository Architecture

```text
src/database/
  models.py       SQLAlchemy table definitions
  crud.py         Database reads and writes
  connection.py   SQLite engine and session factory
src/document_processing/
  resume_parser.py  Resume PDF to clean text
  jd_parser.py      Job description PDF or raw text to clean text
src/llm/
  clients.py        Anthropic and OpenRouter clients
  cover_letter.py   Cover letter generation
  cv_tailoring.py   LaTeX tailoring and tectonic compilation
  scoring.py        Resume-job scoring
  email_parser.py   Email intent classification
src/agent/
  state.py          AgentState TypedDict
  tools.py          Agent tools
  nodes.py          LangGraph node implementations
  graph.py          Graph assembly and compilation
src/tracking/
  mlflow_tracker.py MLflow logging wrapper
api/
  main.py           FastAPI application
  routers/          API route modules
  static/           Tailwind dashboard assets
 tests/             Unit and integration tests
templates/          Master LaTeX CV template, gitignored
data/resumes/      Uploaded resumes, gitignored
outputs/generated/  Generated documents, gitignored
mlruns/             Local MLflow data, gitignored
```

The repository may be partially implemented. Add missing modules in the location implied by this architecture instead of moving existing code without a clear reason.

## Model Routing: Mandatory

Never hardcode a model ID in application code. Read model names from environment variables so models can be swapped without code changes:

| Workload | Environment variable | Default |
|---|---|---|
| Cover letters | `HAIKU_MODEL` | `claude-haiku-4-5` |
| LaTeX CV tailoring | `HAIKU_MODEL` | `claude-haiku-4-5` |
| Job match scoring | `HAIKU_MODEL` | `claude-haiku-4-5` |
| Agent reasoning | `SONNET_MODEL` | `claude-sonnet-4-5` |
| Email intent parsing | `OPENROUTER_MODEL` | `meta-llama/llama-3.2-3b-instruct:free` |

Use the configured client wrappers. Keep provider-specific setup in `src/llm/clients.py`, not scattered across features.

## Context Limits

Prevent unbounded prompt and conversation growth:

- Keep at most the last 8 conversation turns, controlled by `MEMORY_WINDOW_SIZE`.
- Truncate each tool observation to at most `TOOL_RESULT_MAX_TOKENS` tokens before adding it to agent context.
- Pass the LaTeX template as a file reference or controlled content where practical, not duplicated repeatedly.
- Limit resume and job-description inputs to the first 1500 tokens when they exceed the context budget.
- Treat cover-letter generation, scoring, and CV tailoring as single-turn document tasks.
- Respect `MAX_AGENT_ITERATIONS` when executing the agent loop.

## Document Input and Generation

### Job descriptions

Support both input paths:

1. Pasted raw text stored in `job_descriptions.raw_text`.
2. Uploaded PDF parsed with PyMuPDF and stored in the same field.

Downstream features must consume `raw_text`, so they do not need to know how the job description was entered. Preserve optional company, role, URL, and source file metadata.

### LaTeX CV tailoring

The master template is `templates/cv_template.tex` and is user-provided. The tailoring pipeline must:

1. Read the master resume text and job description.
2. Read the existing LaTeX template.
3. Ask the configured Haiku model for a modified template.
4. Write the generated `.tex` output to the configured output area.
5. Compile it with tectonic.
6. If compilation fails, send the compiler error back to the model and retry, up to 3 total attempts.
7. Store the final source and compiled PDF path in `generated_documents`.

Compilation errors are expected failure cases. Preserve the error-feedback retry loop and make failures observable rather than silently returning an invalid PDF.

## LangGraph Agent

The agent uses typed state and graph-based routing. The intended flow is:

```text
parse_intent
  -> router
  -> capability tool node(s)
  -> response
  -> memory update
```

Capability nodes include:

- `generate_cover_letter_node`
- `tailor_cv_node`
- `score_match_node`
- `get_application_node`
- `update_status_node`
- `list_applications_node`
- `parse_emails_node`
- `search_applications_node`

Keep the state contract compatible with:

```python
class AgentState(TypedDict):
    messages: list[dict]
    current_task: str
    tool_results: list[dict]
    final_response: str
    error: str | None
```

When adding a LangGraph concept such as a state graph, node, edge, conditional edge, or subgraph, explain the pattern briefly before introducing it in implementation documentation or a user-facing change summary. Keep routing and tool behavior testable independently from the model provider.

## Database Contract

The main tables and important fields are:

- `resumes`: `id`, `filename`, `upload_date`, `parsed_text`, `file_path`.
- `job_descriptions`: `id`, required `company` and `role`, `upload_date`, `raw_text`, optional `file_path`, optional `url`.
- `applications`: `id`, `resume_id`, `job_id`, `date_applied`, `status`, `match_score`, `notes`, `created_at`, `updated_at`.
- `generated_documents`: `id`, `application_id`, `doc_type`, `content_text`, `file_path`, `prompt_version`, `created_at`.
- `email_events`: `id`, optional `application_id`, `received_at`, `subject`, `snippet`, `detected_intent`, optional `status_change`, and `raw_email_id`.

Application statuses are `Applied`, `Interview Scheduled`, `Interview Done`, `Offer`, `Rejected`, and `Ghosted`. Match scores range from 0.0 to 1.0. Generated document types include `cover_letter`, `cv_latex`, `cv_pdf`, and `tailoring_suggestions`.

Use CRUD functions in `src/database/crud.py` for persistence. Keep database access out of presentation code when an existing service or CRUD boundary can own it. Account for SQLite's single-user and limited-concurrency nature.

## Gmail Email Sync

Email sync should:

1. Fetch recent Gmail messages through Gmail MCP, normally from the last 7 days and filtered by known company names.
2. Classify intent with the configured OpenRouter model.
3. Map recognized intents such as interview invite, rejection, offer, or follow-up to status changes.
4. Update the related application when confidence and matching data support it.
5. Record an `email_events` row with a short snippet and detected intent.
6. Deduplicate by Gmail `raw_email_id`.
7. Expose detected changes for manual review and allow the user to override incorrect parsing.

Do not make an automatic status change impossible to audit. Preserve the source email metadata and resulting status change.

## MLflow and LangSmith

Track every LLM generation through the tracking wrapper. At minimum capture:

- Prompt template version.
- Model name.
- Relevant resume and job IDs.
- Generated output.
- Prompt used.
- Output length or equivalent useful metric.
- MLflow run ID in `generated_documents.prompt_version`.

Use LangSmith tracing for LLM calls when configured. Do not make a feature depend on credentials being present during unit tests; mock providers and keep local tests deterministic.

## API Contract

Preserve these endpoint responsibilities:

```text
POST   /resume/upload
POST   /jobs/upload
POST   /jobs/paste

POST   /applications
GET    /applications
GET    /applications/{id}
PATCH  /applications/{id}
DELETE /applications/{id}

POST   /generate/cover-letter
POST   /generate/tailor-cv
POST   /generate/score

POST   /emails/sync
GET    /emails/{application_id}

POST   /chat
DELETE /chat/{session_id}

GET    /health
```

The health response should report the state of the application, database, MLflow, and Gmail MCP integrations. Keep request and response models explicit and validate IDs, statuses, scores, file types, and required fields at the API boundary.

## Configuration and Secrets

Use `.env.example` as the documented configuration surface. Important variables include:

```text
ANTHROPIC_API_KEY
HAIKU_MODEL
SONNET_MODEL
OPENROUTER_API_KEY
OPENROUTER_MODEL
OPENROUTER_BASE_URL
LANGCHAIN_TRACING_V2
LANGCHAIN_API_KEY
LANGCHAIN_PROJECT
MLFLOW_TRACKING_URI
DATABASE_URL
TEMPLATES_DIR
OUTPUTS_DIR
DATA_DIR
MEMORY_WINDOW_SIZE
MAX_AGENT_ITERATIONS
TOOL_RESULT_MAX_TOKENS
```

Never commit `.env`, API keys, private resumes, generated career documents, Gmail contents, or database files. Keep paths configurable and compatible with Docker volume mounts.

## Docker and Local Runtime

The intended services are:

- `jam`: the FastAPI application on port 8000.
- `mlflow`: local MLflow UI/server exposed on port 5001 and backed by the shared `mlruns` volume.

The application mounts the local database, templates, outputs, data, and MLflow directories. Changes to startup, health checks, or environment handling should keep `docker-compose.yml`, `Dockerfile`, and the `/health` contract aligned.

## Testing and Quality

For relevant changes, add or update focused tests. Coverage targets include:

- SQLAlchemy database CRUD.
- PDF and raw-text document parsing.
- Structured output parsing for cover letters, scoring, and LaTeX.
- CV compilation retry behavior.
- Agent tools with mocked LLM calls.
- FastAPI endpoints and validation.
- Email deduplication and status updates.

The CI contract is:

```text
pip install -r requirements.txt
pytest tests/ -v
ruff check src/
Docker image build
Container starts and /health returns HTTP 200
```

Prefer deterministic unit tests with mocked external services. Do not require Anthropic, OpenRouter, Gmail, LangSmith, or MLflow credentials for ordinary tests.

## Delivery Phases

Maintain the intended sequence unless a dependency requires otherwise:

1. Project setup: environment, Docker skeleton, database models, CRUD, `/health`.
2. Document processing: resume and job-description parsing plus upload endpoints.
3. LLM pipelines: cover letters, scoring, CV tailoring, tectonic retry loop, MLflow.
4. LangGraph agent: state, tools, nodes, graph, `/chat`.
5. Gmail MCP: fetch, classify, status updates, deduplication, manual review.
6. GitHub Actions test and build workflow.
7. Tailwind dashboard connected to the API.
8. Docker, README, `.env.example`, and local deployment polish.

After completing a phase, summarize what was built, how it connects to the current architecture, and what the next phase depends on.

## Working Conventions

- Before creating a new component or subsystem, state what it does and why it belongs at that architectural boundary.
- Name non-obvious patterns when introducing them, especially in the agent graph.
- When asked why a design works a certain way, explain the reasoning before changing code.
- Keep edits minimal, focused, and consistent with nearby code.
- Add comments only for genuinely non-obvious logic.
- Update documentation when behavior, configuration, or API contracts change.
- Do not commit changes or create branches unless explicitly requested.
- Treat [CLAUDE.md](../CLAUDE.md) as the detailed canonical manifest when these instructions need clarification.
