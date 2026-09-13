---
name: silent-side-effect-review
description: Audits code where a program automatically mutates stored state without a human confirming each change — auto-status-updates, auto-approve, auto-merge, auto-deploy, auto-classify-and-act flows. Especially important when the decision driving the mutation comes from an LLM, ML score, or fuzzy-match heuristic rather than a deterministic rule. Checks for five safeguards: visibility, audit trail, idempotency, reversibility, and confidence handling. Invoke explicitly — this skill does not auto-trigger.
disable-model-invocation: true
---

# Silent Side-Effect Review

## Why this exists

Most bugs in a normal feature are visible — the user notices the wrong thing on screen and reports it. A silent side effect is different: the program changes stored state on its own, nobody was watching at the moment it happened, and the only trace is the new (wrong) state itself. By the time anyone notices, there's no way to tell what caused it, whether it happened once or five times, or what the state was before.

This is a report-only review. It never edits code — it produces a findings list so you can decide what to fix and in what order.

## When to run this

Run it against any chain of the shape: **trigger → decision → mutation**, where the mutation writes to persistent state (a database row, a file, a deployed resource, a sent message) without a human approving that specific change first. Prioritize chains where the decision step is probabilistic — an LLM classification, an ML confidence score, a fuzzy string match — over chains driven by a deterministic rule (`if status_code == 200`), since deterministic mutations fail loudly and predictably while probabilistic ones fail quietly and unpredictably.

## The five checks

For each trigger→decision→mutation chain in scope, check for a concrete artifact in the code — not a judgment call, an actual mechanism — for each of the following. Cite the file/function where it does or doesn't exist.

**1. Visibility** — Is the change shown to a human, with the reasoning behind it, before or immediately after it's applied? "It's in the database" doesn't count. Look for: a diff of old value → new value, the specific input that triggered the decision (e.g. the source text/snippet), and the decision's stated reasoning or confidence, surfaced somewhere the user will actually see it.

**2. Audit trail** — Is there a permanent, separate-from-the-mutated-field record of what triggered each change, when, and from what input? If the only record of *why* a field changed is the field's current value, there's no audit trail — the previous state and the reasoning are already gone. Look for: an append-only log or events table, with enough detail to answer "why does this say X" weeks later.

**3. Idempotency** — If the same trigger fires twice (a retried job, a duplicated webhook, a re-processed email), does the system reach the same end state without compounding side effects (duplicate notifications, double-appended logs, conflicting writes)? Look for: a dedup key, a check-before-write, or an explicit "already processed" guard.

**4. Reversibility** — Can a wrong automated change be undone directly, or does undoing it require manually reconstructing what the state used to be? Look for: an explicit undo/revert path, or at minimum enough history (via the audit trail) to manually restore prior state without guessing.

**5. Confidence handling** — When the decision is ambiguous or low-confidence, does the code have a defined "defer to human, don't guess" path, or does it always commit to its best guess? Look for: a confidence threshold with a distinct branch (flag for review / no-op) rather than every input forcing a state change.

## Severity

Rate each finding using how much of the chain is missing and how consequential the mutation is:

- **Critical** — the mutation is hard to reverse (or nothing records the prior state) *and* the decision is probabilistic *and* there's no visibility before it applies.
- **Moderate** — one or two of the five checks are missing, but the mutation is either reversible, deterministic, or has some visibility.
- **Minor** — mostly present, but one weak point (e.g. audit trail exists but doesn't capture the triggering input).

## Output format

For each chain reviewed, report:

```
[SEVERITY] <what the chain does, in one line>
Location: <file/function>
Decision source: deterministic | probabilistic (<what drives it>)
Missing: <which of the 5 checks fail, and why — cite the actual code, not a guess>
Failure scenario: <a concrete example — "if the email says X, the system does Y, and nobody would know unless they checked Z">
```

End with a short summary: how many chains were reviewed, how many findings per severity, and which finding you'd fix first if only fixing one.

## What this skill does not do

- Does not modify code — findings only.
- Does not judge whether the automation itself is a good idea — only whether it's safe given that it exists.
- Does not replace tests — a chain can pass all five checks and still have ordinary bugs; that's a different kind of review.
