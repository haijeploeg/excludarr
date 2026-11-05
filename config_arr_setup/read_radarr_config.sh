#!/bin/bash

RADARR_CONFIG_FILE="/radarr_config/config.xml"
CONFIG_FILE="/config/config.yml"
# RADARR_CONFIG_FILE="./.docker/radarr_config/config.xml"
# CONFIG_FILE="./.docker/config/config.yml"
RADARR_DOMAIN=$1

if [ ! -f $RADARR_CONFIG_FILE ]; then
    echo "Radarr config file not found"
    exit 1
fi

if [ ! -f $CONFIG_FILE ]; then
    echo "arr_setup config file not found"
    exit 1
fi

read_dom () {
    local IFS=\>
    read -d \< ENTITY CONTENT
}


while read_dom; do
    if [[ $ENTITY = "Port" ]]; then
        URL="http://$RADARR_DOMAIN:$CONTENT"
        URL=$URL yq -i '.radarr.url = strenv(URL)' $CONFIG_FILE
    fi

    if [[ $ENTITY = "ApiKey" ]]; then
        APIKEY=$CONTENT yq -i '.radarr.api_key = strenv(APIKEY)' $CONFIG_FILE
    fi
done < $RADARR_CONFIG_FILE
