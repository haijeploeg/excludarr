FROM alpine:latest

VOLUME [ "/radarr_config" ]
VOLUME [ "/sonarr_config" ]
VOLUME [ "/config" ]

RUN apk add --no-cache yq bash

WORKDIR /

COPY ./read_radarr_config.sh /radarr.sh
RUN chmod +x /radarr.sh

COPY ./read_sonarr_config.sh /sonarr.sh
RUN chmod +x /sonarr.sh

COPY ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT [ "/entrypoint.sh" ]
