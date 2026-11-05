# Local JustWatch GraphQL fix image

The published `excludarr/excludarr:latest` (v1.1.x) image fails with `JustWatchForbidden` (403)
because JustWatch removed the legacy REST endpoints (`/content/locales/state`, `/content/providers/locale/...`).

Rebuild the patched image (base pinned to the last published image digest):

    docker build -f Dockerfile.jwfix -t excludarr:local-jwfix .
