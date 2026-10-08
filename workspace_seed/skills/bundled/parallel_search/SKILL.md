## Description
Search the web and fetch page excerpts using free, keyless Parallel Search MCP. Optional dependency installation is required before use.

## Setup

Install in the same Python environment that runs FastClaw (Python 3.10 or newer):

```bash
# From a Git clone:
python -m pip install -r workspace/skills/bundled/parallel_search/requirements.txt
# For a default PyPI workspace, after the first FastClaw startup:
python -m pip install -r ~/.fastclaw/workspace/skills/bundled/parallel_search/requirements.txt
```

With `FASTCLAW_WORKSPACE`, use that workspace's `skills/bundled/parallel_search/requirements.txt` instead.

## Parameters

- tool: `web_search` (default) or `web_fetch`.
- arguments: object of MCP parameters. Search requires `objective` and a nonempty `search_queries` list. Fetch requires `urls` (up to 20 HTTP/HTTPS URLs), with an optional short `objective` (at most 200 characters).
- For related calls, optionally pass the same `session_id` in arguments, using a new UUID per conversation. Leave `model_name` unset unless it comes from trusted runtime configuration.

## Examples

FastClaw's agent can dispatch these calls through its existing `run_skills` tool:

```python
run_skills("parallel_search", {
    "tool": "web_search",
    "arguments": {
        "objective": "Find Python's official asyncio documentation",
        "search_queries": ["Python asyncio official documentation"]
    }
})

run_skills("parallel_search", {
    "tool": "web_fetch",
    "arguments": {
        "urls": ["https://docs.python.org/3/library/asyncio.html"],
        "objective": "Explain asyncio tasks"
    }
})
```

The skill returns the server's text content, including source URLs and excerpts. MCP tool errors have an `Error:` prefix. FastClaw's skill timeout defaults to 60 seconds; cancellation closes the MCP session.

## Remote Endpoint

`https://search.parallel.ai/mcp` uses Streamable HTTP. No Parallel API key or OAuth setup is needed; this skill sends no authorization header and ignores saved Parallel credentials. Anonymous use has lower rate limits and server-managed fast search settings. LLM inference still requires your existing model configuration. See the [Parallel Search MCP documentation](https://docs.parallel.ai/integrations/mcp/search-mcp) for current parameters and limits.
