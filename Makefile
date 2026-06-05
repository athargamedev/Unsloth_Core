.PHONY: setup lint format typecheck test audit clean distclean preflight changelog

# ── Environment ──────────────────────────────────────────────────────────────

VENV ?= unsloth_env
ACTIVATE = . $(VENV)/bin/activate

setup: $(VENV)/bin/activate
	@echo "✓ Venv ready"

$(VENV)/bin/activate: requirements.txt
	@if [ ! -d "$(VENV)" ]; then echo "Creating $(VENV)..."; python3 -m venv $(VENV); fi
	$(ACTIVATE) && pip install --upgrade pip setuptools wheel
	$(ACTIVATE) && pip install -r requirements.txt ruff pre-commit mypy
	$(ACTIVATE) && pre-commit install --install-hooks
	@echo "✓ Setup complete"

# ── Code quality ─────────────────────────────────────────────────────────────

lint:
	$(ACTIVATE) && ruff check --no-cache

format:
	$(ACTIVATE) && ruff format --no-cache
	$(ACTIVATE) && ruff check --no-cache --fix --unsafe-fixes

typecheck:
	$(ACTIVATE) && mypy src/ scripts/ --ignore-missing-imports

# ── Testing ──────────────────────────────────────────────────────────────────

test:
	$(ACTIVATE) && python -m pytest -x -q -m "not requires_ollama and not requires_gpu and not requires_supabase and not requires_wandb and not live_model"

test-all:
	$(ACTIVATE) && python -m pytest -x -q

test-fast:
	$(ACTIVATE) && python -m pytest -x -q -m unit

test-contract:
	$(ACTIVATE) && python -m pytest -x -q -m contract

# ── Audits ───────────────────────────────────────────────────────────────────

audit:
	$(ACTIVATE) && python src/core/ops/context_audit.py

audit-instructions:
	$(ACTIVATE) && python src/core/ops/context_audit.py --instructions-audit .hermes .codex docs AGENTS.md

# ── Pipeline ─────────────────────────────────────────────────────────────────

preflight:
	$(ACTIVATE) && ./ucore audit check

# ── Housekeeping ─────────────────────────────────────────────────────────────

clean:
	rm -rf .ruff_cache .mypy_cache .pytest_cache
	rm -rf var/.cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete

distclean: clean
	rm -rf unsloth_env/
	rm -rf .pre-commit-config-local.yaml

changelog:
	@if command -v git-cliff >/dev/null 2>&1; then \
		git-cliff -o CHANGELOG.md; \
		echo "✓ CHANGELOG.md regenerated"; \
	else \
		echo "Install git-cliff for auto-changelog generation"; \
	fi

# ── Help ─────────────────────────────────────────────────────────────────────

help:
	@echo "Targets:"
	@echo "  setup             — Create venv, install deps + pre-commit"
	@echo "  lint              — Run ruff linter"
	@echo "  format            — Auto-format code with ruff"
	@echo "  typecheck         — Run mypy static analysis"
	@echo "  test              — Run non-GPU tests (CI-safe)"
	@echo "  test-all          — Full test suite"
	@echo "  test-fast         — Unit tests only"
	@echo "  test-contract     — Contract/invariant tests"
	@echo "  audit             — Run context stale-path audit"
	@echo "  audit-instructions— Full instructions file freshness audit"
	@echo "  preflight         — Run ucore health check"
	@echo "  clean             — Remove cache dirs"
	@echo "  distclean         — Full cleanup (incl. venv)"
	@echo "  changelog         — Regenerate CHANGELOG.md (needs git-cliff)"
