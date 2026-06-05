from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER_CMD = os.getenv(
    "MCP_SERVER_CMD",
    "python3 chromadb_mcp/server.py",
)


class McpHost:
    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._read: Any = None
        self._write: Any = None
        self._cleanup: asyncio.Task[None] | None = None
        self._tools: list[Tool] = []
        self._ready = asyncio.Event()

    async def start(self) -> None:
        cmd_parts = MCP_SERVER_CMD.split()
        params = StdioServerParameters(
            command=cmd_parts[0],
            args=cmd_parts[1:],
            env={**os.environ},
            cwd=str(REPO_ROOT),
        )

        async with stdio_client(params) as (read, write):
            self._read = read
            self._write = write
            async with ClientSession(read, write) as session:
                self._session = session
                await session.initialize()
                result = await session.list_tools()
                self._tools = result.tools
                self._ready.set()
                logger.info(
                    "MCP server ready, %d tools loaded: %s",
                    len(self._tools),
                    [t.name for t in self._tools],
                )
                # keep session alive forever
                await asyncio.Event().wait()

    async def wait_ready(self, timeout: float = 15) -> bool:
        try:
            await asyncio.wait_for(self._ready.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @property
    def tools(self) -> list[Tool]:
        return self._tools

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> list[TextContent]:
        if not self._session:
            raise RuntimeError("MCP host not started")
        result = await self._session.call_tool(name, arguments or {})
        return [c for c in result.content if isinstance(c, TextContent)]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                },
            }
            for t in self._tools
        ]


mcp_host = McpHost()


@asynccontextmanager
async def run_mcp_host():
    task = asyncio.create_task(mcp_host.start())
    ready = await mcp_host.wait_ready()
    if not ready:
        logger.warning("MCP host did not become ready in time")
    try:
        yield mcp_host
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
