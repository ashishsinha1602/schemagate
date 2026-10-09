"""Every MCP tool tells an agent what it does and what each argument means.

The tool schema is the only documentation a model sees when it picks a tool and fills in arguments. A parameter
without a description is a guess (is `principal` a name, an email, an ID?), and directories such as Glama grade
servers on exactly this. A new tool or argument that ships undescribed fails here.
"""
import asyncio

import pytest

pytest.importorskip("mcp")

from schemagate.demo_schema import demo_catalog  # noqa: E402
from schemagate.mcp_server import TOOL_DESCRIPTIONS, create_server  # noqa: E402


def _tools():
    app = create_server(catalog=demo_catalog())
    return asyncio.run(app.list_tools())


def _schema(tool):
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}


def test_every_tool_has_an_agent_facing_description():
    tools = _tools()
    assert {t.name for t in tools} == set(TOOL_DESCRIPTIONS)
    for t in tools:
        assert t.description == TOOL_DESCRIPTIONS[t.name]
        assert len(t.description) >= 120, f"{t.name}: too short to say what it does and when to use it"


def test_every_parameter_is_described():
    missing = [(t.name, p) for t in _tools() for p, spec in _schema(t).get("properties", {}).items()
               if not (spec.get("description") or "").strip()]
    assert missing == []


def test_every_tool_is_marked_read_only():
    for t in _tools():
        ann = getattr(t, "annotations", None)
        assert ann is not None, t.name
        assert getattr(ann, "read_only_hint", getattr(ann, "readOnlyHint", None)) is True, t.name
        assert getattr(ann, "destructive_hint", getattr(ann, "destructiveHint", None)) is False, t.name


def test_limits_are_in_the_schema():
    by_name = {t.name: _schema(t)["properties"] for t in _tools()}
    assert by_name["run_query"]["max_rows"].get("maximum") == 200
    assert by_name["select_schema"]["top_k"].get("minimum") == 1
