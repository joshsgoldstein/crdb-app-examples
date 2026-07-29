# Gap Analysis: CockroachDB Agent Skills vs. Weaviate Agent Skills

**Date:** 2026-07-29
**Sources:**
- Ours: `/Users/josh/.claude/skills/` (33 CockroachDB/database-related skills)
- Theirs: `/tmp/weaviate-agent-skills/` (clone of `weaviate/agent-skills`, v0.2.3, 2 skills + 8 commands)

---

## 1. Executive Summary

The two collections are almost perfectly complementary — they barely overlap, because they target different personas and different moments in the customer lifecycle.

- **Weaviate** built a small, polished **developer-acquisition funnel**: a core "hands-on-keyboard" skill with 13 executable Python scripts, an app-builder "cookbooks" skill with 11 blueprints (RAG, agents, chatbots, frontends), 8 slash commands including an interactive `/quickstart` onboarding flow, and full plugin packaging for Claude Code and Cursor with a public GitHub repo, marketplace manifest, contribution guide, and marketing funnels (UTM-tagged cloud-console signup links baked into skill text).
- **We** built a deep, wide **operator/DBA and field-engineering library**: 33 skills covering SQL authoring, migration tooling (MOLT), live triage and historical profiling, capacity/maintenance/upgrade operations, a large security/compliance suite, and pre-sales workload sizing. Coverage per skill is far deeper (avg ~330 lines vs. Weaviate's lean index style), tier-aware (Self-Hosted / Advanced / BYOC / Standard / Basic), and privilege-aware.

**Weaviate's biggest advantages over us:** distribution/packaging, onboarding UX, executable scripts, and "build an app on our database" cookbooks.
**Our biggest advantages over them:** operational depth, migration tooling, performance triage, and security/compliance — Weaviate has essentially none of these.

**Top recommendations (detail in §6):**
1. Package our CRDB skills as an installable public plugin (Claude Code marketplace + `npx skills` + Cursor) with manifests and a README.
2. Build a `/cockroachdb:quickstart` interactive onboarding command (cluster signup, connection setup, sample data, first queries).
3. Add an application-builder "cookbooks" skill (Node/Python/Go app scaffolds, ORM patterns, connection pooling, multi-region app blueprints, changefeed-driven event apps).
4. Fix structural debt: broken cross-skill links from the old category layout; tighten a few SKILL.md files that are too long for a single context load.
5. Add executable helper scripts for the read-only diagnostic skills (health check, triage, profiling) so the agent runs one command instead of composing many SQL calls.

---

## 2. What Weaviate Has (Inventory & Characterization)

### 2.1 Repo layout and packaging

```
agent-skills/
├── .claude-plugin/          # marketplace.json + plugin.json (Claude Code plugin, v0.2.3)
├── .cursor-plugin/          # plugin.json with logo (Cursor plugin, v0.1.0)
├── assets/                  # banner.jpg, logo.svg (branding)
├── commands/                # 8 slash commands (ask, collections, data, explore, fetch, import, query, quickstart, search)
├── skills/
│   ├── weaviate/            # core DB-operations skill: SKILL.md + 13 references + 13 Python scripts
│   └── weaviate-cookbooks/  # app-builder skill: SKILL.md + 11 references (no scripts)
├── AGENTS.md                # agent-facing setup instructions (env vars, uv, script index)
├── CONTRIBUTING.md          # community contribution guide (issues, PRs, "good first issue")
├── README.md                # human-facing: install via npx skills / plugin manager / clone
└── LICENSE
```

Three install paths are documented: `npx skills add weaviate/agent-skills` (cross-agent, per the agentskills.io open standard), `/plugin marketplace add` + `/plugin install` (Claude Code), and manual clone with `claude --plugin-dir .`. They explicitly target Claude Code, Cursor, GitHub Copilot, and Gemini CLI.

### 2.2 The `weaviate` core skill (operational, script-backed)

- SKILL.md is a **thin index** (~110 lines): description, env-var requirements, a categorized script index where every entry has a one-line "use when" discriminator (e.g., hybrid = "default choice", keyword = "exact terms, IDs, SKUs"), a 7-step recommended workflow, output-format notes, and an error-handling table.
- 13 reference files, each short (24–160 lines), documenting exactly one script: usage, parameter table, output format, examples.
- 13 Python scripts (list/get/explore/create collection, hybrid/semantic/keyword search, Query Agent ask/search, fetch/filter, import CSV/JSON/JSONL/PDF, example data generator, shared `weaviate_conn.py`). Notable engineering choices:
  - **PEP 723 inline dependency blocks** so `uv run script.py` auto-installs pinned deps — zero project setup.
  - Shared connection helper that auto-detects 17 provider API keys from env and maps them to Weaviate headers.
  - Typer CLIs with consistent flags; every script emits **markdown tables by default, JSON with `--json`** — deliberately agent-friendly output.
  - `example_data.py` (945 lines) ships 5 sample datasets (academic, finance, ecommerce, medical, customer support) so a brand-new user has data to play with in one command.

### 2.3 The `weaviate-cookbooks` skill (app-builder blueprints)

An **index + references** skill with no scripts. The SKILL.md routes to 11 references:

- **Shared contracts:** `project_setup.md` (git init before `.env`, canonical `.gitignore`, and — notably — recommended **Claude Code `settings.json` deny rules** blocking `Read(./.env)` etc.) and `environment_requirements.md` (canonical `.env` template, provider→header table).
- **Cookbooks:** Query Agent Chatbot (FastAPI + SSE streaming), Data Explorer, Basic RAG, Advanced RAG (re-ranking, query rewriting/decomposition, LLM filter selection), Multimodal PDF RAG (ColBERT-style embeddings + Ollama/Qwen3-VL), Basic Agent (DSPy tool-calling), Agentic RAG (RAG tools, hierarchical RAG, vector-DB memory, Query Agent, Elysia).
- **Frontend:** an opinionated Next.js reference (App Router, Tailwind v4, shadcn/ui, Framer Motion, Vercel AI SDK) including visual-style rules ("liquid glass" aesthetic) and layout rules.
- **Production client guidance:** `async_client.md` for FastAPI/async lifecycles.

Cookbooks are prescriptive about stack (`uv`, DSPy, FastAPI) and include "workflow contracts" (build order, when to ask the user, non-secret sanity checks before asking for credentials). They chain: agentic_rag says "MUST READ basic_agent first."

### 2.4 Commands and the quickstart funnel

8 slash commands wrap the scripts with argument hints, `allowed-tools` frontmatter, and `${CLAUDE_PLUGIN_ROOT}` paths. The standout is **`/weaviate:quickstart`** (~330 lines): a branching interactive onboarding that segments users ("brand new" / "cluster but empty" / "cluster with data"), walks account signup on Weaviate Cloud (with UTM-tagged links), teaches secure env-var setup (explicitly: never paste API keys into chat; exit, export, relaunch), loads sample data, runs a guided test drive of every command, and ends with a routed "what's next" (including "Build an app" → cookbooks). It doubles as product marketing.

### 2.5 Tone and audience

Developer-first, acquisition-oriented, friendly, and lean. The whole repo is ~7,400 lines including scripts. There is **no** content on operations, scaling, backup, security hardening, monitoring, upgrades, or migration from competing vector DBs.

---

## 3. What We Have (Inventory & Characterization)

33 CockroachDB skills in `/Users/josh/.claude/skills/`, ~10,900 lines of SKILL.md alone plus references. All are markdown-only (no scripts, no commands, no plugin manifests). Consistent frontmatter: `name`, `description` with explicit "Use when..." trigger sentences, a `compatibility` field (privileges, binaries, plan tiers), and `metadata` (author, version 1.0/2.0).

### Journey coverage

| Journey | Skills |
|---|---|
| **SQL authoring & schema design** | cockroachdb-sql (rules corpus: fundamentals, schema, DML, query patterns, optimization, operational; mandatory EXPLAIN validation loop) |
| **App development patterns** | designing-application-transactions (retries, pooling, keyset pagination, follower reads), designing-multi-region-applications (RBR/GLOBAL/partitioning + demo setup), benchmarking-transaction-patterns |
| **Migration (MOLT suite)** | molt-fetch, molt-verify, molt-replicator — full fetch → verify → CDC-replicate → cutover workflow from PG/MySQL/Oracle/MSSQL |
| **Live & historical performance triage** | triaging-live-sql-activity, profiling-statement-fingerprints, profiling-transaction-fingerprints, auditing-table-statistics, analyzing-range-distribution, analyzing-schema-change-storage-risk, monitoring-background-jobs |
| **Day-2 operations (tier-aware, v2.0 series)** | reviewing-cluster-health, provisioning-cluster-for-production, upgrading-cluster-version, managing-cluster-settings, managing-cluster-capacity, performing-cluster-maintenance, managing-certificates-and-encryption |
| **Security & compliance (11 skills)** | auditing-cloud-cluster-security, configuring-audit-logging / ip-allowlists / log-export / private-connectivity / sso-and-scim, enabling-cmek-encryption, enforcing-password-policies, hardening-user-privileges, managing-tls-certificates, preparing-compliance-documentation (SOC 2 / PCI / ISO / HIPAA / GDPR) |
| **Field/pre-sales** | workload-analyzer (multi-source customer workload → HTML sizing report; integrates docs MCP, Gong, Confluence, Slack, Salesforce, Drive) |

### Distinctive strengths

- **Tier-aware routing:** the v2.0 skills gather deployment context first (Self-Hosted / Advanced / BYOC / Standard / Basic) and route to tier-appropriate procedures — a sophistication Weaviate has no equivalent of.
- **Privilege- and safety-awareness:** compatibility fields name exact privileges (VIEWACTIVITY, ZONECONFIG, CONTROLJOB); skills separate read-only diagnostics from opt-in destructive actions with explicit warnings; "production-safe" annotations on internal tables.
- **Cross-skill referrals:** triage → profiling → jobs skills point at each other for the right tool.
- **Troubleshooting tables** (symptom / cause / fix) in most diagnostic skills.

### Weaknesses observed

- **No packaging or distribution.** Skills live loose in a personal `~/.claude/skills` directory: no plugin.json, no marketplace manifest, no README, no install story, no Cursor/Copilot path, no public repo hygiene (LICENSE, CONTRIBUTING).
- **No slash commands, no onboarding.** A new user has no `/quickstart`; every skill assumes an existing cluster and credentials.
- **No executable scripts.** Everything is "here is SQL to run" — the agent must compose and execute many statements per session, which is slower, more error-prone, and harder to keep consistent than Weaviate's one-command scripts with markdown/JSON output.
- **Broken cross-links from a flattened layout.** Several skills (reviewing-cluster-health, benchmarking-transaction-patterns, designing-application-transactions, designing-multi-region-applications) still link via old category paths like `../../observability-and-diagnostics/monitoring-background-jobs/SKILL.md` and `../../query-and-schema-design/cockroachdb-sql/SKILL.md`, which don't resolve in the current flat layout.
- **Heavy single-file skills.** Several SKILL.md files run 400–700 lines (auditing-table-statistics 700, configuring-sso-and-scim 618, designing-application-transactions 588, auditing-cloud-cluster-security 548, monitoring-background-jobs 525) with thin or absent `references/` — the opposite of the progressive-disclosure pattern; the entire body loads on trigger.
- **Inconsistent metadata:** workload-analyzer lacks `compatibility`/`metadata`; version split between 1.0 and 2.0 conventions.

---

## 4. Gap Analysis

### 4.a What Weaviate has that we lack

| Gap | What they do | Why it matters for us |
|---|---|---|
| **Plugin packaging & distribution** | `.claude-plugin/marketplace.json` + `plugin.json`, `.cursor-plugin/plugin.json` with logo, `npx skills add`, public GitHub repo with README/LICENSE/CONTRIBUTING/branding assets | Our skills are undistributable today. Packaging is nearly free and turns the library into a public developer-relations asset ("`/plugin install cockroachdb`"). |
| **Interactive quickstart / onboarding command** | `/weaviate:quickstart` segments the user, walks cloud signup (UTM-tagged), teaches secure credential setup, loads sample data, test-drives every command, routes to cookbooks | This is a signup funnel inside the agent. We have zero acquisition surface; every skill assumes an existing, connected cluster. A CRDB equivalent (create CockroachDB Cloud Basic cluster / `cockroach demo`, set `COCKROACH_URL`, load sample workload, run first queries) would be high-leverage. |
| **App-builder cookbooks** | 7 end-to-end application blueprints (RAG variants, agents, chatbot, data explorer) + frontend guide + async-client production guide | We help people *operate* CockroachDB but not *build on* it. Nothing covers "scaffold a Node/Python/Go app on CRDB," ORM setup (Prisma/SQLAlchemy/GORM), REST API + pooling, changefeed/outbox event-driven apps, or a multi-region app demo end-to-end. |
| **Executable helper scripts** | 13 uv-runnable Python scripts with inline deps, shared connection helper, consistent markdown/JSON output | One command replaces a multi-step agent dance; output is deterministic and diff-able. Our diagnostic skills would benefit most (health check, triage, fingerprint profiling as single scripts against `$COCKROACH_URL`). |
| **Slash commands wrapping common ops** | 8 commands with argument hints, `allowed-tools`, AskUserQuestion fallbacks | Commands give discoverability (`/cockroachdb:health`, `/cockroachdb:slow-queries`, `/cockroachdb:sql`) and constrain tool permissions. |
| **Sample data / instant playground** | `example_data.py` with 5 domain datasets; `/weaviate:data` | Lowers time-to-first-query for evaluators. CRDB has `cockroach workload init movr` etc. — a skill/command surfacing it would match this. |
| **Shared setup contracts** | `project_setup.md`: git-before-.env ordering, canonical `.gitignore`, Claude settings deny-rules for secrets | A small, reusable safety pattern we should adopt for any app-building skills (and it's a good look security-wise). |
| **Frontend guidance** | Opinionated Next.js/shadcn/Tailwind reference with visual style rules | Relevant if we ship cookbooks whose demos need a UI (e.g., multi-region latency visualizer). Lower priority for a database company, but it's what makes their demos feel finished. |
| **Community/contribution motion** | CONTRIBUTING.md, good-first-issue labels, discussions-first policy, agentskills.io open-standard alignment | Positions the skill repo as an ecosystem project, not internal tooling. |
| **Agent-agnosticism** | Explicit support for Claude Code, Cursor, Copilot, Gemini CLI via the open Agent Skills standard | Our frontmatter is Claude-flavored; packaging per the standard broadens reach at little cost. |

### 4.b What we have that Weaviate lacks

| Our asset | Weaviate's coverage | Notes |
|---|---|---|
| **Deep operational/DBA skills** (health, provisioning, upgrades, capacity, maintenance, settings) | None | Weaviate has no day-2 story at all — no health checks, no scaling, no upgrade guidance, no backup/restore. This is our moat; their skills stop at "query your data." |
| **Migration tooling suite** (molt fetch/verify/replicator, cutover workflow) | None | No "migrate from Pinecone/Qdrant/pgvector" equivalent exists in their repo — a notable hole on their side, and a category we should keep investing in. |
| **Performance triage & profiling** (live activity, statement/txn fingerprints, ranges, stats, jobs) | None | Their only diagnostic is `explore_collection` stats. |
| **Security & compliance suite** (11 skills: audit logging, CMEK, SSO/SCIM, allowlists, private connectivity, RBAC hardening, compliance docs) | A one-paragraph security disclaimer + `.env` hygiene | Enterprise buyers ask for exactly what we cover. Nothing comparable exists on their side. |
| **Tier-aware routing** (Self-Hosted/Advanced/BYOC/Standard/Basic context gathering) | Cloud-only assumption (Weaviate Cloud sandbox) | Our skills adapt to deployment reality; theirs assume one happy path. |
| **Privilege/safety modeling** (exact privileges in `compatibility`, read-only vs. opt-in destructive separation, production-safe annotations) | Minimal (admin API key assumed) | Genuinely differentiated rigor; keep it. |
| **Pre-sales tooling** (workload-analyzer with multi-MCP enrichment and HTML report) | None | Internal-facing but unique; no analog in their repo. |
| **Troubleshooting matrices** (symptom/cause/fix tables) | A 3-bullet error list | Ours are much stronger for unattended agent recovery. |
| **Version/compatibility gating** ("CockroachDB >= 22.1", plan requirements) | Client version pins only | Helps the agent avoid recommending unavailable features. |

### 4.c Structural & quality observations

1. **Index + references vs. monolith.** Weaviate keeps SKILL.md thin (~110 lines) and pushes detail into per-topic references — the intended progressive-disclosure model, cheap on context. Roughly a third of our skills instead carry 400–700-line SKILL.md bodies with little in `references/`. Our best-structured skills (cockroachdb-sql with its rules corpus, triaging-live-sql-activity with queries/permissions split out) already follow the better pattern.
2. **Description quality: we are actually stronger.** Our descriptions consistently embed trigger phrases, symptoms ("users report cluster slowness"), and interface constraints ("without DB Console access"), plus a separate `compatibility` field. Weaviate's two descriptions are good but generic. However, their per-reference one-line discriminators in the index ("default choice," "exact terms/IDs/SKUs") are excellent routing hints we mostly lack at the reference level.
3. **Scripts as the execution layer.** Weaviate's inline-dependency uv scripts + shared connection helper + markdown/JSON dual output is the best current pattern for skill-attached tooling. We have zero scripts in the CRDB set (only unrelated skills like pptx/xlsx use them).
4. **Distribution.** They ship a versioned plugin (0.2.3) on two marketplaces with branding; we ship nothing.
5. **Link hygiene.** Our flattened layout left broken `../../<category>/<skill>/SKILL.md` links in at least 4 skills; Weaviate's relative links all resolve. If we re-adopt category folders in a public repo, do it deliberately and keep links consistent.
6. **Commands as guardrails.** Their commands declare `allowed-tools: Bash(uv:*), AskUserQuestion, Skill` — narrow permissions per command. Worth copying when we add commands.
7. **Secret handling.** Their quickstart's "never paste API keys into chat, exit and export" flow and the settings.json deny-rules are thoughtful patterns for credential-touching flows (ours frequently need `COCKROACH_URL` with embedded passwords — same risk, no equivalent guidance today).
8. **Marketing embedded in skills.** UTM-tagged signup links and eBook funnels appear inside skill/reference text. Effective for acquisition; we should decide our own policy (docs links yes; tracking links — brand call).

---

## 5. Head-to-Head Summary

| Dimension | CockroachDB skills | Weaviate skills | Edge |
|---|---|---|---|
| Breadth of lifecycle (dev → migrate → operate → secure → comply) | 33 skills, full lifecycle | 2 skills, dev/eval only | **Us** |
| Depth per topic | High (procedures, safety, troubleshooting) | Light (index + short refs) | **Us** |
| App-builder journeys (build X on the DB) | ~2 (transactions, multi-region design) | 7 cookbooks + frontend | **Them** |
| Onboarding / acquisition funnel | None | `/quickstart` + sample data + signup flow | **Them** |
| Executable tooling | None | 13 scripts, uv inline deps | **Them** |
| Slash commands | None | 8 | **Them** |
| Packaging & distribution | None | Claude + Cursor plugins, npx skills, public repo | **Them** |
| Trigger-description quality | Strong, symptom-rich + compatibility field | Adequate | **Us** |
| Context economy (progressive disclosure) | Mixed (several 500+ line monoliths) | Consistently lean | **Them** |
| Safety/privilege modeling | Strong | Minimal | **Us** |
| Community motion | None | CONTRIBUTING, labels, standard alignment | **Them** |

---

## 6. Prioritized Recommendations

### P0 — Package and publish (low effort, high leverage)
Create a public `cockroachdb/agent-skills` repo with `.claude-plugin/marketplace.json` + `plugin.json`, `.cursor-plugin/plugin.json`, README (three install paths: `npx skills add`, plugin manager, clone), LICENSE, CONTRIBUTING, and branding assets. Group skills into plugin(s) sensibly (e.g., one `cockroachdb` plugin; optionally split `cockroachdb-security` and `molt`). *Rationale:* everything we've built is invisible outside this machine; Weaviate demonstrates the whole packaging lift is a few dozen files. This also forces the link-hygiene fix (P1).

### P0 — Fix structural debt before publishing
- Repair the broken `../../<category>/...` cross-links in reviewing-cluster-health, benchmarking-transaction-patterns, designing-application-transactions, designing-multi-region-applications (either restore category dirs or rewrite as flat `../<skill>/SKILL.md`).
- Normalize frontmatter (add `compatibility`/`metadata` to workload-analyzer; unify version scheme).
- Split the 500+ line monoliths (auditing-table-statistics, configuring-sso-and-scim, designing-application-transactions, auditing-cloud-cluster-security, monitoring-background-jobs) into thin SKILL.md indexes + references, keeping the trigger-rich descriptions.

### P1 — `/cockroachdb:quickstart` onboarding command
Model on Weaviate's: segment the user (no cluster / has cluster, no data / ready to query), walk CockroachDB Cloud Basic signup or `cockroach demo` for local, secure `COCKROACH_URL` setup (adopt their "never paste secrets into chat" pattern), load sample data (`cockroach workload init movr` or a curated dataset), guided first queries, then route to skills. Add a handful of wrapper commands with narrow `allowed-tools` (`/cockroachdb:health`, `/cockroachdb:slow-queries`, `/cockroachdb:sql`). *Rationale:* this is Weaviate's acquisition funnel; we have no equivalent and most of the underlying content already exists in our skills.

### P1 — App-builder "cockroachdb-cookbooks" skill
Index + references, mirroring their pattern: (a) shared project-setup contract (git-before-.env, `.gitignore`, Claude deny-rules for secrets/connection strings); (b) cookbooks — REST API on CRDB (FastAPI/Express + pooling + retry loop, drawing on designing-application-transactions), ORM setup (Prisma/SQLAlchemy/GORM/Hibernate with CRDB-specific settings), multi-region app end-to-end (drawing on designing-multi-region-applications), event-driven app with changefeeds/outbox, serverless app on Basic tier; (c) optional frontend reference if demos need UIs. *Rationale:* we cover operate-and-migrate deeply but "build your first app on CockroachDB" — the journey that creates new users — is our biggest content gap and squarely what Weaviate's cookbooks do.

### P2 — Executable scripts for diagnostics
Add uv-runnable scripts (PEP 723 inline deps, shared `crdb_conn.py` reading `$COCKROACH_URL`, markdown-default/`--json` output) for the read-only skills first: cluster health snapshot, live-activity triage, statement/transaction fingerprint top-N, range distribution, stats staleness, job health. Keep destructive actions (CANCEL, settings changes) as SQL-in-markdown with the existing opt-in warnings. *Rationale:* determinism, speed, fewer agent mistakes; Weaviate's scripts are the strongest engineering pattern in their repo.

### P2 — Sample-data / playground command
Surface `cockroach workload` datasets (movr, tpcc, bank) via a `/cockroachdb:data` command and reference, so quickstart and cookbooks have instant data. *Rationale:* direct analog of their 5-domain `example_data.py`; nearly free since the tooling exists.

### P3 — Adopt their micro-patterns opportunistically
- One-line "use when / default choice" discriminators on every reference link in our SKILL.md indexes.
- Error-handling and output-format sections in skill indexes.
- Decide policy on UTM-tagged cloud signup links inside skill content.
- Align frontmatter with the agentskills.io open standard for cross-agent portability (Cursor/Copilot/Gemini CLI).

### Non-goals (keep our advantages, don't chase theirs blindly)
- Don't thin out operational depth to match their lean style — depth is our differentiation; restructure it (index + references), don't delete it.
- Frontend/"liquid glass" styling guidance is low priority for a database audience; only add if cookbook demos require UIs.

---

## Appendix: Key file paths

**Weaviate**
- Manifests: `/tmp/weaviate-agent-skills/.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`
- Core skill: `/tmp/weaviate-agent-skills/skills/weaviate/SKILL.md` (+ `references/`, `scripts/`)
- Cookbooks: `/tmp/weaviate-agent-skills/skills/weaviate-cookbooks/SKILL.md` (+ 11 references)
- Onboarding: `/tmp/weaviate-agent-skills/commands/quickstart.md`
- Setup contract: `/tmp/weaviate-agent-skills/skills/weaviate-cookbooks/references/project_setup.md`
- Shared connection helper: `/tmp/weaviate-agent-skills/skills/weaviate/scripts/weaviate_conn.py`

**Ours (representative)**
- `/Users/josh/.claude/skills/cockroachdb-sql/SKILL.md` (best-structured: rules corpus in `references/cockroachdb-rules/`)
- `/Users/josh/.claude/skills/triaging-live-sql-activity/SKILL.md` (strong diagnostic pattern)
- `/Users/josh/.claude/skills/reviewing-cluster-health/SKILL.md` (tier-aware routing; contains broken `../../observability-and-diagnostics/...` links)
- `/Users/josh/.claude/skills/workload-analyzer/SKILL.md` (pre-sales; missing `compatibility`/`metadata` frontmatter)
- MOLT suite: `/Users/josh/.claude/skills/molt-{fetch,verify,replicator}/SKILL.md`
