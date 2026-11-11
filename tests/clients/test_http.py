import httpx
import pytest
import respx

from excludarr.clients import http
from excludarr.clients.http import HttpClient, IntegrationError

BASE = "http://svc.test/api"


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(http, "_sleep", calls.append)
    return calls


@respx.mock
def test_retries_on_503_then_succeeds(sleeps):
    route = respx.get(f"{BASE}/x").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    client = HttpClient("svc", BASE, {}, backoff=0)
    assert client.get("/x") == {"ok": True}
    assert route.call_count == 2


@respx.mock
def test_honors_retry_after(sleeps):
    respx.get(f"{BASE}/x").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200)]
    )
    client = HttpClient("svc", BASE, {}, backoff=0)
    assert client.get("/x") is None  # empty body
    assert sleeps == [7.0]


@respx.mock
def test_raises_integration_error_on_404(sleeps):
    route = respx.get(f"{BASE}/x").mock(return_value=httpx.Response(404, text="nope" * 100))
    client = HttpClient("svc", BASE, {}, backoff=0)
    with pytest.raises(IntegrationError) as e:
        client.get("/x")
    assert e.value.status == 404
    assert e.value.integration == "svc"
    assert route.call_count == 1
    assert len(str(e.value)) < 300


@respx.mock
def test_raises_after_retries_exhausted(sleeps):
    route = respx.get(f"{BASE}/x").mock(return_value=httpx.Response(503))
    client = HttpClient("svc", BASE, {}, retries=2, backoff=0)
    with pytest.raises(IntegrationError) as e:
        client.get("/x")
    assert e.value.status == 503
    assert route.call_count == 3


@respx.mock
def test_retries_on_transport_error(sleeps):
    respx.get(f"{BASE}/x").mock(side_effect=[httpx.ConnectError("boom"), httpx.Response(200)])
    client = HttpClient("svc", BASE, {}, backoff=0)
    assert client.get("/x") is None


@respx.mock
def test_500_not_retried(sleeps):
    route = respx.get(f"{BASE}/x").mock(return_value=httpx.Response(500))
    with pytest.raises(IntegrationError) as e:
        HttpClient("svc", BASE, {}, backoff=0).get("/x")
    assert e.value.status == 500
    assert route.call_count == 1


@respx.mock
def test_invalid_json_on_2xx(sleeps):
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(IntegrationError, match="invalid JSON") as e:
        HttpClient("svc", BASE, {}, backoff=0).get("/x")
    assert e.value.status == 200


@respx.mock
def test_exponential_backoff_sequence(sleeps):
    respx.get(f"{BASE}/x").mock(return_value=httpx.Response(503))
    with pytest.raises(IntegrationError):
        HttpClient("svc", BASE, {}, retries=3, backoff=1).get("/x")
    assert sleeps == [1, 2, 4]


@pytest.mark.parametrize(
    ("header", "expected"), [("nan", 1), ("inf", 1), ("-5", 1), ("abc", 1), ("999", 60.0)]
)
@respx.mock
def test_retry_after_sanitized(sleeps, header, expected):
    respx.get(f"{BASE}/x").mock(
        side_effect=[httpx.Response(429, headers={"Retry-After": header}), httpx.Response(200)]
    )
    HttpClient("svc", BASE, {}, backoff=1).get("/x")
    assert sleeps == [expected]


@respx.mock
def test_wait_covers_retries_and_failures_without_logging_payloads(sleeps, caplog):
    respx.get(f"{BASE}/x").mock(
        side_effect=[httpx.Response(503, text="secret"), httpx.Response(403, text="secret")]
    )
    client = HttpClient("svc", BASE, {}, backoff=0)
    waiting = []
    client.on_wait = lambda name, active: waiting.append((name, active))
    with caplog.at_level("DEBUG", logger=http.__name__), pytest.raises(IntegrationError) as exc:
        client.get("/x")
    assert waiting == [("svc", True), ("svc", False)]
    assert "Retrying svc" in caplog.text and "HTTP 503" in caplog.text
    assert "secret" not in caplog.text and "secret" not in str(exc.value)
