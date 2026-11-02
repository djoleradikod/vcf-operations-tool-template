# Convenience targets. Every target is a plain command you can run without make.
PY ?= python

.PHONY: setup render check test lint privacy build release-notes

setup:            ## install the tool and development dependencies
	$(PY) -m pip install -e ".[dev]" && pre-commit install

render:           ## regenerate README/docs/metadata from tool.yaml
	$(PY) scripts/repokit.py render

lint:
	ruff check . && ruff format --check .

test:
	pytest --cov

privacy:
	$(PY) scripts/repokit.py privacy

check: lint test privacy  ## everything CI runs
	$(PY) scripts/repokit.py check

build:
	$(PY) -m build --outdir dist && $(PY) scripts/repokit.py bundle --outdir dist && \
	$(PY) scripts/repokit.py project-json -o dist/project.json

release-notes:    ## make release-notes VERSION=1.2.0
	$(PY) scripts/repokit.py release-notes $(VERSION)
