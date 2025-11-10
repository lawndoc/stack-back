FROM restic/restic:0.17.3

RUN apk update && apk add \
    python3 \
    dcron

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ADD . /restic-compose-backup
WORKDIR /restic-compose-backup

# RUN uv python install $(cat .python-version)  # does not build for aarch64 -- see https://github.com/astral-sh/uv/issues/6890
RUN uv sync --locked
ENV PATH="/restic-compose-backup/.venv/bin:${PATH}"

ENV XDG_CACHE_HOME=/cache

ENTRYPOINT []
CMD ["./entrypoint.sh"]
