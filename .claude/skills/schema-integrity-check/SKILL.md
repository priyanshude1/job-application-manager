---
name: schema-integrity-check
description: Audits a relational database schema (ORM models + migrations) for cascade/orphan risk, missing uniqueness constraints, drift between the live schema and the model code, nullable/required mismatches, and consistency with any external system a row references (e.g. an experiment-tracking run ID). Invoke explicitly — this skill does not auto-trigger.
disable-model-invocation: true
---

# Schema-Integrity Check

## Why this exists

A schema that "works" in normal use can still be quietly unsound: a foreign key with no defined delete behavior leaves orphaned rows the first time something upstream gets deleted, a uniqueness rule enforced only in application code gets bypassed the first time a second code path writes to the table, or the ORM model in source no longer matches what the actual database looks like because a migration was never written or never run. None of these show up until the specific sequence of events that triggers them — usually in production, usually at an inconvenient time.

This is a report-only review. It never edits code, models, or migrations — it produces a findings list.

## When to run this

Run it against any relational schema (SQLAlchemy models, Django models, raw migration files, or an equivalent) — most valuable after the schema stabilizes past its first draft, before deploying, or whenever a row in one table starts referencing state tracked in a separate system (a run ID in an experiment tracker, a job ID in a queue, a file path on disk).

## The five checks

**1. Cascade / orphan behavior** — For each foreign key, what happens to child rows when the parent is deleted — CASCADE, SET NULL, RESTRICT, or nothing explicitly defined (silently falling back to whatever the DB engine defaults to)? Is that behavior the intended one, or just whatever happened by omission? Look specifically for child rows that would become orphaned (referencing a deleted parent) with no defined cleanup.

**2. Uniqueness / duplicate risk** — Are there fields or field-combinations that should be unique (e.g. one active record per natural key) but rely only on application-level checks rather than a DB-level unique constraint? A check in one code path doesn't stop a different code path, a script, or a race condition from creating a duplicate.

**3. Cross-system reference consistency** — Where a row stores an identifier or version tracked by an external system (a run ID, a tracked artifact version, a queue job ID), is there any guarantee the two stay in sync — or can the DB record a reference to something that was never actually created externally, or that has since been deleted/rotated there?

**4. Nullable vs. required mismatch** — For fields the application logic assumes are always present (it reads `row.field` without a None-check), does the DB actually enforce NOT NULL — or is that assumption only true because every current code path happens to set it, meaning a new code path or a bulk import could silently violate it?

**5. Model-vs-migration drift** — Does the live schema, as actually produced by the migration history, match the ORM model definitions in source? Look for: a model field with no corresponding migration, a migration that was edited after being applied elsewhere, or a column that exists in the DB but not in the model (or vice versa).

## Severity

- **Critical** — a foreign key relationship with undefined cascade behavior on a table that's actually deleted from in the app, or model-vs-migration drift affecting a field the application actively reads/writes.
- **Moderate** — a uniqueness rule enforced only in application code, or a nullable field the app assumes is always set.
- **Minor** — a cross-system reference with no sync guarantee, but low consequence if it goes stale (e.g. a soft-fail read path already handles a missing reference gracefully).

## Output format

For each table/relationship reviewed, report:

```
[SEVERITY] <table.field or relationship>
Missing: <which of the 5 checks fail, and why — cite the actual model/migration>
Failure scenario: <a concrete sequence of events that triggers the problem>
```

End with a short summary: tables reviewed, findings per severity, and which one you'd fix first — usually whichever failure scenario is most likely to actually occur given how the app is used, not the theoretically worst one.

## What this skill does not do

- Does not modify models, migrations, or the database — findings only.
- Does not evaluate schema design choices (normalization, indexing for performance) — only integrity risks that produce silently wrong or orphaned data.
- Does not run against a live database by default — it reviews the model/migration source; running the checks against real data is a separate, heavier step you'd do manually if a finding warrants it.
