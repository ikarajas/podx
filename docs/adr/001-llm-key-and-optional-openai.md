# ADR 001: LLM API key via env; OpenAI SDK optional

## Context

Summarization uses a Large Language Model (ChatGPT/OpenAI by default). We must decide how to supply the API key and whether to declare the `openai` package as a hard dependency.

## Decision

- Store the OpenAI API key in an environment variable (`OPENAI_API_KEY`), not in the persisted config file.
- Do not include `openai` in the default `pyproject.toml` dependencies; treat it as an optional dependency users can install on demand.

## Rationale

- Secrets in env:
  - Security: avoids writing secrets to disk and accidental commits/backups.
  - Operational fit: works with CI/CD, containers, and secret injection.
  - Convenience: switch accounts/tenants per shell without editing files.
  - Consistency: `save_config` only persists safe fields, reducing leakage risk.

- Optional OpenAI SDK:
  - Keep core features (ingest/search/UI) usable offline with no OpenAI account.
  - Reduce install weight and avoid SDK version churn in non‑LLM workflows.
  - Allow users to pin a preferred SDK version when they opt in.
  - Preserve flexibility for other providers later without dragging unused deps.

## Consequences

- Users must export `OPENAI_API_KEY` (or use their own secret mgr) to enable summarization.
- The default install won’t provide the `openai` package; users run `pip install openai` (or `podx[llm]` if an extra is added later).

## Alternatives considered

- Persist API key in config: simpler UX but higher risk (plain‑text secret on disk, commits/backups). Could be allowed as read‑only with clear warnings; we chose not to persist it.
- Make `openai` a hard dependency: simpler setup but penalizes non‑LLM users and tightens coupling to a specific SDK version.

