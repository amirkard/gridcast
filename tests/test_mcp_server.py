"""MCP server tests. Same database fixture as the tool tests."""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from gridcast.mcp_server import server
from gridcast.tools import TOOLS

KNOWN_RANGE = {"start": "2025-03-01", "end": "2025-03-04"}


def _in_memory(fn):
    """Run fn(session) against the server through an in-memory MCP connection."""

    async def go():
        async with create_connected_server_and_client_session(server) as session:
            return await fn(session)

    return asyncio.run(go())


def test_lists_the_same_tools_as_the_agent():
    """One tool contract: MCP clients and the agent must see identical schemas."""
    listed = _in_memory(lambda s: s.list_tools()).tools
    assert {t.name for t in listed} == {t["name"] for t in TOOLS}
    by_name = {t["name"]: t for t in TOOLS}
    for tool in listed:
        assert tool.description == by_name[tool.name]["description"]
        assert tool.inputSchema == by_name[tool.name]["input_schema"]


def test_call_returns_json_rows():
    args = {**KNOWN_RANGE, "aggregate": "summary"}
    result = _in_memory(lambda s: s.call_tool("query_load_history", args))
    assert not result.isError
    rows = json.loads(result.content[0].text)["rows"]
    assert rows[0]["intervals"] == 288


def test_tool_error_is_flagged_not_returned_as_data():
    """An empty range must reach the client as isError, not as a normal result."""
    args = {"start": "2030-01-01", "end": "2030-01-02", "aggregate": "summary"}
    result = _in_memory(lambda s: s.call_tool("query_load_history", args))
    assert result.isError
    assert "no measured data" in result.content[0].text


def test_invalid_arguments_are_rejected():
    """aggregate is an enum; anything else must fail before it reaches SQL."""
    args = {**KNOWN_RANGE, "aggregate": "weekly"}
    result = _in_memory(lambda s: s.call_tool("query_load_history", args))
    assert result.isError


def test_stdio_transport_end_to_end():
    """Start the server as a separate process, as a desktop client would."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "gridcast.mcp_server"],
        env=dict(os.environ),
    )

    async def go():
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            info = await session.call_tool("get_model_info", {})
            return tools, info

    tools, info = asyncio.run(go())
    assert len(tools.tools) == len(TOOLS)
    assert not info.isError
    assert "evaluation" in json.loads(info.content[0].text)
