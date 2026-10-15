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
# python:3.12-slim, pinned by digest so the base cannot change under a rebuild
FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9 AS build

WORKDIR /w
COPY pyproject.toml README.md ./
COPY docker/requirements.txt ./requirements.txt
COPY src ./src

# Every driver, MCP, and the model SDKs -- but NOT [huggingface]: torch is two
# gigabytes and a local model is a choice, not a default. Someone who wants it
# installs it into a derived image.
# Every dependency by hash (docker/requirements.txt, from scripts/lock_ci.py), then
# schemagate itself, built here as a wheel and installed with --no-deps, so
# nothing unreviewed is fetched. The prefix is set through PIP_PREFIX rather
# than --prefix=/install, which Scorecard's pin check reads as a package name.
RUN export PIP_PREFIX=/install \
 && pip install --no-cache-dir --require-hashes -r requirements.txt \
 && pip wheel --no-cache-dir --no-deps -w /wheels . \
 && pip install --no-cache-dir --no-deps /wheels/*.whl


FROM python:3.12-slim@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

# curl for HEALTHCHECK; libaio1 is what oracledb thick mode looks for if
# anyone switches to it. Thin mode, the default, needs neither.
#
# SQL Server: pyodbc needs unixODBC (libodbc.so.2) to import at all, and
# Microsoft's ODBC Driver 18 to connect -- without both, every mssql+pyodbc
# URL failed in this image while the other three drivers worked. Same steps as
# the CI jobs, from Microsoft's Debian repository for this base (trixie),
# which is signed with the 2025 key; its fingerprint is checked, not trusted.
# The architecture is the build's own: the image is published for amd64 and
# arm64, and a hard-coded amd64 made the arm64 build fail at release.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gnupg ca-certificates unixodbc \
 && curl -fsSL https://packages.microsoft.com/keys/microsoft-2025.asc -o /tmp/ms.asc \
 && gpg --batch --show-keys --with-colons /tmp/ms.asc | grep -q "^fpr:::::::::AA86F75E427A19DD33346403EE4D7792F748182B:" \
 && gpg --batch --yes --dearmor -o /usr/share/keyrings/microsoft-prod.gpg /tmp/ms.asc && rm /tmp/ms.asc \
 && . /etc/os-release \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/${VERSION_ID}/prod ${VERSION_CODENAME} main" \
      > /etc/apt/sources.list.d/mssql-release.list \
 && apt-get update \
 && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
 && apt-get purge -y gnupg && apt-get autoremove -y \
 && odbcinst -q -d | grep -qi "ODBC Driver 18 for SQL Server" \
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
