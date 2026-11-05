FROM python:3.12-alpine

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /build

ENV EXCLUDARR_CONFIG=/config/excludarr.yml
VOLUME /config

# Fallback crontab location for cron mode
RUN mkdir -p /etc/excludarr
COPY .examples/crontab /etc/excludarr/crontab

WORKDIR /
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
