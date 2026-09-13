# schemagate studio, in one command.
#
#   docker run -p 8770:8770 -e SCHEMAGATE_DATABASE_URL=postgresql://... schemagate
#
# The point of this image is that installing schemagate is the part people get
# stuck on: which extra do I need for my database, does my Python have a
# compiler for psycopg, is oracledb going to want an Instant Client. All four
# drivers are baked in here, so the answer is none of it.
#
# Two stages so the runtime image does not carry pip's build machinery or the
# wheels it downloaded.
FROM python:3.12-slim AS build

WORKDIR /w
COPY pyproject.toml README.md ./
COPY src ./src

# Every driver, MCP, and the model SDKs -- but NOT [huggingface]: torch is two
# gigabytes and a local model is a choice, not a default. Someone who wants it
# installs it into a derived image.
RUN pip install --no-cache-dir --prefix=/install ".[databases,ai,mcp]"


FROM python:3.12-slim

# curl for HEALTHCHECK; libaio1 is what oracledb thick mode looks for if
# anyone switches to it. Thin mode, the default, needs neither.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /install /usr/local

# Not root. The Studio binds a port and runs SQL a model wrote; there is no
# reason for it to be able to write to the image. /app rather than a user
# home, because the repo's own check rejects that shape of path outright.
RUN useradd --no-create-home --uid 10001 schemagate && mkdir -p /app && chown schemagate:schemagate /app
USER schemagate
WORKDIR /app

# 0.0.0.0 inside the container, because a container's 127.0.0.1 is reachable
# by nothing. Publish it to a host port you control -- `-p 127.0.0.1:8770:8770`
# if you do not want it on your network. The Studio has no login.
ENV SCHEMAGATE_STUDIO_HOST=0.0.0.0 \
    SCHEMAGATE_STUDIO_PORT=8770 \
    PYTHONUNBUFFERED=1

EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${SCHEMAGATE_STUDIO_PORT}/api/health" || exit 1

# --demo when no database is given, so `docker run -p 8770:8770 schemagate`
# shows something instead of an empty page. entrypoint.sh does that choosing.
# --chmod because the mode in the index is what the builder copies, and a
# Windows checkout cannot record one: git stores this script 100644 there,
# Docker Desktop hands a Windows build context 0777 and hides it, and the
# Linux runner that builds the published image does not. The image shipped
# in 0.1.51 could not start at all -- `exec: permission denied` -- and the
# local build it was tested with was fine. Setting the mode here means the
# builder's opinion of the checkout stops mattering.
COPY --chown=schemagate:schemagate --chmod=0755 docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
