# Contributing

Thank you for contributing to CockroachDB Agent Skills! Here's how to get started.

[1. Getting Started](#getting-started) | [2. Issues](#issues) | [3. Pull Requests](#pull-requests) | [4. Contributing to a Skill](#contributing-to-a-skill) | [5. Creating a New Skill](#creating-a-new-skill)

## Getting Started

1. Fork and clone the repository:
   ```bash
   git clone https://github.com/<your-username>/agent-skills.git
   cd agent-skills
   ```
2. Ensure you have [Python 3.12+](https://www.python.org/) and [uv](https://docs.astral.sh/uv/) installed.
3. Set `DATABASE_URL` to a CockroachDB cluster (a free [CockroachDB Cloud](https://cockroachlabs.cloud) cluster or a local `cockroach demo`). See the [README](./README.md#configuration) for details.

## Issues

If you find a bug, have a suggestion, or want to propose a new skill or reference, please create an issue.

- Search existing issues before creating a new one.
- Include a clear description of the problem or suggestion.
- Tag your issue appropriately (e.g., `bug`, `enhancement`, `new-reference`, `new-skill`, `documentation`).

## Pull Requests

We actively welcome pull requests!

- If you're fixing an issue, check that no one else has already opened a PR for it, and link your PR to the related issue(s).
- Keep PRs focused: one cookbook or one concern per PR.
- Verify SQL against the [CockroachDB docs](https://www.cockroachlabs.com/docs/) — do not invent syntax. Note the minimum CockroachDB version for any feature you use.
- Test cookbook changes end to end: install the plugin locally (`/plugin marketplace add <path-to-your-clone>`), open an agent session in a folder of sample data, and build the app the cookbook describes.

## Contributing to a Skill

Each skill follows the index + references pattern:

- `SKILL.md` — frontmatter (name, triggering description) and a high-level index. Keep it short; details belong in references.
- `references/*.md` — self-contained guides the agent loads on demand.

Conventions to preserve:

- All cookbooks share `DATABASE_URL`, the same connection helpers, and the same `run_transaction` retry pattern for `40001` errors.
- Vector cookbooks must direct the agent to ask the user where embeddings come from before writing code (see "Embeddings: Ask the User First" in `SKILL.md`).
- Call out Weaviate-style features CockroachDB lacks (built-in vectorizers, managed query agents) and show the substitute approach explicitly.

## Creating a New Skill

1. Create `skills/<skill-name>/SKILL.md` with a specific, action-oriented `description` — it is what makes agents load the skill.
2. Put detailed guides in `skills/<skill-name>/references/`.
3. Add the skill to the README's Available Skills table.
4. If the skill warrants a slash command, add it under `commands/`.
