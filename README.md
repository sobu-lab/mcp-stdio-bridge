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

### A. ローカルで直接起動する場合

#### 1. `server.py` をプロジェクトにコピー

stdio MCP サーバーと同じディレクトリか、親ディレクトリに配置します。

#### 2. 依存パッケージをインストール

```bash
pip install mcp uvicorn starlette
# stdio MCP サーバーの依存パッケージも別途インストール
```

#### 3. 環境変数を設定して起動

| 変数名 | 説明 | デフォルト |
|---|---|---|
| `STDIO_CMD` | stdio MCP サーバーの起動コマンド | `python mcp_server.py` |
| `STDIO_CWD` | stdio サーバーの作業ディレクトリ | （カレントディレクトリ） |
| `PORT` | HTTP リッスンポート | `8080` |

```bash
STDIO_CMD="python your_mcp_server.py" uvicorn server:app --host 0.0.0.0 --port 8080
```

---

### B. Docker / Cloud Run で使う場合

Dockerfile の中で stdio サーバーのクローン・`server.py` のコピー・依存パッケージのインストールをすべて行うため、**手順 A の 1・2 は不要**です。

#### ディレクトリ構成

```
your-project/
  server.py          ← このリポジトリからコピー
  requirements.txt   ← ブリッジ + サーバーの依存をまとめたもの
  Dockerfile
```

#### Dockerfile

変更が必要な箇所にコメントを記載しています：

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# ↓【変更】stdio MCP サーバーのリポジトリURL
ARG STDIO_REPO=https://github.com/your-org/your-mcp-server.git
# ↓【変更】コードが src/ 以下にある場合は /tmp/mcp/src/. のまま
#          src/ がなくルート直下にある場合は /tmp/mcp/. に変更
ARG STDIO_SRC=/tmp/mcp/src/.

RUN apt-get update && apt-get install -y --no-install-recommends git && \
    git clone --depth=1 $STDIO_REPO /tmp/mcp && \
    cp -r $STDIO_SRC ./stdio/ && \
    rm -rf /tmp/mcp && \
    apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY requirements.txt server.py ./
RUN pip install --no-cache-dir -r requirements.txt

# ↓【変更】stdio サーバーの起動コマンド（server.py 以外の場合）
ENV STDIO_CMD="python server.py"
ENV STDIO_CWD="/app/stdio"

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
```

#### requirements.txt

ブリッジ必須の3行 + stdio サーバーの依存パッケージを追記します：

```
# ブリッジ必須（変更不要）
mcp
uvicorn
starlette
# ↓【変更】stdio サーバーの requirements.txt の内容をここに追加
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

## Google Cloud Run へのデプロイ

GitHub Actions を使って `main` ブランチへの push で自動デプロイする手順です。

> **注意：コマンドの行継続文字について**
> このマニュアルのコマンドは **bash（Linux/Mac/Git Bash/GCP Cloud Shell）** 向けに `\` で記述しています。
> Windows の場合は PowerShell → `` ` ``、コマンドプロンプト → `^` に置換してください。

### 前提条件

- Google Cloud SDK (gcloud CLI) インストール済み・ログイン済み
- GitHub CLI (gh) インストール済み・ログイン済み
- GCP プロジェクト作成済み・課金有効化済み
- GitHub リポジトリ作成済み

以降のコマンドの `<YOUR_PROJECT_ID>` と `<GITHUB_ORG>/<REPO_NAME>` を自分の環境に置き換えてください。

### 1. GCP API の有効化

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  --project=<YOUR_PROJECT_ID>
```

### 2. Artifact Registry リポジトリ作成

```bash
gcloud artifacts repositories create cloud-run-images \
  --repository-format=docker \
  --location=asia-northeast1 \
  --project=<YOUR_PROJECT_ID>
```

### 3. サービスアカウントの作成と権限付与

```bash
gcloud iam service-accounts create github-actions-cloudrun \
  --display-name="GitHub Actions Cloud Run Deploy" \
  --project=<YOUR_PROJECT_ID>

SA="github-actions-cloudrun@<YOUR_PROJECT_ID>.iam.gserviceaccount.com"

for role in \
  roles/run.admin \
  roles/artifactregistry.admin \
  roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding <YOUR_PROJECT_ID> \
    --member="serviceAccount:$SA" \
    --role="$role" \
    --quiet
done
```

### 4. Workload Identity Federation（WIF）の設定

```bash
PROJECT_NUMBER=$(gcloud projects describe <YOUR_PROJECT_ID> --format="value(projectNumber)")

gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  --project=<YOUR_PROJECT_ID>

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" \
  --attribute-condition="assertion.repository.startsWith('<GITHUB_ORG>/')" \
  --project=<YOUR_PROJECT_ID>

gcloud iam service-accounts add-iam-policy-binding \
  "github-actions-cloudrun@<YOUR_PROJECT_ID>.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/<GITHUB_ORG>/<REPO_NAME>" \
  --project=<YOUR_PROJECT_ID>
```

> **2つ目以降のリポジトリを追加する場合**、プール・プロバイダーの作成は不要です。バインディングの追加のみ行ってください：
>
> ```bash
> PROJECT_NUMBER=$(gcloud projects describe <YOUR_PROJECT_ID> --format="value(projectNumber)")
>
> gcloud iam service-accounts add-iam-policy-binding \
>   "github-actions-cloudrun@<YOUR_PROJECT_ID>.iam.gserviceaccount.com" \
>   --role="roles/iam.workloadIdentityUser" \
>   --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/<GITHUB_ORG>/<NEW_REPO_NAME>" \
>   --project=<YOUR_PROJECT_ID>
> ```

### 5. GitHub Secrets の登録

```bash
gh secret set WIF_PROVIDER \
  --body="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider" \
  --repo=<GITHUB_ORG>/<REPO_NAME>

gh secret set WIF_SERVICE_ACCOUNT \
  --body="github-actions-cloudrun@<YOUR_PROJECT_ID>.iam.gserviceaccount.com" \
  --repo=<GITHUB_ORG>/<REPO_NAME>

# stdio MCP サーバーが必要とする環境変数があれば追加
# gh secret set YOUR_SECRET --body="<VALUE>" --repo=<GITHUB_ORG>/<REPO_NAME>
```

### 6. deploy.yml の作成

`.github/workflows/deploy.yml` を作成し、`env` セクションを自分の環境に合わせて設定します：

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]

env:
  PROJECT_ID: <YOUR_PROJECT_ID>
  REGION: asia-northeast1
  IMAGE: asia-northeast1-docker.pkg.dev/<YOUR_PROJECT_ID>/cloud-run-images/<SERVICE_NAME>

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.WIF_PROVIDER }}
          service_account: ${{ secrets.WIF_SERVICE_ACCOUNT }}

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker asia-northeast1-docker.pkg.dev --quiet

      - name: Build and push Docker image
        run: |
          docker build -t $IMAGE:${{ github.sha }} -t $IMAGE:latest .
          docker push $IMAGE:${{ github.sha }}
          docker push $IMAGE:latest

      - uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: <SERVICE_NAME>
          region: ${{ env.REGION }}
          image: ${{ env.IMAGE }}:${{ github.sha }}
          env_vars: |
            YOUR_ENV_VAR=${{ secrets.YOUR_SECRET }}
```

### 7. 初回デプロイ

必要なファイルをコミットして push します。GitHub Actions が自動で起動し、ビルド・デプロイが実行されます。

```bash
git init
git branch -m main
git add Dockerfile server.py requirements.txt .github/workflows/deploy.yml
git commit -m "Initial commit"
git remote add origin https://github.com/<GITHUB_ORG>/<REPO_NAME>.git
git push -u origin main
```

> すでに GitHub 上でリポジトリを作成済みで、ローカルと紐付け済みの場合は以下のみ：
>
> ```bash
> git push origin main
> ```

### 8. 未認証アクセスの許可

初回デプロイ後に実行します。これを行わないと Claude.ai 等からのリクエストが 403 で拒否されます：

```bash
gcloud run services add-iam-policy-binding <SERVICE_NAME> \
  --region=asia-northeast1 \
  --member="allUsers" \
  --role="roles/run.invoker" \
  --project=<YOUR_PROJECT_ID>
```

> **注意:** `deploy.yml` に `--allow-unauthenticated` フラグを追加しても、組織ポリシーによって拒否される場合があります。その場合は上記コマンドを手動で実行してください。

### コスト管理（Cloud Run 無料枠）

| 項目 | 無料枠 |
|---|---|
| リクエスト数 | 200万回/月 |
| CPU | 180,000 vCPU秒/月 |
| メモリ | 360,000 GB秒/月 |
| Artifact Registry | 0.5GB/月 |

古いイメージの削除：

```bash
gcloud artifacts docker images list \
  asia-northeast1-docker.pkg.dev/<YOUR_PROJECT_ID>/cloud-run-images/<SERVICE_NAME>

gcloud artifacts docker images delete \
  "asia-northeast1-docker.pkg.dev/<YOUR_PROJECT_ID>/cloud-run-images/<SERVICE_NAME>@sha256:<DIGEST>" \
  --quiet
```

### トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| 403 Forbidden | 未認証アクセスが拒否されている | `allUsers` に `roles/run.invoker` を付与 |
| unauthorized_client | WIF の attribute-condition が不一致 | `--attribute-condition` のリポジトリ名を確認 |
| Request timed out (-32001) | コールドスタート | `--min-instances 1` を設定 |

---

## ライセンス

MIT
