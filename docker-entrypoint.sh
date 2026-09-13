#!/bin/sh
# Pick a sensible command so `docker run schemagate` does something useful.
#
#   docker run -p 8770:8770 schemagate                      -> the demo schema
#   docker run -p 8770:8770 -e SCHEMAGATE_DATABASE_URL=...   -> your database
#   docker run schemagate mcp                                -> the MCP server
#   docker run schemagate schemagate select "..." --url ...  -> anything else
#
# Anything that is not one of the two shorthands is executed as given, so the
# image stays a way to run the CLI rather than a wrapper you have to fight.
set -eu

HOST="${SCHEMAGATE_STUDIO_HOST:-0.0.0.0}"
PORT="${SCHEMAGATE_STUDIO_PORT:-8770}"

if [ "$#" -eq 0 ] || [ "$1" = "studio" ]; then
    [ "$#" -gt 0 ] && shift
    if [ -n "${SCHEMAGATE_DATABASE_URL:-}" ]; then
        exec schemagate studio --host "$HOST" --port "$PORT" \
             --url "$SCHEMAGATE_DATABASE_URL" "$@"
    fi
    echo "no SCHEMAGATE_DATABASE_URL set -- starting on the bundled demo schema." >&2
    echo "Pass -e SCHEMAGATE_DATABASE_URL='postgresql://…' to use your own." >&2
    exec schemagate studio --host "$HOST" --port "$PORT" --demo "$@"
fi

if [ "$1" = "mcp" ]; then
    shift
    # streamable-http rather than stdio: stdio has no meaning across a
    # container boundary, so a container that ran it would look hung.
    export SCHEMAGATE_MCP_TRANSPORT="${SCHEMAGATE_MCP_TRANSPORT:-streamable-http}"
    export SCHEMAGATE_MCP_HOST="${SCHEMAGATE_MCP_HOST:-0.0.0.0}"
    export SCHEMAGATE_MCP_PORT="${SCHEMAGATE_MCP_PORT:-8765}"
    exec python -m schemagate.mcp_server "$@"
fi

exec "$@"
