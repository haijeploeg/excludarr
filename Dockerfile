FROM python:3.8-alpine

ENV PS1="\[\e[0;33m\]|> excludarr <| \[\e[1;35m\]\W\[\e[0m\] \[\e[0m\]# "

WORKDIR /src
COPY . /src
RUN pip install --no-cache-dir -r requirements.txt \
    && python setup.py install
WORKDIR /
ENTRYPOINT ["excludarr"]
