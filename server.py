"""
Generic stdio-to-HTTP MCP bridge.
Wraps any stdio MCP server as a Streamable HTTP server.

Configuration via environment variables:
  STDIO_CMD  - command to run the stdio MCP server (default: "python mcp_server.py")
  STDIO_CWD  - working directory for the stdio server (optional)
  PORT       - HTTP port to listen on (default: 8080)
"""
import json
import logging
import os
import shlex

import uvicorn
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STDIO_CMD = os.environ.get("STDIO_CMD", "python mcp_server.py")
STDIO_CWD = os.environ.get("STDIO_CWD") or None


def get_stdio_params() -> StdioServerParameters:
    parts = shlex.split(STDIO_CMD)
    return StdioServerParameters(
        command=parts[0],
        args=parts[1:] if len(parts) > 1 else [],
        cwd=STDIO_CWD,
    )


server = Server("mcp-bridge")


@server.list_tools()
async def handle_list_tools():
    params = get_stdio_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    params = get_stdio_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return result.content


session_manager = StreamableHTTPSessionManager(
    app=server,
    event_store=None,
    json_response=False,
    stateless=True,
)


async def send_json(send, status: int, body: dict):
    body_bytes = json.dumps(body).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            [b"content-type", b"application/json"],
            [b"content-length", str(len(body_bytes)).encode()],
        ],
    })
    await send({"type": "http.response.body", "body": body_bytes})


async def app(scope, receive, send):
    if scope["type"] == "lifespan":
        await handle_lifespan(scope, receive, send)
        return

    path = scope.get("path", "")

    if path == "/mcp":
        # Ensure Accept header is present (required by MCP Streamable HTTP spec)
        headers = list(scope.get("headers", []))
        if b"accept" not in [k.lower() for k, v in headers]:
            headers.append((b"accept", b"application/json, text/event-stream"))
            scope["headers"] = headers
        await session_manager.handle_request(scope, receive, send)
        return

    # OAuth discovery endpoints (return empty 200 to skip auth flow)
    if path in (
        "/.well-known/oauth-protected-resource",
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-authorization-server",
    ):
        await send_json(send, 200, {})
        return

    # OAuth client registration (dummy response)
    if path == "/register":
        await send_json(send, 200, {"client_id": "dummy"})
        return

    await send_json(send, 404, {"detail": "Not Found"})


async def handle_lifespan(scope, receive, send):
    async with session_manager.run():
        logger.info(f"MCP bridge starting... STDIO_CMD={STDIO_CMD} STDIO_CWD={STDIO_CWD}")
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        message = await receive()
        if message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("server:app", host="0.0.0.0", port=port)
