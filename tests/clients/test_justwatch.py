import httpx
import respx

from excludarr.clients.justwatch import JustWatchClient, normalize_locale

GQL = "https://apis.justwatch.com/graphql"


def offer(pid, mon="FLATRATE"):
    return {"monetizationType": mon, "package": {"packageId": pid}}


def test_normalize_locale():
    assert normalize_locale("nl_NL") == "nl_NL"
    assert normalize_locale("nl") == "en_NL"
    assert normalize_locale("garbage!") == "en_US"


@respx.mock
def test_providers_parses_packages():
    route = respx.post(GQL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "packages": [
                        {
                            "packageId": 8,
                            "clearName": "Netflix",
                            "technicalName": "netflix",
                            "shortName": "nfx",
                            "monetizationTypes": ["FLATRATE"],
                        }
                    ]
                }
            },
        )
    )
    (p,) = JustWatchClient("nl_NL").providers()
    assert (p.id, p.clear_name, p.short_name, p.monetization_types) == (
        8,
        "Netflix",
        "nfx",
        ["FLATRATE"],
    )
    assert "Mozilla" in route.calls[0].request.headers["User-Agent"]


@respx.mock
def test_show_offers_keys_by_season_episode():
    node = {
        "seasons": [
            {
                "episodes": [
                    {"content": {"seasonNumber": 1, "episodeNumber": 2}, "offers": [offer(8)]},
                    {"content": {"seasonNumber": 1, "episodeNumber": 3}, "offers": []},
                ]
            }
        ]
    }
    respx.post(GQL).mock(return_value=httpx.Response(200, json={"data": {"node": node}}))
    assert JustWatchClient("en_US").show_offers("tse1") == {
        (1, 2): frozenset({(8, "FLATRATE")}),
        (1, 3): frozenset(),
    }
