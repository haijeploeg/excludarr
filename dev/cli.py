"""Launch the normal CLI with the one editable manual development configuration."""

import json
import os
import sys
import time
from pathlib import Path

import httpx

from dev import stack
from dev.stack import SetupError
from excludarr.config import ConfigError, load_config

CONFIG = Path("/config/user/excludarr.yml")
REAL_CLI = str(Path(sys.executable).with_name("excludarr"))
KEYS = {
    "radarr": "RADARR_API_KEY",
    "sonarr": "SONARR_API_KEY",
    "plex": "PLEX_TOKEN",
    "tautulli": "TAUTULLI_API_KEY",
    "seerr": "SEERR_API_KEY",
    "feed": "LIST_PROXY_API_KEY",
}


def environment() -> dict[str, str]:
    keys = stack.credentials()
    if not all(keys.get(name) for name in KEYS):
        raise SetupError("Finish account setup and run make dev-seed first")
    state = json.loads((stack.CONFIG / "state.json").read_text())
    username = state.get("plex", {}).get("username")
    if not username:
        raise SetupError("Run the full make dev-seed to resolve the test user")
    return (
        os.environ
        | {env: keys[name] for name, env in KEYS.items()}
        | {"EXCLUDARR_CONFIG": str(CONFIG), "DEV_PLEX_USER": username}
    )


def validate_config(path: Path = CONFIG):
    config, _ = load_config(path)
    for name, integration in vars(config.integrations).items():
        if integration and integration.url != stack.SERVICES[name]:
            raise SetupError(f"{name}: manual config must use the fixed development service URL")
    if config.database != "sqlite:////config/manual.db":
        raise SetupError(
            "Manual config must use sqlite:////config/manual.db, separate from automated tests"
        )
    return config


def main() -> None:
    args = sys.argv[1:] or ["--help"]
    env = {}
    try:
        if any(arg == "--config" or arg.startswith("--config=") for arg in args):
            raise SetupError("Edit dev/excludarr.yml; the development launcher uses only that file")
        if args in (["--help"], ["--version"]):
            os.execvpe(REAL_CLI, [REAL_CLI, *args], os.environ)
        env = environment()
        os.environ.update(env)
        config = validate_config()
        stack.verify_stack(full=True)
        if args[0] == "--shell":
            env["PATH"] = str(Path(__file__).with_name("bin")) + os.pathsep + env.get("PATH", "")
            os.execvpe("bash", ["bash"], env)
        if args[0] == "--feed":
            if len(args) != 2 or not config.list_proxy or args[1] not in config.list_proxy.lists:
                raise SetupError("Choose a list name from dev/excludarr.yml")
            # Docker start can finish before HTTP and the initial snapshot are ready.
            deadline = time.monotonic() + 30
            with httpx.Client(timeout=5, trust_env=False) as client:
                while time.monotonic() < deadline:
                    try:
                        response = client.get(
                            f"http://excludarr:8989/lists/{args[1]}",
                            params={"apikey": config.list_proxy.api_key.get_secret_value()},
                        )
                        if response.status_code == 200:
                            print(json.dumps(response.json(), indent=2))
                            return
                        if response.status_code != 503:
                            raise SetupError(
                                f"Feed returned HTTP {response.status_code}; check daemon/config"
                            )
                    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                        pass
                    time.sleep(1)
            raise SetupError("Feed not ready; start make dev-daemon and refresh the selected list")
        os.execvpe(REAL_CLI, [REAL_CLI, "--config", str(CONFIG), *args], env)
    except (SetupError, ConfigError, OSError, ValueError, KeyError, httpx.HTTPError) as error:
        if isinstance(error, (SetupError, ConfigError)):
            message = str(error)
            for name, value in env.items():
                if value and any(
                    part in name for part in ("TOKEN", "KEY", "SECRET", "PASSWORD", "CLIENT_ID")
                ):
                    message = message.replace(value, "[redacted]")
        else:
            message = f"Development launcher failed ({type(error).__name__}); check setup/config"
        print(message, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
