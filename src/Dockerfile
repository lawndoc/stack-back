FROM ghcr.io/astral-sh/uv:0.9.8 AS uv-builder

FROM restic/restic:0.18.1

RUN apk update && apk add dcron

COPY --from=uv-builder /uv /uvx /bin/

ADD . /restic-compose-backup
WORKDIR /restic-compose-backup

RUN uv python install $(cat .python-version)
RUN uv sync --locked
ENV PATH="/restic-compose-backup/.venv/bin:${PATH}"

ENV XDG_CACHE_HOME=/cache

ENTRYPOINT []
CMD ["./entrypoint.sh"]
