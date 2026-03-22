# mcp-stdio-bridge

任意の **stdio MCP サーバー** を **Streamable HTTP MCP サーバー** として公開する汎用ブリッジです。

元の MCP サーバーのコードを一切変更せずに使えます。環境変数でコマンドを指定するだけで、Google Cloud Run など HTTP を受け付けるサービスにデプロイできます。

```
Claude.ai / mcp-remote
       │  HTTP POST /mcp
       ▼
┌─────────────────────┐
│   mcp-stdio-bridge  │  ← このリポジトリ (Python / uvicorn)
│   server.py         │
└────────┬────────────┘
         │  stdin / stdout
         ▼
┌─────────────────────┐
│  任意の stdio MCP   │
│  サーバー           │
└─────────────────────┘
```

## 仕組み

- Python MCP SDK の `StreamableHTTPSessionManager` で HTTP を処理
- リクエストごとに stdio MCP サーバーをサブプロセスとして起動（ステートレス）
- `list_tools` / `call_tool` を透過的にブリッジ
- OAuth ディスカバリエンドポイントを自動処理（認証不要で返却）

## ファイル

| ファイル | 説明 |
|---|---|
| `server.py` | ブリッジ本体（プロジェクトにコピーして使用） |
| `requirements.txt` | ブリッジの依存パッケージのみ |

---

## 使い方

### 1. `server.py` をプロジェクトにコピー

stdio MCP サーバーと同じディレクトリか、親ディレクトリに配置します。

### 2. 依存パッケージをインストール

```bash
pip install mcp uvicorn starlette
# stdio MCP サーバーの依存パッケージも別途インストール
```

### 3. 環境変数を設定

| 変数名 | 説明 | デフォルト |
|---|---|---|
| `STDIO_CMD` | stdio MCP サーバーの起動コマンド | `python mcp_server.py` |
| `STDIO_CWD` | stdio サーバーの作業ディレクトリ | （カレントディレクトリ） |
| `PORT` | HTTP リッスンポート | `8080` |

### 4. 起動

```bash
STDIO_CMD="python your_mcp_server.py" uvicorn server:app --host 0.0.0.0 --port 8080
```

---

## Docker / Cloud Run での使用例

### ディレクトリ構成

```
your-project/
  server.py          ← このリポジトリからコピー
  requirements.txt   ← ブリッジ + サーバーの依存をまとめたもの
  stdio/
    your_server.py   ← 元の stdio MCP サーバー
    （その他のファイル）
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# stdio MCP サーバーをクローン
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

### requirements.txt（まとめた例）

```
mcp
uvicorn
starlette
# stdio サーバーの依存パッケージを以下に追加
shapely
pyproj
requests
```

---

## Claude.ai からの接続設定

MCP クライアントの設定ファイル（例: `claude_desktop_config.json`）に追記します：

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

## 実際の使用例

[mlit-geospatial-mcp-sgw](https://github.com/sobu-lab/mlit-geospatial-mcp-sgw) では、このブリッジを使って stdio ベースの [chirikuuka/mlit-geospatial-mcp](https://github.com/chirikuuka/mlit-geospatial-mcp)（国土交通省 不動産情報ライブラリ API）を Google Cloud Run 上で HTTP として公開しています。

---

## ライセンス

MIT
