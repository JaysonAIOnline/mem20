# mem20 packaging shortcuts
PYTHON ?= python3
VENV ?= .venv

.PHONY: help sync venv install dev docker deb npm dashboard test clean

help:
	@echo "mem20 packaging targets:"
	@echo "  make sync     - copy mcp/ into mem20_runtime/mcp (keep package data in sync)"
	@echo "  make venv     - create a venv and install requirements"
	@echo "  make install  - pip install . (builds wheel, installs mem20-mcp)"
	@echo "  make deb      - build the .deb package (packaging/deb/build-deb.sh)"
	@echo "  make docker   - docker build -t mem20 ."
	@echo "  make npm      - build the dashboard (npm run build in dashboard/)"
	@echo "  make test     - run the test suite"
	@echo "  make clean    - remove build artifacts"

sync:
	bash packaging/sync_runtime.sh

venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -U pip
	$(VENV)/bin/pip install -r requirements.txt

install: sync
	$(PYTHON) -m pip install .

dev: sync
	$(PYTHON) -m pip install -e .

deb: sync
	bash packaging/deb/build-deb.sh

docker:
	docker build -t mem20:$$(grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/') .

npm dashboard:
	cd dashboard && npm install && npm run build

test:
	$(PYTHON) -m pytest -q

clean:
	rm -rf build dist *.egg-info dashboard/dist mem20_runtime/mcp
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
