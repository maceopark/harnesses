# PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-07
**Commit:** 77b0327
**Branch:** master

## OVERVIEW

This checkout is a harness workspace, not a single product. It contains seven declared submodules plus local todo CLI experiment fixtures and agent workflow artifacts.

## STRUCTURE

```text
harnesses/
|-- reference/                # Git submodule collection
|   |-- oh-my-codex/          # OMX TypeScript/Rust orchestration layer
|   |-- codex/                # OpenAI Codex CLI/app-server Rust workspace
|   |-- ouroboros/            # Agent OS Python project; has its own AGENTS.md
|   |-- skills/               # Matt Pocock skill catalog and docs source
|   |-- SkillOpt/             # Python skill optimization research + sleep engine
|   |-- lazycodex/            # LazyCodex / OmO Codex harness installer and marketplace
|   `-- epistemic-protocols/  # Epistemic protocol marketplace and protocol skills
|-- benchmark/                # Todo CLI benchmark and Python experiment arms
|-- .agents/                  # Local harness skill copies, notably ultimateinterview
|-- .omo/                     # OMO runtime/evidence artifacts
|-- .ultimateinterview/       # Interview ledgers and protocol artifacts
`-- docs/                     # Current root docs, including renamed ultimateinterview files
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Root workspace boundaries | `.gitmodules` | Submodules under `reference/` are `ouroboros`, `oh-my-codex`, `skills`, `SkillOpt`, `lazycodex`, `epistemic-protocols`, `codex`. |
| OMX CLI/runtime work | `reference/oh-my-codex/` | Submodule. Use `reference/oh-my-codex/README.md`, `CONTRIBUTING.md`, `package.json`. |
| OpenAI Codex CLI/runtime work | `reference/codex/` | Submodule. Use `reference/codex/AGENTS.md`, `README.md`, and the relevant `codex-rs/` crate. |
| Ouroboros commands | `reference/ouroboros/AGENTS.md` | Existing router for `ooo` commands; do not replace casually. |
| Skill catalog edits | `reference/skills/` | Submodule. Bucket/docs/plugin rules live in `reference/skills/CLAUDE.md` and `CONTEXT.md`. |
| SkillOpt training/sleep work | `reference/SkillOpt/` | Submodule. Use `reference/SkillOpt/README.md`, `CONTRIBUTING.md`, `pyproject.toml`. |
| LazyCodex / OmO harness work | `reference/lazycodex/` | Submodule. Use `reference/lazycodex/README.md`, `package.json`. |
| Epistemic protocol/plugin work | `reference/epistemic-protocols/` | Submodule. Has its own `AGENTS.md`; use `reference/epistemic-protocols/README.md`, protocol directories, and `package.json`. |
| Todo CLI acceptance harnesses | `benchmark/` | Small Python apps; use their local `pyproject.toml` and README contracts. |
| Deep interview policy copies | `.agents/skills/ultimateinterview/` | Local harness copy of interview instructions and lessons. |
| Evidence artifacts | `.omo/evidence/`, `benchmark/todo-cli-*/artifacts/` | Treat as observed outputs unless the task explicitly asks to regenerate. |

## CODE MAP

Codegraph tools were not exposed in this harness, and LSP had no active TS/Python clients during generation. Symbol/reference centrality below is therefore from `rg`/file-count evidence, not measured references.

| Symbol or Surface | Type | Location | Role |
|-------------------|------|----------|------|
| `omx` | CLI bin | `reference/oh-my-codex/package.json` | Primary OMX command surface. |
| `run-test-files.ts` | Test runner | `reference/oh-my-codex/src/scripts/run-test-files.ts` | Compiled Node test harness used by package scripts. |
| `templates/AGENTS.md` | Runtime template | `reference/oh-my-codex/templates/AGENTS.md` | Generated workspace operating contract template. |
| `parse_ooo_command` | Parser | `reference/ouroboros/src/ouroboros/router/command_parser.py` | Ouroboros command parsing path. |
| `resolve_packaged_skill_path` | Resolver | `reference/ouroboros/src/ouroboros/router/dispatch.py` | Packaged skill lookup and dispatch. |
| `ReflACTTrainer` | Class | `reference/SkillOpt/skillopt/engine/trainer.py` | Main SkillOpt training loop. |
| `EnvAdapter` | Class | `reference/SkillOpt/skillopt/envs/base.py` | Benchmark environment interface. |
| `cmd_run` | CLI handler | `reference/SkillOpt/skillopt_sleep/__main__.py` | Sleep-cycle entry point. |
| `lazycodex-ai` | CLI bin | `reference/lazycodex/package.json` | Codex install alias for LazyCodex / OmO setup. |
| `epistemic-protocols` | Marketplace | `reference/epistemic-protocols/.agents/plugins/marketplace.json` | Codex marketplace for the epistemic protocol plugins. |
| `todo` | Console script | `benchmark/*/pyproject.toml` | Shared experiment CLI entry name. |

## CONVENTIONS

- Root is a coordination checkout. Run builds/tests inside the relevant subproject; root has no unified build.
- Do not treat `uam-api-service` as local source; it is a symlink to `/Users/jpark/IdeaProjects/uam-api-service`.
- Submodule roots have their own git status and ownership. Check `git -C <dir> status` before editing inside them.
- Run Python tooling through the owning project's `uv run` command, including required extras (for example, `uv run --extra test pytest`); do not rely on a bare system interpreter or tool executable.
- Hidden directories `.gjc`, `.omo`, `.ultimateinterview`, and `.agents` are harness/runtime state, not product packages.
- Existing dirty root docs rename `docs/ultrainterview-*` to `docs/ultimateinterview-*`; leave unrelated doc churn alone.

## ANTI-PATTERNS (THIS PROJECT)

- Do not overwrite `reference/ouroboros/AGENTS.md`; it is an active command router with managed `ooo` sections.
- Do not count `.venv`, `node_modules`, `dist`, `build`, `.pytest_cache`, or generated artifacts when assessing project complexity.
- Do not put credentials directly in example MCP config; `reference/ouroboros/docs/examples/mcp-config.yaml` calls this out explicitly.
- Do not assume a literal `init-deep` implementation exists in this checkout. The invoked skill came from the installed OMO plugin.

## COMMANDS

```bash
# Root inventory
git status --short --branch
git submodule status

# oh-my-codex
cd reference/oh-my-codex && npm run build && npm run lint
cd reference/oh-my-codex && npm test

# ouroboros
cd reference/ouroboros && uv run pytest
cd reference/ouroboros && uv run ruff check src tests

# skills
cd reference/skills && npm run changeset

# SkillOpt
cd reference/SkillOpt && uv run --extra dev pytest

# lazycodex
cd reference/lazycodex && npm test
cd reference/lazycodex && npm run pack:dry-run

# epistemic-protocols
cd reference/epistemic-protocols && node .claude/skills/verify/scripts/static-checks.js .
cd reference/epistemic-protocols && node --test scripts/package.test.js anamnesis/scripts/hypomnesis-write.test.mjs

# todo CLI fixtures
cd benchmark/todo-cli-deep-interview && uv run --extra test pytest tests/test_todo.py tests/test_redteam.py
```

## NOTES

This file is intentionally a workspace map. Do not create or edit `AGENTS.md` inside submodules from this root task; use their existing project instructions instead.
