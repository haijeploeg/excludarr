#!/bin/bash

general_fast_search="${GENERAL_FAST_SEARCH:-true}"
general_locale="${GENERAL_LOCALE:-en_US}"
general_providers="[${GENERAL_PROVIDERS:-'netflix'}]"
tmdb_api_key="${TMDB_API_KEY}"
radarr_url="${RADARR_URL:-http://localhost:7878}"
radarr_api_key="${RADARR_API_KEY:-secret}"
radarr_verify_ssl="${RADARR_VERIFY_SSL:-false}"
radarr_exclude="[${RADARR_EXCLUDE:-''}]"
sonarr_url="${SONARR_URL:-http://localhost:8989}"
sonarr_api_key="${SONARR_API_KEY:-secret}"
sonarr_verify_ssl="${SONARR_VERIFY_SSL:-false}"
sonarr_exclude="[${SONARR_EXCLUDE:-''}]"
cron_mode="${CRON_MODE:-false}"


cat << EOF > /etc/excludarr/excludarr.yml
general:
  fast_search: $general_fast_search
  locale: $general_locale
  providers: $general_providers

radarr:
  url: '$radarr_url'
  api_key: '$radarr_api_key'
  verify_ssl: $radarr_verify_ssl
  exclude: $radarr_exclude

sonarr:
  url: '$sonarr_url'
  api_key: '$sonarr_api_key'
  verify_ssl: $sonarr_verify_ssl
  exclude: $sonarr_exclude

EOF

if [[ ! -z $TMDB_API_KEY ]]; then
    cat << EOF >> /etc/excludarr/excludarr.yml
tmdb:
  api_key: '$tmdb_api_key'
EOF
fi

if [ "$cron_mode" = true ]; then
    if test -f "/etc/excludarr/crontab"; then
        cp /etc/excludarr/crontab /var/spool/cron/crontabs/root
        crond -l 8 -f
    else
        echo "No crontab file mounted! Please mount a valid crontab file at /etc/excludarr/crontab before running in cron mode!"
        exit 1
    fi
else
    excludarr $@
fi
