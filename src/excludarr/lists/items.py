"""External list metadata, without invented library state."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ListItem:
    title: str
    kind: Literal["movie", "series"]
    year: int | None = None
    tmdb_id: int | None = None
    imdb_id: str | None = None
    tvdb_id: int | None = None
    genres: frozenset[str] | None = None
    ratings: dict[str, float] | None = None
    ended: bool | None = None

    @property
    def base_title(self) -> str:
        return self.title

    @property
    def key(self) -> str:
        return f"list:{self.kind}:{self.tmdb_id}:{self.imdb_id}:{self.tvdb_id}"
