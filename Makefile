PYTHON       = /usr/bin/env python3
VERSION_FILE = ./src/dug/_version.py
VERSION      = $(shell cut -d " " -f 3 ${VERSION_FILE})
DOCKER_REPO  = docker.io
DOCKER_OWNER = helxplatform
DOCKER_APP	 = dug
DOCKER_TAG   = ${VERSION}
DOCKER_IMAGE = ${DOCKER_OWNER}/${DOCKER_APP}:$(DOCKER_TAG)

.DEFAULT_GOAL = help

.PHONY: help clean install test build image publish

#help: List available tasks on this project
help:
	@grep -E '^#[a-zA-Z\.\-]+:.*$$' $(MAKEFILE_LIST) | tr -d '#' | awk 'BEGIN {FS = ": "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

#clean: Remove old build artifacts and installed packages
clean:
	rm -rf build
	rm -rf dist
	rm -rf src/dug.egg-info
	${PYTHON} -m pip uninstall -y dug
	${PYTHON} -m pip uninstall -y -r requirements.txt

#install: Install application along with required development packages
install:
	${PYTHON} -m pip install --upgrade pip
	${PYTHON} -m pip install -r requirements.txt
	${PYTHON} -m pip install .

#test: Run all tests
test: test.doc test.unit test.integration
	${PYTHON} -m pytest --doctest-modules src
	${PYTHON} -m pytest tests

#build: Build wheel and source distribution packages
build.python:
	echo "Building distribution packages for version $(VERSION)"
	${PYTHON} -m pip install --upgrade build
	${PYTHON} -m build --sdist --wheel .
	echo "Successfully built version $(VERSION)"

#build.image: Build the Docker image
build.image:
	echo "Building docker image: ${DOCKER_IMAGE}"
	docker build -t ${DOCKER_IMAGE} -f Dockerfile .
	echo "Successfully built: ${DOCKER_IMAGE}"
	echo "Testing ${DOCKER_IMAGE}"
	docker run ${DOCKER_IMAGE} make test

#build: Build Python artifacts and Docker image
build: build.python build.image

#all: Alias to clean, install, test, build, and image
all: clean install test build

#publish.image: Push the Docker image
publish.image: build.image
	docker tag ${DOCKER_IMAGE} ${DOCKER_REPO}/${DOCKER_IMAGE}
	docker push ${DOCKER_REPO}/${DOCKER_IMAGE}

#publish.python: Push the build artifacts to PyPI
publish.python:
	echo "publishing wheel..."
	echo "publishing source..."

#publish: Push all build artifacts to appropriate repositories
publish: publish.python publish.image