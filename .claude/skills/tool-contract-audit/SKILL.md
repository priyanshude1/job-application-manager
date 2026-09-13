---
name: tool-contract-audit
description: Audits any set of callable contracts — agent tools (LangGraph/function-calling), REST endpoints, CLI commands, public library functions — for undefined behavior outside the happy path. Checks each callable for zero-match/no-result handling, ambiguous-match handling, downstream-failure handling, output-schema guarantees, and partial-success state. Invoke explicitly — this skill does not auto-trigger.
disable-model-invocation: true
---

# Tool-Contract Audit

## Why this exists

A tool table or API spec that lists `input → output` is a description of the happy path only. Nothing in "takes `application_id`, returns confirmation" says what happens when `application_id` doesn't exist, matches nothing, or the thing it depends on (an LLM call, a DB write, an external API) fails mid-call. Those gaps don't show up in normal testing — they show up the first time a caller (a human, an agent, another service) sends something slightly off-script, and then the failure is whatever the underlying code happens to do, not what anyone decided it should do.

This is a report-only review. It never edits code — it produces a findings list.

## When to run this

Run it against any explicitly defined set of callables meant to be invoked by something other than a human reading the source: agent tool definitions, API route handlers, CLI subcommands, or public functions in a shared library. Prioritize callables that: look up or match against stored data by a loosely-specified key (a name, a natural-language query), depend on an external or probabilistic service (an LLM, a network call), or perform more than one step where an early step can succeed while a later one fails.

## The five checks

For each callable in scope, check for a concrete, intentional code path — not just "it probably doesn't crash" — for each of the following. Cite the file/function.

**1. Zero-match handling** — If the callable looks something up (by ID, name, natural-language query) and nothing matches, what actually happens? Look for: a distinct "not found" return or error, versus an unhandled `None`/index error, an empty-but-still-"successful" response, or silent fallthrough to a default.

**2. Ambiguous-match handling** — If the lookup key could match more than one record (a fuzzy name match, a natural-language query), what happens? Look for: an explicit "multiple matches, which one?" path, versus silently picking the first/last result.

**3. Downstream-failure handling** — If something this callable depends on fails (LLM call errors or times out, a DB write fails, an external API is unreachable), does the callable have a defined failure return, or does the failure propagate as an unhandled exception, a hang, or — worse — get silently swallowed and reported as success? Look specifically for retries that lack a cap (infinite retry) and empty `except:` blocks.

**4. Output-schema guarantee** — Is the declared output shape (the dict/object the caller expects) actually enforced along every path through the function, or can some branch return something that violates it (a missing key, wrong type, `None` where a value is expected)? A caller (especially an LLM agent parsing the result) that gets a malformed output often fails confusingly rather than obviously.

**5. Partial-success state** — For callables that do more than one thing (e.g. "generate suggestions, then compile a PDF"), what state exists if the first step succeeds and the second fails? Look for: whether the callable is effectively atomic (all-or-nothing), or can leave behind a half-done artifact with no indication it's incomplete.

## Severity

- **Critical** — the callable is reachable with realistic input (a plausible name that doesn't exist, a normal API hiccup) that produces an unhandled exception, a hang, or a result the caller can't distinguish from success.
- **Moderate** — the failure is handled but poorly surfaced (e.g. returns `None` with no error context, or a partial result with nothing flagging it as partial).
- **Minor** — handled and surfaced correctly, but inconsistently with the rest of the callables in scope (e.g. every other tool returns a typed error object, this one raises a bare exception).

## Output format

For each callable reviewed, report:

```
[SEVERITY] <callable name>
Location: <file/function>
Missing: <which of the 5 checks fail, and why — cite the actual code>
Failure scenario: <a concrete example input and what actually happens today>
```

End with a short summary: how many callables reviewed, findings per severity, and which one you'd fix first if only fixing one — usually the one most likely to be hit by realistic input, not the theoretically worst one.

## What this skill does not do

- Does not modify code — findings only.
- Does not check business logic correctness (whether `score_match` computes the right score) — only whether the callable's *contract* holds under input it wasn't explicitly designed for.
- Does not replace unit tests — this surfaces what to write tests for, it isn't a substitute for writing them.
