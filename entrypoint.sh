#!/bin/sh
set -e

if [ "$CRON_MODE" = "true" ]; then
  # cron jobs do not inherit the container environment; the crontab sources this file.
  export -p > /etc/excludarr/env.sh
  if [ -f /config/crontab ]; then
    cp /config/crontab /var/spool/cron/crontabs/root
  else
    cp /etc/excludarr/crontab /var/spool/cron/crontabs/root
  fi
  exec crond -f -l 8
fi

exec excludarr "$@"
