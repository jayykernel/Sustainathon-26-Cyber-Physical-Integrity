.PHONY: all setup dev serve demo-data download-calce test test-quick lint typecheck fit-twin plot-nominal calibrate calibrate-probe eval-passive stealth-report localization-report probe-report guard-report eval eval-repeatability failure-drill build check clean

PYTHON ?= python
UV ?= uv
BUN ?= bun
# Frontend package manager: use bun by default, or `make <target> JS_PM=npm`.
JS_PM ?= bun
ifeq ($(JS_PM),npm)
JS_INSTALL = npm ci
JS_RUN = npm run
else
JS_INSTALL = $(BUN) install
JS_RUN = $(BUN) run
endif
ifeq ($(OS),Windows_NT)
VENV_PYTHON = backend/.venv/Scripts/python.exe
else
VENV_PYTHON = backend/.venv/bin/python
endif

all: setup

setup:
	$(UV) venv backend/.venv --python 3.12
	$(UV) pip install --python $(VENV_PYTHON) -r backend/requirements.lock
	$(UV) pip install --python $(VENV_PYTHON) --no-deps -e backend
	cd static-website && $(JS_INSTALL)

dev:
	$(VENV_PYTHON) scripts/dev.py --pm $(JS_PM)

test:
	$(VENV_PYTHON) -m pytest backend/tests/ -v --tb=short
	cd static-website && $(JS_RUN) test

test-quick:
	$(VENV_PYTHON) -m pytest backend/tests/ -v --tb=short -m "not slow and not integration"
	cd static-website && $(JS_RUN) test

lint:
	$(VENV_PYTHON) -m ruff check backend/src/ backend/tests/ --config backend/pyproject.toml

typecheck:
	$(VENV_PYTHON) -m mypy backend/src/ --strict --config-file backend/pyproject.toml
	cd static-website && $(JS_RUN) typecheck

fit-twin:
	$(VENV_PYTHON) scripts/fit_twin.py --write

plot-nominal:
	$(VENV_PYTHON) scripts/plot_nominal.py

calibrate:
	$(VENV_PYTHON) -m physiguard.eval.calibrate

calibrate-probe:
	$(VENV_PYTHON) scripts/calibrate_probe.py

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

failure-drill:
	$(VENV_PYTHON) scripts/failure_drill.py

serve:
	$(VENV_PYTHON) scripts/dev.py --pm $(JS_PM)

demo-data:
	$(VENV_PYTHON) scripts/demo_data.py

download-calce:
	$(VENV_PYTHON) scripts/download_calce.py

build:
	cd static-website && $(JS_RUN) build

check: lint typecheck test build
	@echo All checks passed.

clean:
	$(PYTHON) scripts/clean.py
