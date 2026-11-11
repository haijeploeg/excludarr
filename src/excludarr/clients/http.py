"""Shared sync HTTP client with retry/backoff and uniform errors."""

import logging
import math
import time
from collections.abc import Callable
from typing import Any

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 502, 503, 504}


def _sleep(seconds: float) -> None:
    # Module-level so tests can monkeypatch it.
    time.sleep(seconds)


class IntegrationError(Exception):
    def __init__(self, integration: str, message: str, status: int | None = None):
        super().__init__(f"{integration}: {message}")
        self.integration = integration
        self.status = status


class HttpClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        headers: dict[str, str],
        verify: bool = True,
        timeout: float = 30.0,
        retries: int = 4,
        backoff: float = 1.0,
    ):
        self.name = name
        self.retries = retries
        self.backoff = backoff
        self.on_wait: Callable[[str, bool], None] | None = None
        self._client = httpx.Client(
            base_url=base_url, headers=headers, verify=verify, timeout=timeout
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        observer = self.on_wait
        if observer is None:
            return self._request_with_retries(method, path, **kwargs)
        observer(self.name, True)
        try:
            return self._request_with_retries(method, path, **kwargs)
        finally:
            observer(self.name, False)

    def _request_with_retries(self, method: str, path: str, **kwargs: Any) -> Any:
        for attempt in range(self.retries + 1):
            delay = self.backoff * 2**attempt
            try:
                resp = self._client.request(method, path, **kwargs)
            except httpx.TransportError as e:
                cause = type(e).__name__
                if attempt == self.retries:
                    raise IntegrationError(self.name, f"request failed ({cause})") from e
                log.debug(
                    "Retrying %s in %gs after %s (retry %d/%d)",
                    self.name,
                    delay,
                    cause,
                    attempt + 1,
                    self.retries,
                )
                _sleep(delay)
                continue
            if resp.status_code < 400:
                if not resp.content:
                    return None
                try:
                    return resp.json()
                except ValueError as e:
                    raise IntegrationError(self.name, "invalid JSON", resp.status_code) from e
            if resp.status_code in RETRY_STATUSES and attempt < self.retries:
                try:
                    ra = float(resp.headers["Retry-After"])
                    if math.isfinite(ra) and ra >= 0:
                        delay = min(ra, 60.0)
                except (KeyError, ValueError):
                    pass
                log.debug(
                    "Retrying %s in %gs after HTTP %d (retry %d/%d)",
                    self.name,
                    delay,
                    resp.status_code,
                    attempt + 1,
                    self.retries,
                )
                _sleep(delay)
                continue
            raise IntegrationError(self.name, f"HTTP {resp.status_code}", resp.status_code)

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, json: Any = None, params: dict | None = None) -> Any:
        return self._request("POST", path, json=json, params=params)

    def put(self, path: str, json: Any = None, params: dict | None = None) -> Any:
        return self._request("PUT", path, json=json, params=params)

    def delete(self, path: str, params: dict | None = None, json: Any = None) -> Any:
        return self._request("DELETE", path, params=params, json=json)
