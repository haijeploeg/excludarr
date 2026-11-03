SEARCH_QUERY = """#graphql
query GetSearchTitles(
    $searchTitlesFilter: TitleFilter!
    $country: Country!
    $language: Language!
    $first: Int!
) {
    popularTitles(
        country: $country
        filter: $searchTitlesFilter
        first: $first
    ) {
        edges {
            node {
                ... on MovieOrShow {
                    id
                    objectId
                    objectType
                    content(country: $country, language: $language) {
                        title
                        originalReleaseYear
                        originalReleaseDate
                        externalIds {
                            imdbId
                            tmdbId
                            __typename
                        }
                        __typename
                    }
                    __typename
                }
            }
            __typename
        }
        __typename
    }
}
"""


OFFER_QUERY = """#graphql
query GetTitleOffers(
    $nodeId: ID!
    $country: Country!
    $offerFilter: OfferFilter!
    $language: Language!
) {
    node(id: $nodeId) {
        ...TitleDetails
        __typename
    }
    __typename
}

fragment TitleDetails on Node {
    id
    __typename
    ... on Movie {
        offers(country: $country, platform: WEB, filter: $offerFilter) {
            ...Offer
            __typename
        }
        __typename
    }
    ... on Show {
        seasons(sortDirection: ASC) {
            ...Season
            __typename
        }
        __typename
    }
}

fragment Season on Season {
    id
    objectId
    objectType
    totalEpisodeCount
    content(country: $country, language: $language) {
        seasonNumber
        title
    }
    episodes {
        ...Episode
        __typename
    }
}

fragment Episode on Episode {
    id
    objectId
    content(country: $country, language: $language) {
    episodeNumber
    seasonNumber
    }
    offers(country: $country, platform: WEB, filter: $offerFilter) {
        ...Offer
        __typename
    }
}

fragment Offer on Offer {
    monetizationType
    presentationType
    elementCount
    subtitleLanguages
    audioLanguages
    package {
        id
        packageId
        clearName
        shortName
        technicalName

        __typename
    }
}
"""
