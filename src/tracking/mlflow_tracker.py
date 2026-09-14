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
