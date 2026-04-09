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
	@echo "==> 1. Update VERSION file"
	echo $(TAG) > VERSION
	@echo "==> 2. Commit version bump"
	git add VERSION
	git commit -s -m "release: $(TAG)"
	@echo "==> 3. Push to main"
	git push origin HEAD
	@echo "==> 4. Create tag $(TAG)"
	git tag $(TAG)
	@echo "==> 5. Push tag to remote"
	git push origin $(TAG)
	@echo "==> 6. Build and push Docker images"
	sudo docker build -t $(DOCKER_IMAGE):$(TAG) -t $(DOCKER_IMAGE):latest .
	sudo docker push $(DOCKER_IMAGE):$(TAG)
	sudo docker push $(DOCKER_IMAGE):latest

%:
	@:
