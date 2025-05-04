FROM restic/restic:0.17.3

RUN apk update && apk add \
    dcron \
    mariadb-client \
    mariadb-connector-c-dev

RUN apk add postgresql-client --repository=http://dl-cdn.alpinelinux.org/alpine/edge/main

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ADD . /restic-compose-backup
WORKDIR /restic-compose-backup

RUN uv python install $(cat .python-version)
RUN uv sync --locked
ENV PATH="/restic-compose-backup/.venv/bin:${PATH}"

ENV XDG_CACHE_HOME=/cache

ENTRYPOINT []
CMD ["./entrypoint.sh"]
