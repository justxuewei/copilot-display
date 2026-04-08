.PHONY: install run clean docker-build docker-push tag

VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

DOCKER_IMAGE ?= xavierniu/copilot-display
VERSION ?= latest

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/activate
	$(PIP) install -e .

run: install
	$(VENV)/bin/copilot-display

clean:
	rm -rf $(VENV)

docker-build:
	docker build -t $(DOCKER_IMAGE):$(VERSION) .

docker-push: docker-build
	docker push $(DOCKER_IMAGE):$(VERSION)

tag:
	$(eval TAG := $(filter-out $@,$(MAKECMDGOALS)))
	$(if $(TAG),,$(error Usage: make tag <version>))
	git tag $(TAG)
	git push origin $(TAG)
	$(MAKE) docker-push VERSION=$(TAG)

%:
	@:
