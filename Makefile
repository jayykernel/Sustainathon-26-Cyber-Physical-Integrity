.PHONY: all setup dev serve demo-data test test-quick lint typecheck fit-twin plot-nominal calibrate eval-passive stealth-report localization-report probe-report guard-report eval eval-repeatability build check clean

PYTHON ?= python
ifeq ($(OS),Windows_NT)
VENV_PYTHON = backend/.venv/Scripts/python.exe
else
VENV_PYTHON = backend/.venv/bin/python
endif

all: setup

setup:
	$(PYTHON) -m venv backend/.venv
	$(VENV_PYTHON) -m pip install -r backend/requirements.lock
	$(VENV_PYTHON) -m pip install --no-deps -e backend
	npm ci --prefix frontend

dev: setup
	$(VENV_PYTHON) scripts/dev.py

test:
	$(VENV_PYTHON) -m pytest backend/tests/ -v --tb=short
	npm --prefix frontend test

test-quick:
	$(VENV_PYTHON) -m pytest backend/tests/ -v --tb=short -m "not slow and not integration"

lint:
	$(VENV_PYTHON) -m ruff check backend/src/ backend/tests/ --config backend/pyproject.toml
	npm --prefix frontend run lint

typecheck:
	$(VENV_PYTHON) -m mypy backend/src/ --strict --config-file backend/pyproject.toml
	npm --prefix frontend run typecheck

fit-twin:
	$(VENV_PYTHON) scripts/fit_twin.py --write

plot-nominal:
	$(VENV_PYTHON) scripts/plot_nominal.py

calibrate:
	$(VENV_PYTHON) -m physiguard.eval.calibrate

eval-passive:
	$(VENV_PYTHON) -m physiguard.eval.evaluate_test_fa

stealth-report:
	$(VENV_PYTHON) scripts/stealth_report.py

localization-report:
	$(VENV_PYTHON) scripts/localization_report.py

probe-report:
	$(VENV_PYTHON) scripts/probe_report.py

guard-report:
	$(VENV_PYTHON) scripts/p6_guard_report.py

eval:
	$(VENV_PYTHON) -m physiguard.eval.cli

eval-repeatability:
	$(VENV_PYTHON) -m pytest backend/tests/test_evaluation.py -q

serve:
	$(VENV_PYTHON) scripts/dev.py

demo-data:
	$(VENV_PYTHON) scripts/demo_data.py

build:
	npm --prefix frontend run build

check: lint typecheck test build
	@echo All checks passed.

clean:
	$(PYTHON) scripts/clean.py
