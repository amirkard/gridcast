"""Gridcast tools as an MCP server.

The server reuses the same tool contract as the in-house agent: the schemas come
from gridcast.tools.TOOLS and the calls go to gridcast.tools.DISPATCH. There is
one definition of each tool, so the agent, the evaluation suite and any MCP
client see the same names, descriptions and argument schemas.

Run over stdio (the transport desktop clients use):

    uv run python -m gridcast.mcp_server

stdout carries the MCP protocol, so nothing in this process may print to it.
"""

import asyncio
import json

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from gridcast.tools import DISPATCH, TOOLS

MAX_RESULT_CHARS = 20_000  # same cap as the agent loop

server = Server("gridcast")


class ToolError(Exception):
    """A tool returned an error result. The SDK reports it with isError=True."""


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["input_schema"],
        )
        for t in TOOLS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    if name not in DISPATCH:
        raise ToolError(f"unknown tool: {name}")

    # The tools use a synchronous database driver; keep it off the event loop.
    out = await asyncio.to_thread(DISPATCH[name], **(arguments or {}))

    if isinstance(out, dict) and "error" in out:
        raise ToolError(out["error"])

    return [types.TextContent(type="text", text=json.dumps(out)[:MAX_RESULT_CHARS])]


async def serve() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
