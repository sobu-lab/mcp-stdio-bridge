# mcp-stdio-bridge

A generic bridge that exposes any **stdio MCP server** as a **Streamable HTTP MCP server**.

No modifications to the original MCP server are required. Configure the stdio command via environment variables and deploy anywhere that accepts HTTP (e.g. Google Cloud Run).

```
Claude.ai / mcp-remote
       │  HTTP POST /mcp
       ▼
┌─────────────────────┐
│   mcp-stdio-bridge  │  ← this repo (Python, uvicorn)
│   server.py         │
└────────┬────────────┘
         │  stdin / stdout
         ▼
┌─────────────────────┐
│  Any stdio MCP      │
│  server             │
└─────────────────────┘
```

## How it works

- Uses the Python MCP SDK's `StreamableHTTPSessionManager` on the HTTP side
- Spawns the stdio MCP server as a subprocess per request (stateless)
- Bridges `list_tools` and `call_tool` calls transparently
- Handles OAuth discovery endpoints automatically (no auth required)

## Files

| File | Description |
|---|---|
| `server.py` | The bridge (copy this into your project) |
| `requirements.txt` | Bridge dependencies only |

---

## Usage

### 1. Copy `server.py` into your project

Place `server.py` alongside your stdio MCP server, or in a parent directory.

### 2. Install dependencies

```bash
pip install mcp uvicorn starlette
# also install your stdio MCP server's dependencies
```

### 3. Set environment variables

| Variable | Description | Default |
|---|---|---|
| `STDIO_CMD` | Command to launch the stdio MCP server | `python mcp_server.py` |
| `STDIO_CWD` | Working directory for the stdio server | (current dir) |
| `PORT` | HTTP port to listen on | `8080` |

### 4. Run

```bash
STDIO_CMD="python your_mcp_server.py" uvicorn server:app --host 0.0.0.0 --port 8080
```

---

## Docker / Cloud Run example

### Project layout

```
your-project/
  server.py          ← copied from this repo
  requirements.txt   ← merged bridge + server deps
  stdio/
    your_server.py   ← original stdio MCP server
    (other files...)
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Clone or copy your stdio MCP server
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    git clone --depth=1 https://github.com/your-org/your-mcp-server.git /tmp/mcp && \
    cp -r /tmp/mcp/src/. ./stdio/ && \
    rm -rf /tmp/mcp && \
    apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt server.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENV STDIO_CMD="python server.py"
ENV STDIO_CWD="/app/stdio"

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
```

### requirements.txt (merged)

```
mcp
uvicorn
starlette
# add your stdio server's dependencies below
shapely
pyproj
requests
```

---

## Connect from Claude.ai

Add to your MCP client config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "my-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://your-cloud-run-url/mcp"
      ]
    }
  }
}
```

---

## Real-world example

[mlit-geospatial-mcp-sgw](https://github.com/sobu-lab/mlit-geospatial-mcp-sgw) uses this bridge to expose the stdio-based [chirikuuka/mlit-geospatial-mcp](https://github.com/chirikuuka/mlit-geospatial-mcp) (Japan MLIT geospatial data API) over HTTP on Google Cloud Run.

---

## License

MIT
