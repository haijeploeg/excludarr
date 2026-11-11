"""Tautulli client (watch history)."""

from dataclasses import dataclass
from datetime import UTC, datetime

from excludarr.clients.http import HttpClient, IntegrationError
from excludarr.config import Integration

PAGE = 1000


@dataclass
class HistoryRow:
    at: datetime
    user: str
    friendly_name: str
    rating_key: str
    grandparent_rating_key: str | None
    season: int | None
    episode: int | None
    watched: bool


def _int(v) -> int | None:
    return None if v in ("", None) else int(v)


class TautulliClient:
    def __init__(self, cfg: Integration, http: HttpClient | None = None):
        self.api_key = cfg.api_key
        self.http = http or HttpClient("tautulli", cfg.url, {}, verify=cfg.verify_ssl)

    def history(self) -> list[HistoryRow]:
        rows: list[HistoryRow] = []
        total = None
        while total is None or len(rows) < total:
            resp = self.http.get(
                "/api/v2",
                params={
                    "apikey": self.api_key,
                    "cmd": "get_history",
                    "length": PAGE,
                    "start": len(rows),
                },
            )["response"]
            if resp.get("result") != "success":
                if resp.get("message") == "Invalid apikey":
                    raise IntegrationError("tautulli", "Invalid apikey")
                raise IntegrationError("tautulli", "API returned a failure")
            data = resp["data"]
            total = data["recordsFiltered"]
            page = data["data"]
            if not page:
                break
            for r in page:
                rows.append(
                    HistoryRow(
                        at=datetime.fromtimestamp(int(r["date"]), UTC),
                        user=r["user"] or "",
                        friendly_name=r["friendly_name"] or "",
                        rating_key=str(r["rating_key"]),
                        grandparent_rating_key=str(r["grandparent_rating_key"])
                        if r.get("grandparent_rating_key") not in ("", None)
                        else None,
                        season=_int(r.get("parent_media_index")),
                        episode=_int(r.get("media_index")),
                        watched=float(r.get("watched_status") or 0) >= 1,
                    )
                )
        return rows
