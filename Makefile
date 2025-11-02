.PHONY: help build run stop test clean logs push deploy destroy

DOCKER_IMAGE := syslog-receiver
DOCKER_TAG := latest

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build:
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .

run:
	docker-compose up -d

stop:
	docker-compose down

test:
	chmod +x test_syslog.sh
	./test_syslog.sh

test-docker:
	chmod +x test_syslog.sh
	./test_syslog.sh --docker

test-docker-keep:
	chmod +x test_syslog.sh
	./test_syslog.sh --docker-keep

clean:
	rm -rf logs/*.log
	docker-compose down -v

logs:
	docker-compose logs -f

shell:
	docker-compose exec syslog-receiver /bin/bash

push: ecr-login build
	docker tag $(DOCKER_IMAGE):$(DOCKER_TAG) $(ECR_REPO):$(DOCKER_TAG)
	docker push $(ECR_REPO):$(DOCKER_TAG)

deploy: push tf-apply

# Development targets
dev: stop build run

restart: stop run ## Restart the service

dev-logs:
	docker-compose logs -f syslog-receiver

dev-test:
	sleep 5  # Wait for service to be ready
	$(MAKE) test
