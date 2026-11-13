"""Credential-safe diagnostics shared by core execution and background jobs."""

from pydantic import BaseModel, SecretStr


def safe_error(config, error):
    message = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)

    def redact(value):
        nonlocal message
        if isinstance(value, BaseModel):
            for name in type(value).model_fields:
                item = getattr(value, name)
                if name in {"api_key", "token", "tmdb_token", "client_id", "url"} and item:
                    secret = item.get_secret_value() if isinstance(item, SecretStr) else str(item)
                    message = message.replace(secret, "[redacted]")
                else:
                    redact(item)
        elif isinstance(value, dict):
            for item in value.values():
                redact(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                redact(item)

    redact(config)
    return message
