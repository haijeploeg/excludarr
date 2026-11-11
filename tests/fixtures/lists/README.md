# Source response contracts

Sanitized synthetic fixtures are inline in `tests/clients/test_list_sources.py`
and `test_tmdb.py`, next to their assertions. No account credentials or real user
watchlists are included.

Primary references checked on 2026-11-11:

- Trakt: https://developer.trakt.tv/
- Trakt chart paths: https://github.com/Radarr/Radarr/blob/develop/src/NzbDrone.Core/ImportLists/Trakt/Popular/TraktPopularRequestGenerator.cs
- Plex discovery Watchlist and GUID fields: https://github.com/Radarr/Radarr/blob/develop/src/NzbDrone.Core/Notifications/Plex/PlexTv/PlexTvService.cs
- Plex response parsing: https://github.com/Radarr/Radarr/blob/develop/src/NzbDrone.Core/ImportLists/Plex/PlexParser.cs
- TMDB mixed lists: https://developer.themoviedb.org/v4/reference/list-details
- TMDB Trending: https://developer.themoviedb.org/reference/trending-all
- TMDB ID resolution: https://developer.themoviedb.org/reference/find-by-id
- StevenLu response: https://github.com/Radarr/Radarr/blob/develop/src/NzbDrone.Core/ImportLists/StevenLu/StevenLuParser.cs

These fixtures verify our adapters against the documented/source shapes; they do
not establish that a user's private token or live account currently works.
