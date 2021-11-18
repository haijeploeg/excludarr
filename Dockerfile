FROM python:3.8-alpine

ENV PS1="\[\e[0;33m\]|> excludarr <| \[\e[1;35m\]\W\[\e[0m\] \[\e[0m\]# "

WORKDIR /src
COPY . /src
# hadolint ignore=DL3018
RUN apk add --no-cache bash \
    && pip install --no-cache-dir -r requirements.txt \
    && python setup.py install \
    && mkdir /etc/excludarr

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /
ENTRYPOINT ["/entrypoint.sh"]
