# Development reference

This document walks you through running Excludarr v2 and setting up the environment locally.

## Running locally

Requires Python 3.12 or newer.

1. create a virtualenv and install the package with the dev extras:
   `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`
2. copy `.examples/excludarr-example.yml` to `excludarr.yml` (or pass `--config <file>`) and set
   the environment variables it references
3. run excludarr, for example:
   - `.venv/bin/excludarr config validate`
   - `.venv/bin/excludarr --debug preview`
   - `.venv/bin/excludarr run --rule "Streaming movies" --interactive`
   - `.venv/bin/excludarr providers list --locale nl_NL`

### Tests and lint

- `.venv/bin/pytest -q` (tests never hit the network: httpx is mocked with respx)
- `.venv/bin/ruff format src tests && .venv/bin/ruff check src tests`

### Docker

1. in the root folder run `docker build --tag=excludarr .`
2. run `docker run -it --rm -v "$PWD:/config" excludarr:latest preview` with your
   `excludarr.yml` in the current directory, and pass the environment variables it references
   with `-e`. Set `CRON_MODE=true` to run on a schedule instead (see the README).

## Running the testing environment

The root Compose file starts an isolated development project with real Radarr, Sonarr,
Plex, Tautulli and Seerr, generated clips and repeatable test fixtures. Follow
[the stack guide](../dev/README.md) for startup, the one-time Plex test account setup,
seeding, manual scenarios, destructive integration checks, daemon use and reset.
Manual commands all use the tracked `dev/excludarr.yml`; private keys are injected
from the development volumes. Generated configs are internal to `make dev-check`.

```sh
make dev-up
# After one-time account setup:
make dev-seed
make dev ARGS="preview"
make dev-check
```

Arr-only checks work before account setup. Full `seed` and `check` require completing
the local Plex/Tautulli/Seerr wizards. Destructive checks run only when explicitly
invoked and use this stack's fixed internal addresses and fixture identities. Never
mount personal libraries or configuration into this stack. Default pytest remains
offline; these real integration checks are separate.

## Recording the README demo

`docs/demo/demo.gif` is recorded with [VHS](https://github.com/charmbracelet/vhs) against a fake
Radarr (`docs/demo/fake_radarr.py`) with live JustWatch data. From the repo root:

```bash
docker build -t excludarr-demo -f docs/demo/Dockerfile .
docker run --rm -v "$PWD/docs/demo:/vhs" excludarr-demo demo.tape
```

Edit `docs/demo/demo.tape` to change the script and `docs/demo/excludarr.yml` for the rules.

## Commits and releases

Releases are fully automatic. Every push to `main` runs lint and tests; when they pass,
[python-semantic-release](https://python-semantic-release.readthedocs.io/) reads the
[Conventional Commits](https://www.conventionalcommits.org/) since the last tag and decides the
next version:

- `fix: ...` or `perf: ...`: patch release
- `feat: ...`: minor release
- `feat!: ...` or a `BREAKING CHANGE:` footer: major release
- anything else (`chore:`, `docs:`, `ci:`, `test:`, `refactor:`, ...): no release

On a release it bumps the version in `pyproject.toml` and `src/excludarr/__init__.py`, updates
`CHANGELOG.md`, tags `vX.Y.Z`, creates the GitHub release, publishes to PyPI (trusted
publishing) and pushes `ghcr.io/haijeploeg/excludarr` with the `X.Y.Z`, `X.Y`, `X` and `latest`
tags. PRs are merged with "Rebase and merge" only, so every commit in a PR lands on `main` as
is: give each commit a conventional message.


## Daemon and scheduler

The daemon calls the existing core through execution.py, sharing native SQLite-file
locks with manual mutations. scheduling.py owns cron/DST; jobs.py is a pure planner;
daemon.py owns job execution, HTTP/heartbeat and shutdown. Use fake clocks/Events
and mocked integrations for unit tests. Destructive integration checks are confined
to the explicitly started disposable development stack; never target a personal library.
Scheduler records ship in migration 0005. See docs/daemon.md for runtime semantics.
