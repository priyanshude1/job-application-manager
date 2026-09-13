---
name: model-routing-drift-check
description: Audits a documented task-to-model routing table (which LLM/model handles which task, and why) against what the code actually calls, and checks for deprecation and failure risk in how models are configured. Use for any project that routes different tasks to different LLM providers/models. Invoke explicitly — this skill does not auto-trigger.
disable-model-invocation: true
---

# Model-Routing Drift Check

## Why this exists

A routing table ("task X uses model Y because Z") is a snapshot of a decision, not an enforced constraint. Nothing keeps the code honoring it after the first refactor — someone hardcodes a different model ID during debugging and forgets to revert, a provider deprecates a model ID and the pipeline starts erroring (or silently falling back to something else), or dev and prod quietly end up pointing at different models for the same task. None of this shows up as a crash most of the time; it shows up as output quality that's subtly different from what was designed and tested.

This is a report-only review. It never edits code — it produces a findings list.

## When to run this

Run it against any project where more than one task is routed to a model, and the routing is meant to follow a documented rule (a table, a config file, a README section) rather than being called ad hoc per task. Most valuable right after any change to model config, before a demo, or periodically if the provider(s) involved are known for frequent model deprecations.

## The five checks

**1. Table-to-code fidelity** — For each task listed in the documented routing table, does the actual call site use the model the table says it should? Look for: hardcoded model IDs that bypass the documented config, tasks that exist in code but aren't in the table (undocumented routing), and tasks in the table with no corresponding call site (stale documentation).

**2. Model currency / deprecation risk** — Is each model ID read from a configurable place (env var, config file) rather than hardcoded inline in call sites? Is there any indication (a version suffix, a known sunset date, a provider deprecation notice) that a configured model ID is on a deprecation path?

**3. Fallback on failure** — If a configured model is unavailable, rate-limited, or returns an error, does the code have a defined fallback (a secondary model, a retry with backoff and a cap, a clear surfaced error), or does the failure propagate as an unhandled exception, a silent empty result, or an unintended default?

**4. Environment consistency** — Is the same task routed to the same model across dev, CI, and prod, or can different environments silently diverge (e.g. a cheaper/different model in CI producing misleading test results, or a `.env.example` that's drifted from the actual `.env`)?

**5. Reason validation** — Where the routing table states a *reason* for a task's model choice ("more reliable structured output," "faster"), is there anything backing that claim — a test asserting the expected output shape/quality, a comparison note — or is the reason asserted without a check that would catch it silently stopping being true?

## Severity

- **Critical** — a call site uses a model ID that differs from documented routing with no fallback, or a deprecated/soon-to-be-deprecated model ID is hardcoded with no config layer to swap it.
- **Moderate** — routing is correct but has no fallback on failure, or environments have drifted from each other.
- **Minor** — routing and fallback are fine, but the stated reason for a choice has no backing check.

## Output format

For each task/routing entry reviewed, report:

```
[SEVERITY] <task name>
Documented: <model per the table/config>
Actual: <model the call site actually uses>
Missing: <which of the 5 checks fail, and why — cite the actual code/config>
Failure scenario: <what happens today if this model becomes unavailable or the routing silently diverges further>
```

End with a short summary: tasks reviewed, findings per severity, and which finding you'd fix first — usually wherever code and documented routing already disagree, since that's actively misleading right now rather than a future risk.

## What this skill does not do

- Does not modify code or config — findings only.
- Does not evaluate whether the routing choices themselves are good (whether Groq really is the right call for cover letters) — only whether the system reliably does what it claims to do.
- Does not monitor providers in real time — it's a point-in-time audit, not a live alert on deprecations.
