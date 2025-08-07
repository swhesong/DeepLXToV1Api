# DeepLX to V1 API - 高性能翻译代理服务

一个强大、可靠且高性能的代理服务，它将多个 [DeepLX](https://github.com/OwO-Network/DeepLX) 服务聚合，并将其转换为一个统一的、兼容 OpenAI `v1/chat/completions` 格式的 API 接口。

本项目专为需要高可用性和高吞吐量翻译服务的场景而设计，内置了智能负载均衡、自动健康检查和动态端点管理等高级功能。
## 用法

仓库内已包含相关文件和目录，拉到本地后修改 docker-compose.yml 文件里的环境变量后运行`docker-compose up -d`即可。

模型名说明：

- 示例：
    - `deeplx-EN-ZH`: 英文转中文
    - `deeplx-ZH-EN`: 中文转英文
    - `deeplx-EN`: 自动识别语言转英文
    - `deeplx-ZH`: 自动识别语言转中文
## 调用示例：

```json
{
    "messages": [
        {
            "role": "user",
            "content": [
                "Hi"
            ]
        }
    ],
    "stream": true,
    "model": "deeplx-ZH"
}
```

预期响应：

```plaintext
data: {"id": "a0e35ab6-b859-441b-93e6-6391dcb468ed", "object": "chat.completion.chunk", "created": 1709348239.833917, "model": "deeplx-ZH", "choices": [{"index": 0, "delta": {"content": "\u4f60\u597d"}, "finish_reason": null}]}

data: [DONE]


```

## 效果展示:

![image](https://github.com/Ink-Osier/DeepLXToV1Api/assets/133617214/12c60ed1-538b-4a24-8b4d-999e54f8dabd)


## ✨ 核心功能

*   **🚀 OpenAI 格式兼容**：完美模拟 `v1/chat/completions` 接口，无缝接入各类支持 OpenAI API 的应用和客户端。
*   **🧠 智能负载均衡**：不仅仅是轮询！服务会根据每个 DeepLX 端点的延迟、负载和成功率进行动态评分，始终选择最优的端点进行翻译，最大化性能和成功率。
*   **🩺 自动健康检查与自愈**：后台任务会定期检测所有 DeepLX 端点的可用性，自动剔除失效节点，并在其恢复后自动重新加入服务池。
*   **🔄 动态 URL 管理**：可通过 API 或后台任务自动更新可用的 DeepLX 端点列表，无需重启服务。
*   ** STREAM 支持**：完美支持流式响应，提供类似打字机的逐字输出效果，提升用户体验。
*   **⚙️ 高度可配置**：通过环境变量，您可以轻松调整服务的几乎所有参数，包括速率限制、超时、并发数等。
*   **📊 强大的监控 API**：提供 `/health`, `/v1/urls/status` 等多个接口，方便您实时监控服务状态和各个端点的性能。
*   **🐳 Docker & CI/CD**：提供开箱即用的 `docker-compose.yml` 文件，并通过 GitHub Actions 自动构建和发布多平台（`linux/amd64`, `linux/arm64`）的 Docker 镜像。

## 🚀 快速开始 (使用 Docker Compose)

这是最推荐的部署方式，简单、快速且功能完整。

### 步骤 1: 准备文件

克隆本仓库（或仅下载 `docker-compose.yml` 文件）到您的服务器。

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

### 步骤 2: 创建并配置 `.env` 文件

这是最关键的一步。服务的所有配置都来源于此文件。

首先，创建 `app` 目录和 `.env` 文件：

```bash
mkdir -p ./app
touch ./app/.env
```

然后，编辑 `./app/.env` 文件，填入您要使用的 DeepLX API URL。

**`.env` 文件示例:**
```env
# 【必填】提供一个或多个 DeepLX API URL，用逗号隔开
TRANSLATION_API_URLS=https://api.deeplx.org/translate,https://deeplx.another-one.com/translate

# 【可选】其他常用配置，详情见下文配置章节
LOG_LEVEL=INFO
CHECK_INTERVAL=300
AUTO_UPDATE_URLS=true
ENABLE_CHAR_STREAMING=true
```

### 步骤 3: 启动服务

使用 Docker Compose 一键启动服务。

```bash
docker-compose up -d
```

服务将会在后台启动，并将宿主机的 `38888` 端口映射到容器。

### 步骤 4: 验证服务

使用 `curl` 或任何 API 工具向 `http://localhost:38888` 发送请求。

```bash
curl http://localhost:38888/health
```

如果看到类似下面的响应，说明服务已成功启动！

```json
{
  "status": "healthy",
  "timestamp": "2023-10-27T10:00:00.123456",
  "service_info": { ... },
  "endpoints": { ... },
  "performance": { ... }
}
```

## ⚙️ 服务配置 (环境变量)

您可以通过修改 `./app/.env` 文件来调整服务行为。

| 环境变量                   | 描述                                                                       | 默认值          |
| -------------------------- | -------------------------------------------------------------------------- | --------------- |
| **核心配置**               |                                                                            |                 |
| `TRANSLATION_API_URLS`     | **(必填)** DeepLX 端点 URL 列表，用逗号分隔。                                | `""`            |
| `LOG_LEVEL`                | 日志级别，可选 `DEBUG`, `INFO`, `WARNING`, `ERROR`。                         | `INFO`          |
| `UVICORN_WORKERS`          | Web 服务器的工作进程数。对于IO密集型任务，`1` 通常是最佳选择。             | `1`             |
| `DEBUG`                    | 是否开启 FastAPI 的调试模式。                                              | `false`         |
| `ENABLE_CHAR_STREAMING`    | 在流式响应中，是否启用逐字模拟打字机效果。                                 | `true`          |
| **URL 健康检查**           |                                                                            |                 |
| `CHECK_INTERVAL`           | 后台自动检查 URL 可用性的时间间隔（秒）。                                  | `300`           |
| `INITIAL_CHECK_DELAY`      | 服务启动后，延迟多久开始第一次 URL 检查（秒）。                            | `30`            |
| `CHECK_TIMEOUT`            | 检查单个 URL 时的网络超时时间（秒）。                                      | `5`             |
| `MAX_CONSECUTIVE_FAILURES` | 一个 URL 连续失败多少次后，会被暂时禁用。                                  | `15`            |
| `AUTO_UPDATE_URLS`         | 检查后，是否自动用可用的 URL 列表更新当前服务使用的列表。                  | `true`          |
| `MIN_AVAILABLE_URLS`       | 当 `AUTO_UPDATE_URLS` 开启时，至少需要有多少个可用 URL 才会执行更新。      | `2`             |
| **性能与限制**             |                                                                            |                 |
| `MAX_REQUESTS_PER_MINUTE`  | 全局每分钟最大请求数。                                                     | `10000`         |
| `DISABLE_RATE_LIMIT`       | 是否禁用速率限制。                                                         | `false`         |
| `TIMEOUT`                  | 调用 DeepLX 翻译接口的超时时间（秒）。                                     | `300`           |
| `MAX_WORKERS`              | 并发检查 URL 时的最大并发数。                                              | `5`             |

## 📖 API 使用文档

### 1. 翻译接口 (`/v1/chat/completions`)

这是核心的翻译接口，完全兼容 OpenAI 的格式。

*   **Endpoint**: `POST /v1/chat/completions`
*   **Content-Type**: `application/json`

#### 模型命名规则

通过 `model` 字段来指定源语言和目标语言：

*   `deeplx-SOURCE-TARGET`: 例如 `deeplx-EN-ZH` (英语到中文)。
*   `deeplx-TARGET`: 自动检测源语言，例如 `deeplx-JA` (自动识别语言到日语)。

#### 请求示例

```bash
curl -X POST http://localhost:38888/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
    "model": "deeplx-EN-ZH",
    "messages": [
        {
            "role": "user",
            "content": "Hello, world!"
        }
    ],
    "stream": false
}'
```

#### 响应示例 (非流式)

```json
{
    "id": "c3a7f8b2-1e9d-4c6a-8f5b-9d7e0c1a3b4d",
    "object": "chat.completion",
    "created": 1677652288,
    "model": "deeplx-EN-ZH",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "你好，世界！"
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5
    }
}
```

#### 响应示例 (流式, `stream: true`)

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"deeplx-EN-ZH","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"deeplx-EN-ZH","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"deeplx-EN-ZH","choices":[{"index":0,"delta":{"content":"，"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"deeplx-EN-ZH","choices":[{"index":0,"delta":{"content":"世界"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"deeplx-EN-ZH","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

### 2. 监控与管理 API

| Method | Endpoint                       | 描述                                                                                   |
| ------ | ------------------------------ | -------------------------------------------------------------------------------------- |
| `GET`  | `/health`                      | 检查服务的整体健康状况，包括可用端点数量和性能摘要。                                     |
| `GET`  | `/v1/urls/status`              | 获取所有已配置 URL 的详细状态，包括延迟、失败次数、健康评分等。                          |
| `POST` | `/v1/check-and-export-urls`    | 手动触发一次所有 URL 的健康检查，并将可用 URL 列表保存到结果文件（默认为 `./results/useful.txt`）。 |
| `GET`  | `/v1/models`                   | 列出服务支持的翻译模型（语言对）。                                                     |
| `GET`  | `/docs`                        | 访问自动生成的 Swagger UI 交互式 API 文档。                                            |

## 🏗️ 部署与维护

### 推荐的 `docker-compose.yml`

为了获得最佳的稳定性和启动体验，我们建议在 `docker-compose.yml` 中添加 `healthcheck` 配置。

```yaml
version: '3.8'

services:
  deeplx:
    image: devinglaw/deeplxtov1api:latest
    container_name: deeplxtov1api
    restart: always
    user: root
    ports:
      - "38888:8000"
    env_file:
      - ./app/.env
    environment:
      - UVICORN_WORKERS=1
      - DEBUG=false
      - INITIAL_CHECK_DELAY=30
    
    # 健康检查配置，防止因启动慢而被错误地重启
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      # 关键：给予容器 60 秒的启动宽限期
      start_period: 60s
      
    volumes:
      - ./results:/app/results
      - ./logs:/app/logs
      - /etc/localtime:/etc/localtime:ro
      
    logging:
      driver: "json-file"
      options:
        max-size: "20m"
        max-file: "5"
    
    networks:
      - deeplx-network

networks:
  deeplx-network:
    driver_opts:
      com.docker.network.driver.mtu: 1500
```

### 查看日志

```bash
docker-compose logs -f deeplx
```

### 自动更新 Docker 镜像

您可以配合 [Watchtower](https://containrrr.dev/watchtower/) 来自动拉取并更新到最新的 Docker 镜像，实现无人值守更新。

```yaml
# 在 docker-compose.yml 中添加 watchtower 服务
services:
  # ... 您的 deeplx 服务 ...

  watchtower:
    image: containrrr/watchtower
    container_name: watchtower
    restart: always
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    # 每 6 小时检查一次更新
    command: --interval 21600
```

## 🤖 自动化构建 (CI/CD)

本项目使用 GitHub Actions 实现了全自动的 CI/CD 流程。

*   **触发条件**: 当创建新的 `release` 时，或手动触发。
*   **构建平台**: `linux/amd64` 和 `linux/arm64`。
*   **发布**: 自动构建并推送 Docker 镜像到 [Docker Hub](https://hub.docker.com/r/devinglaw/deeplxtov1api)。
*   **标签策略**:
    *   `latest`: 仅在创建 `release` 时更新，代表最新的稳定版。
    *   `v1.2.3`: 对应 Git 标签 `v1.2.3`。
    *   `v1.2`: 对应主版本和次版本号。

<details>
<summary>点击查看 GitHub Actions Workflow 源码 (`.github/workflows/docker.yml`)</summary>

```yaml
# .github/workflows/docker.yml

name: Build and Push Docker Image

on:
  release:
    types: [created]
  workflow_dispatch:
    inputs:
      tag:
        description: '为手动构建指定一个 Docker 标签 (例如: 1.2.4-beta)'
        required: false
        type: string

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Ensure LF line endings for shell scripts
        run: |
          if ! command -v dos2unix &> /dev/null; then
            sudo apt-get update -y && sudo apt-get install -y dos2unix
          fi
          find . -type f -name "*.sh" -exec dos2unix {} +

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        id: buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to Docker Hub
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: devinglaw/deeplxtov1api
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=${{ github.event.inputs.tag }},enable=${{ github.event_name == 'workflow_dispatch' && github.event.inputs.tag != '' }}
            type=raw,value=latest,enable=${{ github.event_name == 'release' }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```
</details>

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
