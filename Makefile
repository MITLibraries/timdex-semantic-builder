SHELL=/bin/bash
DATETIME:=$(shell date -u +%Y%m%dT%H%M%SZ)

### This is the Terraform-generated header for timdex-semantic-builder-dev. If
###   this is a Lambda repo, uncomment the FUNCTION line below
###   and review the other commented lines in the document.
ECR_NAME_DEV := timdex-semantic-builder-dev
ECR_URL_DEV := 222053980223.dkr.ecr.us-east-1.amazonaws.com/timdex-semantic-builder-dev
CPU_ARCH ?= $(shell cat .aws-architecture 2>/dev/null || echo "linux/amd64")
FUNCTION_DEV := timdex-semantic-builder-dev
### End of Terraform-generated header

help: # Preview Makefile commands
	@awk 'BEGIN { FS = ":.*#"; print "Usage:  make <target>\n\nTargets:" } \
/^[-_[:alpha:]]+:.?*#/ { printf "  %-15s%s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ensure OS binaries aren't called if naming conflict with Make recipes
.PHONY: help venv install update test coveralls lint black mypy ruff safety lint-apply black-apply ruff-apply check-arch dist-dev publish-dev update-lambda-dev docker-clean

##############################################
# Python Environment and Dependency commands
##############################################

install: .venv .git/hooks/pre-commit # Install Python dependencies, hooks, and create virtual environment if not exists
	uv sync --dev

.venv: # Creates virtual environment if not found
	@echo "Creating virtual environment at .venv..."
	uv venv .venv

.git/hooks/pre-commit: # Sets up pre-commit hook if not setup
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install

venv: .venv # Create the Python virtual environment

update: # Update Python dependencies
	uv lock --upgrade
	uv sync --dev

######################
# Unit test commands
######################

test: # Run tests and print a coverage report
	uv run coverage run --source=lambdas -m pytest -vv
	uv run coverage report -m

coveralls: test # Write coverage data to an LCOV report
	uv run coverage lcov -o ./coverage/lcov.info

####################################
# Code quality and safety commands
####################################

lint: black mypy ruff # Run linters

black: # Run 'black' linter and print a preview of suggested changes
	uv run black --check --diff .

mypy: # Run 'mypy' linter
	uv run mypy .

ruff: # Run 'ruff' linter and print a preview of errors
	uv run ruff check .

safety: # Check for security vulnerabilities
	uv run pip-audit

lint-apply: black-apply ruff-apply # Apply changes with 'black' and resolve 'fixable errors' with 'ruff'

black-apply: # Apply changes with 'black'
	uv run black .

ruff-apply: # Resolve 'fixable errors' with 'ruff'
	uv run ruff check --fix .

####################################
# SAM Lambda
####################################
sam-build: # Build SAM image for running Lambda locally
	sam build --template tests/sam/template.yaml

sam-http-run: # Run lambda locally as an HTTP server
	sam local start-api --template tests/sam/template.yaml --env-vars tests/sam/env.json

sam-http-ping: # Send curl command to SAM HTTP server
	curl --location 'http://localhost:3000/myapp' \
	--header 'Content-Type: application/json' \
	--data '{"msg":"in a bottle"}'

####################################
# Deployment to ECR
####################################
### Terraform-generated Developer Deploy Commands for Dev environment ###
check-arch:
	@ARCH_FILE=".aws-architecture"; \
	if [[ "$(CPU_ARCH)" != "linux/amd64" && "$(CPU_ARCH)" != "linux/arm64" ]]; then \
        echo "Invalid CPU_ARCH: $(CPU_ARCH)"; exit 1; \
    fi; \
	if [[ -f $$ARCH_FILE ]]; then \
		echo "latest-$(shell echo $(CPU_ARCH) | cut -d'/' -f2)" > .arch_tag; \
	else \
		echo "latest" > .arch_tag; \
	fi

dist-dev: check-arch ## Build docker container (intended for developer-based manual build)
	@ARCH_TAG=$$(cat .arch_tag); \
	docker buildx inspect $(ECR_NAME_DEV) >/dev/null 2>&1 || docker buildx create --name $(ECR_NAME_DEV) --use; \
	docker buildx use $(ECR_NAME_DEV); \
	docker buildx build --platform $(CPU_ARCH) \
		--load \
	    --tag $(ECR_URL_DEV):$$ARCH_TAG \
	    --tag $(ECR_URL_DEV):make-$$ARCH_TAG \
		--tag $(ECR_URL_DEV):make-$(shell git describe --always) \
		--tag $(ECR_NAME_DEV):$$ARCH_TAG \
		.

publish-dev: dist-dev ## Build, tag and push (intended for developer-based manual publish)
	@ARCH_TAG=$$(cat .arch_tag); \
	aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(ECR_URL_DEV); \
	docker push $(ECR_URL_DEV):$$ARCH_TAG; \
	docker push $(ECR_URL_DEV):make-$$ARCH_TAG; \
	docker push $(ECR_URL_DEV):make-$(shell git describe --always); \
    echo "Cleaning up dangling Docker images..."; \
    docker image prune -f --filter "dangling=true"

## If this is a Lambda repo, uncomment the two lines below
update-lambda-dev: ## Updates the lambda with whatever is the most recent image in the ecr (intended for developer-based manual update)
	@ARCH_TAG=$$(cat .arch_tag); \
	aws lambda update-function-code \
		--region us-east-1 \
		--function-name $(FUNCTION_DEV) \
		--image-uri $(ECR_URL_DEV):make-$$ARCH_TAG

docker-clean: ## Clean up Docker detritus generated by dist-dev and publish-dev
	@ARCH_TAG=$$(cat .arch_tag); \
	echo "Cleaning up Docker leftovers (containers, images, builders)"; \
	docker rmi -f $(ECR_URL_DEV):$$ARCH_TAG; \
	docker rmi -f $(ECR_URL_DEV):make-$$ARCH_TAG; \
	docker rmi -f $(ECR_URL_DEV):make-$(shell git describe --always) || true; \
    docker rmi -f $(ECR_NAME_DEV):$$ARCH_TAG || true; \
	docker buildx rm $(ECR_NAME_DEV) || true
	@rm -rf .arch_tag
