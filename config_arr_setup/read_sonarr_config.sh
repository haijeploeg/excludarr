#!/bin/bash

SONARR_CONFIG_FILE="/sonarr_config/config.xml"
CONFIG_FILE="/config/config.yml"
# SONARR_CONFIG_FILE="./.docker/sonarr_config/config.xml"
# CONFIG_FILE="./.docker/config/config.yml"
SONARR_DOMAIN=$1

if [ ! -f $SONARR_CONFIG_FILE ]; then
    echo "Sonarr config file not found"
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
        URL="http://$SONARR_DOMAIN:$CONTENT"
        URL=$URL yq -i '.sonarr.url = strenv(URL)' $CONFIG_FILE
    fi

    if [[ $ENTITY = "ApiKey" ]]; then
        APIKEY=$CONTENT yq -i '.sonarr.api_key =  strenv(APIKEY)' $CONFIG_FILE
    fi
done < $SONARR_CONFIG_FILE
