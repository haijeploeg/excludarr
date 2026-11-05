from typer.testing import CliRunner

from excludarr.cli import app


def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0 and "2.0.0" in r.stdout


def test_providers_list_with_locale_needs_no_config(monkeypatch, tmp_path):
    import httpx
    import respx

    monkeypatch.chdir(tmp_path)
    pk = {
        "packageId": 8,
        "clearName": "Netflix",
        "shortName": "nfx",
        "monetizationTypes": ["FLATRATE"],
    }
    with respx.mock:
        route = respx.post("https://apis.justwatch.com/graphql").mock(
            return_value=httpx.Response(200, json={"data": {"packages": [pk]}})
        )
        r = CliRunner().invoke(app, ["providers", "list", "--locale", "nl_NL"])
    assert r.exit_code == 0 and "Netflix" in r.stdout
    assert b'"country":"NL"' in route.calls[0].request.content


def test_providers_list_invalid_config_exits_1(tmp_path):
    bad = tmp_path / "excludarr.yml"
    bad.write_text("bogus: 1\n")
    r = CliRunner().invoke(app, ["--config", str(bad), "providers", "list"])
    assert r.exit_code == 1
