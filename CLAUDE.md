# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Excludarr v2 is a Typer CLI rule engine for Radarr (movies) and Sonarr (series). YAML rules (conditions plus an action) decide what is deleted, unmonitored, monitored, tagged or import-excluded. JustWatch availability is one condition among Radarr/Sonarr, Tautulli and Seerr data. Spec: `docs/superpowers/specs/2026-11-05-library-rules-design.md` (binding).

## Current state

- v2 is a breaking rewrite (src layout, hatchling, version 2.0.0) of the v1 poetry/pyarr code. v1 history: the canonical v1 source was `github.com/excludarr/excludarr` (remote `org`); `origin/v2` is an abandoned Django rewrite.
- Never commit unprompted (user rule). Never add AI attribution (Co-Authored-By, "Generated with") to commits or PRs.
- Releases are automatic: `.github/workflows/ci.yml` runs lint + tests, then python-semantic-release (config in `pyproject.toml`) versions from Conventional Commits and publishes to PyPI (trusted publishing) and `ghcr.io/haijeploeg/excludarr`. Commit messages and squash-merge PR titles must be conventional.

## Commands

```bash
python3.14 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q                                  # no network: respx + fakes
.venv/bin/ruff format src tests && .venv/bin/ruff check src tests   # line length 100
.venv/bin/excludarr --config .examples/excludarr-example.yml config validate
docker build -t excludarr:dev . && docker run --rm excludarr:dev --version
```

## Architecture (`src/excludarr`)

- `cli.py`: Typer app (`run`, `preview`, `queue`, `rescue`, `history`, `exceptions`, `providers`, `config`); thin layer over the core. `output.py` renders rich tables.
- `config.py`: pydantic models (`Config`, `Rule`, `Integrations`, `Profile`), `${VAR}` substitution inside parsed string values (after YAML parsing, so values never become YAML or leak into parse errors), config search path, URL normalization.
- `conditions.py`: leaf registry `LEAVES` (name, parse, evaluate, label, required integrations, targets/levels) plus `all`/`any`/`not` parsing. Three-valued logic: `True`/`False`/`None` (unknown). A rule acts only when `when` is True and `unless` is False.
- `items.py`: `MediaItem` (movie, series, season, episode with inherited series attributes). `facts.py`: lazy lookups (streaming, watch, requests) that return `None` when unknown.
- `engine.py`: evaluates rules in file order, preview, grace queue, exceptions, Leaving Soon collection. `actions.py`: executes an action plus side effects (queue cleanup, Seerr clear, Plex refresh); a failed side effect does not roll back the action.
- `clients/`: one httpx client per integration on `http.py` (retry, timeouts); `justwatch.py` (GraphQL, queries in `justwatch_queries.py`), `radarr.py`, `sonarr.py`, `tautulli.py`, `seerr.py`, `plex.py`.
- `storage/`: SQLAlchemy models and `repo.py` (queue, exceptions, history, cache); alembic migrations in `storage/migrations` ship in the wheel.
- Docker: `entrypoint.sh` runs `excludarr "$@"`, or `crond -f` with `/config/crontab` when `CRON_MODE=true`. Config is `/config/excludarr.yml`; no env-to-YAML generation.
- Open item: the Plex Leaving Soon collection request shape is unverified against a real server.
