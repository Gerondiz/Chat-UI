from __future__ import annotations

import asyncio
import os
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

from datetime import datetime
from db_manager import ChromaManager
from web_search import search_images, search_web

server = Server("chromadb-mcp-server")
db = ChromaManager()


@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    collections = db.list_collections()
    return [
        types.Resource(
            uri=f"chromadb://collections/{c['name']}",
            name=f"Collection: {c['name']}",
            description=f"ChromaDB collection '{c['name']}' with {c['count']} files",
            mimeType="text/plain",
        )
        for c in collections
    ]


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_chromadb",
            description=(
                "Search for relevant documents, context, or information "
                "in a ChromaDB collection using semantic search."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "collection_name": {
                        "type": "string",
                        "description": "Name of the ChromaDB collection to search in",
                    },
                    "query": {
                        "type": "string",
                        "description": "Semantic search query (what the user is looking for)",
                    },
                    "n_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["collection_name", "query"],
            },
        ),
        types.Tool(
            name="list_collections",
            description=(
                "List all available ChromaDB collections with their document counts."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="search_web",
            description=(
                "Search the internet for current information. "
                "Use this when you need up-to-date knowledge or facts outside the local database."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="get_current_time",
            description=(
                "Get the current date and time. "
                "Use this when you need to know today's date, current time, "
                "day of the week, or any time-related information."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        types.Tool(
            name="search_images",
            description=(
                "Search the internet for images. "
                "The result already contains the markdown image syntax (e.g. ![title](url)) "
                "that you MUST copy-paste directly into your response. "
                "YOUR RESPONSE MUST INCLUDE these markdown image lines — "
                "do not describe the images, show them. "
                "DO NOT list URLs as text or suggest the user search elsewhere."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for images",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of image results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    if name == "search_chromadb":
        if not arguments:
            raise ValueError("Missing arguments")
        collection_name = arguments.get("collection_name")
        query = arguments.get("query")
        n_results = arguments.get("n_results", 5)
        if not collection_name or not query:
            raise ValueError("collection_name and query are required")

        try:
            results = db.search_collection(collection_name, query, n_results)
        except ValueError as e:
            return [types.TextContent(type="text", text=str(e))]

        if not results:
            return [
                types.TextContent(
                    type="text",
                    text=f"No relevant documents found in collection '{collection_name}'.",
                )
            ]

        lines = [f"Search results from collection '{collection_name}':"]
        for r in results:
            content_preview = r["content"][:500]
            if len(r["content"]) > 500:
                content_preview += "..."
            lines.append(f"\n--- {r['filename']} (chunk {r['chunk']}) ---")
            lines.append(content_preview)

        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "list_collections":
        collections = db.list_collections()
        if not collections:
            return [
                types.TextContent(
                    type="text", text="No collections found in ChromaDB."
                )
            ]
        lines = ["Available collections:"]
        for c in collections:
            lines.append(f"- {c['name']} ({c['count']} files)")
        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "search_web":
        if not arguments or not arguments.get("query"):
            raise ValueError("query is required")
        query = arguments["query"]
        max_results = arguments.get("max_results", 5)
        results = await search_web(query, max_results)
        if not results:
            return [types.TextContent(type="text", text=f"No search results found for '{query}'.")]
        lines = [f"Web search results for '{query}':"]
        for i, r in enumerate(results, 1):
            lines.append(f"\n{i}. {r['title']}")
            lines.append(f"   URL: {r['url']}")
            lines.append(f"   Snippet: {r['snippet']}")
            if r.get("content"):
                lines.append(f"   Content:\n{r['content']}")
        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "search_images":
        if not arguments or not arguments.get("query"):
            raise ValueError("query is required")
        query = arguments["query"]
        max_results = arguments.get("max_results", 5)
        results = await search_images(query, max_results)
        if not results:
            return [types.TextContent(type="text", text=f"No images found for '{query}'.")]
        lines = [f"I searched for '{query}' and found these images. YOU MUST DISPLAY THEM using the markdown below:"]
        for i, r in enumerate(results, 1):
            lines.append("")
            lines.append(f"![{r['title']}]({r['image_url']})")
            lines.append(f"[Source: {r['source_url']}]")
        lines.append("")
        lines.append("IMPORTANT: Copy-paste the markdown image lines above into your response to show the user the images.")
        return [types.TextContent(type="text", text="\n".join(lines))]

    elif name == "get_current_time":
        now = datetime.now()
        return [types.TextContent(
            type="text",
            text=(
                f"Current date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Day of week: {now.strftime('%A')}\n"
                f"Timezone: UTC{now.strftime('%z') or '+0000'}"
            ),
        )]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="chromadb-mcp-server",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
