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

The testing environment is composed of a Radarr instance and a Sonarr instance, we also have `arr-setup` a tool to automatically populate both Radarr and Sonarr based on a config. You can run the environment both with or without `arr-setup`, if you don't run it you'll just have to add movies/series manually.

This whole environment can be run both through docker compose or by running each component by hand.

### Without `arr-setup`

Steps to run the environment:

1. run `docker compose up` (by default only Radarr and Sonarr will run)
2. done

With the default `docker-compose.yml` you can reach radarr on `http://localhost:7878` and sonarr on `http://localhost:8989`

### With `arr-setup`

Steps to run the environment:

1. write your config file and put it in the `arr_setup_config` volume that will be mounted. The name of the config should be `config.yml` and you can find an example config file in `arr-setup/.examples/arr-setup-example.yml`
2. run `docker compose --profile setup up`
3. make sure that the logs for `setup-arr` and `config_setup_arr` do not contain errors
4. done

With the default `docker-compose.yml` you can reach radarr on `http://localhost:7878` and sonarr on `http://localhost:8989`
