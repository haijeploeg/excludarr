from typing import Dict, List


class SearchResult:
    id: str
    objectType: str
    title: str
    year: int
    imdbId: str | None
    tmdbId: int | None

    def __init__(self, json):
        self.__from_json(json)

    def __from_json(self, node):
        self.id = node["id"]
        self.ty = node["objectType"]
        self.title = node["content"]["title"]
        self.year = node["content"]["originalReleaseYear"]
        self.imdbId = node["content"]["externalIds"]["imdbId"]
        tmdbId = node["content"]["externalIds"]["tmdbId"]
        self.tmdbId = int(tmdbId) if tmdbId is not None else None


class Offer:
    id: str
    monetizationType: str
    presentationType: str
    providerClearName: str
    providertechnicalName: str
    providerShortName: str
    subtitleLanguages: List[str]
    audioLanguages: List[str]

    def __init__(self, json):
        self.__from_json(json)

    def __from_json(self, node):
        assert node["__typename"] == "Offer"

        self.monetizationType = node["monetizationType"]
        self.presentationType = node["presentationType"]
        self.subtitleLanguages = node["subtitleLanguages"]
        self.audioLanguages = node["audioLanguages"]

        self.id = node["package"]["packageId"]
        self.providerClearName = node["package"]["clearName"]
        self.providertechnicalName = node["package"]["technicalName"]
        self.providerShortName = node["package"]["shortName"]


# flat offers list
MovieOffers = List[Offer]

# season -> episode -> offers list
ShowOffers = Dict[int, Dict[int, List[Offer]]]
