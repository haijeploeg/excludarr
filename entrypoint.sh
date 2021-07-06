#!/bin/bash

general_country="${GENERAL_COUNTRY:-NL}"
general_providers="${GENERAL_PROVIDERS:-netflix}"
tmdb_api_key="${TMDB_API_KEY:-secret}"
radarr_url="${RADARR_URL:-http://localhost:7878}"
radarr_api_key="${RADARR_API_KEY:-secret}"
radarr_verify_ssl="${RADARR_VERIFY_SSL:-false}"

cat << EOF > /etc/excludarr/excludarr.yml
general:
  country: $general_country
  providers:
    - netflix

tmdb:
  api_key: '$tmdb_api_key'

radarr:
  url: '$radarr_url'
  api_key: '$radarr_api_key'
  verify_ssl: $radarr_verify_ssl
EOF

excludarr $@
