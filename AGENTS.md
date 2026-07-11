# PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-07
**Commit:** 77b0327
**Branch:** master

## OVERVIEW

This checkout is a harness workspace, not a single product. It contains seven declared submodules plus local todo CLI experiment fixtures and agent workflow artifacts.

## STRUCTURE

```text
harnesses/
|-- oh-my-codex/              # OMX TypeScript/Rust orchestration layer
|-- codex/                    # OpenAI Codex CLI/app-server Rust workspace
|-- ouroboros/                # Agent OS Python project; has its own AGENTS.md
|-- skills/                   # Matt Pocock skill catalog and docs source
|-- SkillOpt/                 # Python skill optimization research + sleep engine
|-- lazycodex/                # LazyCodex / OmO Codex harness installer and marketplace
|-- epistemic-protocols/      # Epistemic protocol plugin marketplace and protocol skills
|-- todo-cli*/                # Small Python CLI experiment arms
|-- .agents/                  # Local harness skill copies, notably ultimateinterview
|-- .omo/                     # OMO runtime/evidence artifacts
|-- .ultimateinterview/       # Interview ledgers and protocol artifacts
`-- docs/                     # Current root docs, including renamed ultimateinterview files
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Root workspace boundaries | `.gitmodules` | Submodules are `ouroboros`, `oh-my-codex`, `skills`, `SkillOpt`, `lazycodex`, `epistemic-protocols`, `codex`. |
| OMX CLI/runtime work | `oh-my-codex/` | Submodule. Use `oh-my-codex/README.md`, `CONTRIBUTING.md`, `package.json`. |
| OpenAI Codex CLI/runtime work | `codex/` | Submodule. Use `codex/AGENTS.md`, `README.md`, and the relevant `codex-rs/` crate. |
| Ouroboros commands | `ouroboros/AGENTS.md` | Existing router for `ooo` commands; do not replace casually. |
| Skill catalog edits | `skills/` | Submodule. Bucket/docs/plugin rules live in `skills/CLAUDE.md` and `CONTEXT.md`. |
| SkillOpt training/sleep work | `SkillOpt/` | Submodule. Use `SkillOpt/README.md`, `CONTRIBUTING.md`, `pyproject.toml`. |
| LazyCodex / OmO harness work | `lazycodex/` | Submodule. Use `lazycodex/README.md`, `package.json`. |
| Epistemic protocol/plugin work | `epistemic-protocols/` | Submodule. Has its own `AGENTS.md`; use `epistemic-protocols/README.md`, protocol directories, and `package.json`. |
| Todo CLI acceptance harnesses | `todo-cli*` | Small Python apps; use their local `pyproject.toml` and README contracts. |
| Deep interview policy copies | `.agents/skills/ultimateinterview/` | Local harness copy of interview instructions and lessons. |
| Evidence artifacts | `.omo/evidence/`, `todo-cli-*/artifacts/` | Treat as observed outputs unless the task explicitly asks to regenerate. |

## CODE MAP

Codegraph tools were not exposed in this harness, and LSP had no active TS/Python clients during generation. Symbol/reference centrality below is therefore from `rg`/file-count evidence, not measured references.

| Symbol or Surface | Type | Location | Role |
|-------------------|------|----------|------|
| `omx` | CLI bin | `oh-my-codex/package.json` | Primary OMX command surface. |
| `run-test-files.ts` | Test runner | `oh-my-codex/src/scripts/run-test-files.ts` | Compiled Node test harness used by package scripts. |
| `templates/AGENTS.md` | Runtime template | `oh-my-codex/templates/AGENTS.md` | Generated workspace operating contract template. |
| `parse_ooo_command` | Parser | `ouroboros/src/ouroboros/router/command_parser.py` | Ouroboros command parsing path. |
| `resolve_packaged_skill_path` | Resolver | `ouroboros/src/ouroboros/router/dispatch.py` | Packaged skill lookup and dispatch. |
| `ReflACTTrainer` | Class | `SkillOpt/skillopt/engine/trainer.py` | Main SkillOpt training loop. |
| `EnvAdapter` | Class | `SkillOpt/skillopt/envs/base.py` | Benchmark environment interface. |
| `cmd_run` | CLI handler | `SkillOpt/skillopt_sleep/__main__.py` | Sleep-cycle entry point. |
| `lazycodex-ai` | CLI bin | `lazycodex/package.json` | Codex install alias for LazyCodex / OmO setup. |
| `epistemic-protocols` | Marketplace | `epistemic-protocols/.agents/plugins/marketplace.json` | Codex marketplace for the epistemic protocol plugins. |
| `todo` | Console script | `todo-cli*/pyproject.toml` | Shared experiment CLI entry name. |

## CONVENTIONS

- Root is a coordination checkout. Run builds/tests inside the relevant subproject; root has no unified build.
- Do not treat `uam-api-service` as local source; it is a symlink to `/Users/jpark/IdeaProjects/uam-api-service`.
- Submodule roots have their own git status and ownership. Check `git -C <dir> status` before editing inside them.
- Hidden directories `.gjc`, `.omo`, `.ultimateinterview`, and `.agents` are harness/runtime state, not product packages.
- Existing dirty root docs rename `docs/ultrainterview-*` to `docs/ultimateinterview-*`; leave unrelated doc churn alone.

## ANTI-PATTERNS (THIS PROJECT)

- Do not overwrite `ouroboros/AGENTS.md`; it is an active command router with managed `ooo` sections.
- Do not count `.venv`, `node_modules`, `dist`, `build`, `.pytest_cache`, or generated artifacts when assessing project complexity.
- Do not put credentials directly in example MCP config; `ouroboros/docs/examples/mcp-config.yaml` calls this out explicitly.
- Do not assume a literal `init-deep` implementation exists in this checkout. The invoked skill came from the installed OMO plugin.

## COMMANDS

```bash
# Root inventory
git status --short --branch
git submodule status

# oh-my-codex
cd oh-my-codex && npm run build && npm run lint
cd oh-my-codex && npm test

# ouroboros
cd ouroboros && uv run pytest
cd ouroboros && uv run ruff check src tests

# skills
cd skills && npm run changeset

# SkillOpt
cd SkillOpt && pip install -e ".[dev]"
cd SkillOpt && pytest

# lazycodex
cd lazycodex && npm test
cd lazycodex && npm run pack:dry-run

# epistemic-protocols
cd epistemic-protocols && node .claude/skills/verify/scripts/static-checks.js .
cd epistemic-protocols && node --test scripts/package.test.js anamnesis/scripts/hypomnesis-write.test.mjs

# todo CLI fixtures
cd todo-cli-deep-interview && python -m pytest tests/test_todo.py tests/test_redteam.py
```

## NOTES

This file is intentionally a workspace map. Do not create or edit `AGENTS.md` inside submodules from this root task; use their existing project instructions instead.
