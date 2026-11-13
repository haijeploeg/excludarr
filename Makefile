.DEFAULT_GOAL := dev-help

DEV_COMPOSE := docker compose -p excludarr-dev
ARGS ?= --help
LIST ?= movies

ifeq ($(origin CONFIG),command line)
$(error CONFIG is no longer needed; edit dev/excludarr.yml)
endif

.PHONY: dev-help dev-up dev-down dev-seed dev-check dev-shell dev dev-daemon dev-daemon-stop dev-feed

dev-help:
	@printf '%s\n' \
	  'Edit dev/excludarr.yml; CLI, shell and daemon all use that file.' \
	  'make dev-up                    Build and start the integration services' \
	  'make dev-seed                  Stop the daemon and restore test fixtures' \
	  'make dev ARGS="preview"        Preview the user config (all rules start in preview)' \
	  'make dev ARGS="run --rule tag --yes"   Apply tag after editing its preview flag' \
	  'make dev-shell                 Bash with the same config and private test credentials' \
	  'make dev-daemon                Start/restart the daemon with the same user config' \
	  'make dev-feed LIST=movies      Read a served list without printing its key' \
	  'make dev-daemon-stop           Stop the manual daemon' \
	  'make dev-check                 Run the separate destructive automated checks' \
	  'make dev-down                  Stop the stack; keep volumes'

dev-up:
	$(DEV_COMPOSE) up -d --build

dev-down:
	$(DEV_COMPOSE) --profile '*' down

dev-seed:
	$(DEV_COMPOSE) stop excludarr
	$(DEV_COMPOSE) run --rm tools seed

dev-check:
	$(DEV_COMPOSE) stop excludarr
	$(DEV_COMPOSE) run --rm tools check

dev-shell:
	$(DEV_COMPOSE) run --rm --entrypoint python tools -m dev.cli --shell

dev:
	$(DEV_COMPOSE) run --rm --entrypoint python tools -m dev.cli $(ARGS)

dev-daemon:
	$(DEV_COMPOSE) --profile daemon up -d --no-deps --force-recreate excludarr

dev-daemon-stop:
	$(DEV_COMPOSE) stop excludarr

dev-feed:
	$(DEV_COMPOSE) run --rm --entrypoint python tools -m dev.cli --feed $(LIST)
