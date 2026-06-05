# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] — 2026-06-05

### Added

- **5-tier instructions file hierarchy**: AGENTS.md (T0), developer onboarding (T1),
  canonical reference docs (T2), skills/procedures (T3), agent briefs (T4).
- **Stale-path automation**: `context_audit.py --instructions-audit` detects stale
  frontmatter, missing brief fields, legacy paths, and AGENTS.md bloat.
- **Standardized agent brief template** (`docs/reference/agent-brief-template.md`)
  with mandatory `source_order`, `goals`, `boundaries`, `composition` sections.
- **CONTRIBUTING.md, SETUP.md** — full developer onboarding and contribution guidelines.
- **docs/INDEX.md** — upgraded navigation hub with staleness map and 5-tier layout.
- **Deduplicated skills**: Hermes skills are canonical masters; Codex skills are thin
  shims deferring to `.hermes/skills/`.
- **`pyproject.toml`** — modern Python project metadata, ruff/mypy/pytest tool configs.
- **`.editorconfig`, `.gitattributes`** — cross-editor and git file consistency.
- **Pre-commit hooks** — ruff lint + format, trailing whitespace, YAML/JSON/TOML
  validation, no large files, no merge conflicts.
- **Makefile** — `make setup`, `make lint`, `make test`, `make audit`, `make format`.
- **GitHub Actions CI** — lint, typecheck, CI-safe tests, freshness audit.
- **Issue/PR templates** — standardized bug reports, feature requests, PR checklist.
- **CHANGELOG.md** — Keep a Changelog format with semantic versioning.
- **Version string** — `src/__init__.py` with `__version__ = "0.4.0"`.

### Changed

- **138 files reformatted** with `ruff format` for consistent code style.
- **All 13 agent briefs** (4 Hermes + 9 Codex) migrated to standard template with
  `version: 1.0.0` and `source_order` frontmatter.
- **`.python-version`** fixed from `unsloth_core_env` to `3.12`.
- **`.gitignore`** consolidated with proper artifact and cache exclusions.
- **`pytest.ini`** migrated into `pyproject.toml` with expanded `norecursedirs`.
- **`docs/project-state.md`** — `Last verified:` text replaced with YAML frontmatter.

### Removed

- **Stale `subjects/` paths** — 80+ references across `.hermes/`, `.codex/`, `docs/`
  updated to `data/` and `artifacts/` equivalents.
- **Duplicated skills** in `.codex/skills/` — 4 skills replaced with thin shims.
- **`CLI-Anything/`, `.opencode/`, `.pi/`** excluded from ruff and pytest scanning.

### Fixed

- **`configs/` ↔ `etc/` duplication** — `configs/` is canonical, `etc/` is a symlink.
- **9 Codex agent briefs** — missing `## Mission` headings added.
- **Template placeholder date** (`YYYY-MM-DD`) in agent brief template.
- **Missing frontmatter** in `.codex/skills/unsloth-core-pipeline-agent/references/subagents.md`.
- **`docs/reference/` stale paths** — 31 legacy `subjects/` references in 4 files fixed.
- **`docs/architecture/`, `docs/guides/`, `docs/planning/` stale paths** — batch-fixed.
- **`SETUP.md`** — `--preset test-readiness` replaced with existing `smoke` preset.
