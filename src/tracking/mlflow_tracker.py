import os
from types import ModuleType
from typing import Any

MLFLOW_EXPERIMENT_NAME = "job-application-manager"


def log_generation_run(
    *,
    run_name: str,
    prompt_template_version: str,
    job_id: int,
    resume_id: int,
    prompt_used: str,
    output_text: str,
    extra_params: dict[str, Any] | None = None,
    extra_metrics: dict[str, float] | None = None,
    tracker: ModuleType | None = None,
) -> str:
    """Log one LLM generation call to MLflow and return its run ID.

    The returned run ID is stored in generated_documents.prompt_version, linking
    every generated document back to the exact prompt, model, and inputs that
    produced it. This is what makes any document reproducible and lets prompt
    template versions be compared side by side in the MLflow UI.

    `tracker` defaults to the real mlflow module (imported lazily, like the LLM
    clients in src/llm/clients.py, so importing this module doesn't require
    mlflow to be installed) but is injectable so callers (tests) can swap in a
    fake tracker without a live tracking server or writes to the mlruns/
    directory.
    """
    if tracker is None:
        # MLflow's own defaults (7 retries, exponential backoff, 120s/request)
        # are tuned for tolerating a rate-limited *remote* server -- wrong for
        # this project, where "the local MLflow container isn't running" is the
        # common case, not a transient blip. Without this, a single failed
        # call can block for minutes before log_generation_run_safe's
        # try/except ever gets a chance to catch anything. setdefault() so a
        # deployment that genuinely wants MLflow's resilient retries can still
        # override these via its own environment.
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
        os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "2")
        import mlflow as tracker

    tracker.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001"))
    tracker.set_experiment(MLFLOW_EXPERIMENT_NAME)

    with tracker.start_run(run_name=run_name) as run:
        tracker.log_param("prompt_template_version", prompt_template_version)
        tracker.log_param("model", os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001"))
        tracker.log_param("job_id", job_id)
        tracker.log_param("resume_id", resume_id)
        for key, value in (extra_params or {}).items():
            tracker.log_param(key, value)

        tracker.log_text(prompt_used, "prompt.txt")
        tracker.log_text(output_text, "output.txt")
        tracker.log_metric("output_length_tokens", len(output_text.split()))
        for key, value in (extra_metrics or {}).items():
            tracker.log_metric(key, value)

        return run.info.run_id


def log_generation_run_safe(
    *,
    run_name: str,
    resume_id: int,
    job_id: int,
    output_text: str,
    prompt_template_version: str = "v1",
) -> str | None:
    """Best-effort wrapper around log_generation_run: returns the run id, or
    None if MLflow itself is unreachable/misconfigured.

    MLflow is optional local infrastructure -- a generated document must stay
    usable even if the tracking server is down, so failures here are
    swallowed rather than propagated. This is the single place both
    api/routers/generate.py and src/agent/tools.py call, so a document
    created via the direct API and one created via the chat agent get the
    same MLflow lineage instead of silently diverging.
    """
    try:
        return log_generation_run(
            run_name=run_name,
            prompt_template_version=prompt_template_version,
            job_id=job_id,
            resume_id=resume_id,
            prompt_used=f"{run_name} for resume_id={resume_id}, job_id={job_id}",
            output_text=output_text,
        )
    except Exception:
        return None
