"""The version a client is told in `initialize` is schemagate's, not the SDK's.

It was the SDK's: FastMCP's low-level server is built with version=None and
the SDK then falls back to *its own* package version, or to an empty string
in an image where that metadata does not resolve. Every client, and every
directory that lists servers, showed one or the other.
"""
import os
import sys

import pytest

from schemagate import __version__, mcp_server


def test_in_process_server_reports_the_package_version():
    pytest.importorskip("mcp")
    app = mcp_server.create_server()
    low = getattr(app, "_mcp_server", None)
    reported = (low.create_initialization_options().server_version if low is not None
                else getattr(app, "version", None))
    assert reported == __version__, reported


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_a_real_client_sees_the_package_version_over_stdio():
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {k: v for k, v in os.environ.items() if k != "SCHEMAGATE_CATALOG_CONFIG"}
    env["SCHEMAGATE_DATABASE_URL"] = "demo"
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "schemagate.mcp_server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            # 1.x spells it serverInfo, 2.x server_info; the server is the same.
            info = getattr(init, "server_info", None) or getattr(init, "serverInfo", None)
            assert info is not None, init
            assert info.name == "schemagate"
            assert info.version == __version__, info
