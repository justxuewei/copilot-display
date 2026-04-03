.PHONY: install run clean

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/activate
	$(PIP) install -e .

run: install
	$(VENV)/bin/copilot-display

clean:
	rm -rf $(VENV)
