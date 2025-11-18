.PHONY: help build run stop test clean logs push deploy destroy

DOCKER_IMAGE := syslog-receiver
DOCKER_TAG := latest
AWS_REGION := us-east-1
AWS_ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text)
ECR_REPO := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(DOCKER_IMAGE)

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build Docker image
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

run: ## Run with Docker Compose
	docker-compose up -d

stop: ## Stop Docker Compose services
	docker-compose down

test: ## Run pytest test suite
	pytest tests/ -v

test-unit: ## Run unit tests only (fast)
	pytest tests/test_syslog_parser.py tests/test_deduplicator.py tests/test_syslog_writer.py -v

test-integration: ## Run integration tests
	pytest tests/test_integration.py -v

test-scenarios: ## Run real-world scenario tests
	pytest tests/test_scenarios.py -v

test-coverage: ## Run tests with coverage report
	pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "Coverage report generated: htmlcov/index.html"

test-fast: ## Run tests in parallel
	pytest tests/ -n auto -v

test-bash: ## Run bash test script (assumes service is running)
	chmod +x test_syslog.sh
	./test_syslog.sh

test-docker: ## Start Docker, run bash tests, then stop
	chmod +x test_syslog.sh
	./test_syslog.sh --docker

test-docker-keep: ## Start Docker, run bash tests, keep running
	chmod +x test_syslog.sh
	./test_syslog.sh --docker-keep

clean: ## Clean up logs and temporary files
	rm -rf logs/*.log
	docker-compose down -v

logs: ## View logs from Docker Compose
	docker-compose logs -f

shell: ## Get a shell in the running container
	docker-compose exec syslog-receiver /bin/bash

# AWS/ECR targets
ecr-login: ## Login to AWS ECR
	aws ecr get-login-password --region $(AWS_REGION) | docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com

push: ecr-login build ## Build and push image to ECR
	docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(ECR_REPO):$(DOCKER_TAG)
	docker push $(ECR_REPO):$(DOCKER_TAG)

# Terraform targets
tf-init: ## Initialize Terraform
	cd terraform && terraform init

tf-plan: ## Run Terraform plan
	cd terraform && terraform plan

tf-apply: ## Apply Terraform configuration
	cd terraform && terraform apply

tf-destroy: ## Destroy Terraform resources
	cd terraform && terraform destroy

deploy: push tf-apply ## Build, push image and deploy infrastructure

# Development targets
dev: stop build run ## Build and run for development (stops existing containers first)

restart: stop run ## Restart the service

dev-logs: ## Show application logs in real-time
	docker-compose logs -f syslog-receiver

dev-test: ## Run tests against development instance
	sleep 5  # Wait for service to be ready
	$(MAKE) test

