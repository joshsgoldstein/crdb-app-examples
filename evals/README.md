# Skill Evaluations

Behavioral evaluations for the `crdb-cookbooks` skill. Each scenario runs a real headless Claude Code session with the plugin loaded, then an LLM judge scores the transcript against a rubric. Scenarios are plan/dry-run style, so no CockroachDB cluster or embedding API keys are needed — the evals measure **skill adherence** (does the agent follow the cookbooks' load-bearing rules), not infrastructure.

## What is evaluated

| Scenario | Load-bearing behavior |
| --- | --- |
| `trigger-basic-rag` | Skill activates from a natural prompt; embeddings source resolved before code; correct VECTOR/index DDL and version notes |
| `embeddings-existing` | Pre-embedded data is never re-embedded; model/dimension consistency |
| `hybrid-rrf` | Hybrid search is a single SQL statement with server-side RRF, not client-side merging |
| `retry-handling` | Writes retry on SQLSTATE `40001` with backoff |
| `nl2sql-safety` | NL-to-SQL chatbot enforces read-only execution in code; streaming; CRDB-persisted history |
| `version-gating` | Correct version facts (VECTOR v24.2+, vector indexes v25.2+) |
| `data-explorer` | Catalog introspection, identifier safety, pagination |
| `one-shot-build` | `/cockroachdb:build` batches all questions up front, then builds uninterrupted |

## Running

Requires the [Claude Code CLI](https://code.claude.com) (authenticated) and [uv](https://docs.astral.sh/uv/).

```bash
uv run evals/run_evals.py                    # all scenarios, Opus 4.8 agent + judge
uv run evals/run_evals.py --only hybrid-rrf  # single scenario
uv run evals/run_evals.py --model claude-opus-4-8 --judge-model claude-opus-4-8
```

Both the model under test and the judge default to `claude-opus-4-8`. Results (per-criterion verdicts plus full agent responses) are written to `evals/results/<timestamp>.json`; the script exits non-zero if any scenario fails.

## Notes

- Runs cost real tokens: 8 scenarios × (one agent session + one judge call) on Opus.
- The judge is instructed to be strict — a criterion passes only if clearly satisfied.
- When a cookbook's guidance changes, update the matching rubric in `scenarios.yaml` in the same PR.
