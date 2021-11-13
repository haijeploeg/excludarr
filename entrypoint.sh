#!/bin/bash

general_country="${GENERAL_COUNTRY:-NL}"
general_providers="[${GENERAL_PROVIDERS:-'netflix'}]"
tmdb_api_key="${TMDB_API_KEY:-secret}"
radarr_url="${RADARR_URL:-http://localhost:7878}"
radarr_api_key="${RADARR_API_KEY:-secret}"
radarr_verify_ssl="${RADARR_VERIFY_SSL:-false}"
sonarr_url="${SONARR_URL:-http://localhost:8989}"
sonarr_api_key="${SONARR_API_KEY:-secret}"
sonarr_verify_ssl="${SONARR_VERIFY_SSL:-false}"

cat << EOF > /etc/excludarr/excludarr.yml
general:
  country: $general_country
  providers: $general_providers

tmdb:
  api_key: '$tmdb_api_key'

radarr:
  url: '$radarr_url'
  api_key: '$radarr_api_key'
  verify_ssl: $radarr_verify_ssl

sonarr:
  url: '$sonarr_url'
  api_key: '$sonarr_api_key'
  verify_ssl: $sonarr_verify_ssl
EOF

excludarr $@
