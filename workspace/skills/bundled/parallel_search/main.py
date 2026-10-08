# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""Anonymous Parallel Search MCP via FastClaw's skill dispatcher."""

import json

ENDPOINT = "https://search.parallel.ai/mcp"
USER_AGENT = "FastClaw/parallel-search (+https://github.com/kandada/fastclaw)"


async def execute(tool="web_search", arguments=None):
    """Call web_search or web_fetch using the server's MCP argument schema."""
    if tool not in ("web_search", "web_fetch"):
        return "Error: tool must be web_search or web_fetch"
    if not isinstance(arguments, dict):
        return "Error: arguments must be an object containing the MCP tool parameters"

    try:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
    except ImportError:
        return "Error: Install parallel_search/requirements.txt in FastClaw's Python environment first"

    # A fresh anonymous client never reads Parallel keys or saved OAuth credentials.
    # FastClaw's execute_skill enforces the overall timeout and cancellation.
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30.0,
    ) as client:
        async with streamable_http_client(ENDPOINT, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)

    text = "\n".join(block.text for block in result.content if block.type == "text")
    if not text:
        text = json.dumps(result.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
    return ("Error: " if result.isError else "") + text
