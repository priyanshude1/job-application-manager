from contextlib import contextmanager
from types import SimpleNamespace

from src.tracking.mlflow_tracker import log_generation_run


class FakeTracker:
    def __init__(self):
        self.tracking_uri = None
        self.experiment = None
        self.run_name = None
        self.params: dict[str, object] = {}
        self.texts: dict[str, str] = {}
        self.metrics: dict[str, float] = {}

    def set_tracking_uri(self, uri):
        self.tracking_uri = uri

    def set_experiment(self, name):
        self.experiment = name

    @contextmanager
    def start_run(self, run_name):
        self.run_name = run_name
        yield SimpleNamespace(info=SimpleNamespace(run_id="fake-run-id-123"))

    def log_param(self, key, value):
        self.params[key] = value

    def log_text(self, text, artifact_file):
        self.texts[artifact_file] = text

    def log_metric(self, key, value):
        self.metrics[key] = value


def test_log_generation_run_logs_expected_params_artifacts_and_metric():
    tracker = FakeTracker()

    run_id = log_generation_run(
        run_name="cover_letter_v1",
        prompt_template_version="v1",
        job_id=7,
        resume_id=3,
        prompt_used="Write a cover letter for Acme.",
        output_text="Dear Acme hiring team, I am a strong fit.",
        tracker=tracker,
    )

    assert run_id == "fake-run-id-123"
    assert tracker.run_name == "cover_letter_v1"
    assert tracker.experiment == "job-application-manager"
    assert tracker.params["prompt_template_version"] == "v1"
    assert tracker.params["job_id"] == 7
    assert tracker.params["resume_id"] == 3
    assert "model" in tracker.params
    assert tracker.texts["prompt.txt"] == "Write a cover letter for Acme."
    assert tracker.texts["output.txt"] == "Dear Acme hiring team, I am a strong fit."
    assert tracker.metrics["output_length_tokens"] == 9


def test_log_generation_run_logs_extra_params_and_metrics():
    tracker = FakeTracker()

    log_generation_run(
        run_name="score_v1",
        prompt_template_version="v1",
        job_id=1,
        resume_id=1,
        prompt_used="prompt",
        output_text="output",
        extra_params={"doc_type": "score"},
        extra_metrics={"match_score": 0.75},
        tracker=tracker,
    )

    assert tracker.params["doc_type"] == "score"
    assert tracker.metrics["match_score"] == 0.75


def test_log_generation_run_does_not_import_mlflow_when_tracker_is_injected(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "mlflow":
            raise AssertionError("real mlflow should not be imported when tracker is injected")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    log_generation_run(
        run_name="run",
        prompt_template_version="v1",
        job_id=1,
        resume_id=1,
        prompt_used="prompt",
        output_text="output",
        tracker=FakeTracker(),
    )
