# Agent Guidance

This repository is a standalone Agent Skill (`crdb-cookbooks`) with example-app cookbooks for building AI applications on CockroachDB.

## Repository layout

- `skills/crdb-cookbooks/` — the main skill: `SKILL.md` index + `references/` cookbooks
- `commands/` — slash commands (`/cockroachdb:build`)
- `.claude-plugin/`, `.cursor-plugin/` — plugin/marketplace manifests
- `docs/` — internal notes (not part of the plugin)

## Conventions when editing this repo

- Verify all CockroachDB SQL against https://www.cockroachlabs.com/docs/ — never invent syntax. Note minimum versions (VECTOR type v24.2+, vector indexes v25.2+, cosine opclass v25.3+).
- All cookbooks share `DATABASE_URL`, the same connection helpers, and the `run_transaction` retry pattern for SQLSTATE `40001`.
- Vector cookbooks must keep the "Embeddings: Ask the User First" step — CockroachDB has no built-in vectorizer, so the embedding source (existing vectors vs. provider) must be resolved before code is written.
- Where a feature has no CockroachDB equivalent (built-in vectorizers, managed query agents, native BM25 fusion), state it explicitly and show the substitute (client-side embedding, NL-to-SQL agent, single-query RRF).
- Bump the version in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` together.
