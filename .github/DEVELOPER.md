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

`docker compose up` starts a Radarr instance on `http://localhost:7878` and a Sonarr instance on
`http://localhost:8989`. Add movies and series by hand.

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
tags. With squash merges, the PR title becomes the commit message, so give PRs a conventional
title.
