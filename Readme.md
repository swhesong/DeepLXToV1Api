# DeepLX to OpenAI API Adapter

[

![Python Version](https://img.shields.io/badge/Python-3.8+-blue.svg)

](https://www.python.org/)
[

![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg?logo=docker)

](https://www.docker.com/)
[

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

](https://opensource.org/licenses/MIT)
[

![OpenAI Compatible](https://img.shields.io/badge/OpenAI%20API-Compatible-brightgreen)

](https://platform.openai.com/docs/api-reference/chat)

一个高性能、高可用的 DeepLX 适配器，它能将标准的 OpenAI 聊天接口请求（`/v1/chat/completions`）无缝转换为对多个 DeepLX 后端服务的调用。项目内置了**负载均衡、自动故障转移和后端健康检查**机制，确保翻译服务稳定、高效，并支持**流式响应**，带来如打字机般的流畅体验。

## ✨ 核心功能

-   **🤖 OpenAI API 兼容**: 完全兼容 OpenAI 的 `/v1/chat/completions` 接口格式，可无缝接入任何支持 OpenAI API 的客户端或应用。
-   **⚖️ 负载均衡与故障转移**: 自动在多个 DeepLX 后端 URL 之间分配请求，并能剔除失效节点，保证服务的高可用性。
-   **💨 流式响应 (Streaming)**: 支持 SSE (Server-Sent Events) 流式输出，可实现字符级的“打字机”效果，极大提升交互体验。
-   **🩺 自动健康检查**: 定期对所有后端 DeepLX 服务进行健康检查，动态更新可用节点池，并可将结果导出。
-   **🧩 灵活的模型命名**: 通过类似 `deeplx-EN-ZH` 的模型名称，直观地指定源语言和目标语言。支持自动语言检测。
-   **🐳 Docker 一键部署**: 提供 `docker-compose.yml`，只需简单配置即可一键启动服务，轻松部署。
-   **📊 丰富的监控端点**: 提供 `/health`, `/v1/urls/status` 等多个接口，方便监控服务和后端节点的实时状态。

## 📸 效果展示



![效果演示](https://github.com/Ink-Osier/DeepLXToV1Api/assets/133617214/12c60ed1-538b-4a24-8b4d-999e54f8dabd)



## 🚀 快速开始

### 1. 环境准备

-   确保您的系统已安装 [Git](https://git-scm.com/) 和 [Docker](https://www.docker.com/) / [Docker Compose](https://docs.docker.com/compose/install/)。

### 2. 克隆并配置项目

```bash
# 克隆仓库
git clone <your-repository-url>
cd <repository-directory>

# 创建必要的目录并设置权限
# 这将确保容器内的应用有权限写入结果和日志文件
mkdir -p ./results ./logs
chmod 777 ./results ./logs
```

### 3. 配置环境变量

在项目根目录下创建一个 `.env` 文件，用于存放您的配置。这是最关键的一步。

```bash
# 创建 .env 文件
touch ./app/.env
```

然后编辑 `./app/.env` 文件，填入您的 DeepLX 后端 URL。

**`.env` 文件内容示例：**

```env
# 必填：您的 DeepLX 后端服务 URL，用逗号分隔
# 示例：
TRANSLATION_API_URLS=http://127.0.0.1:1188/translate,https://deeplx.example.com/translate

# 可选：其他高级配置，请参考下文的“环境配置”章节
# CHECK_INTERVAL=300
# MAX_REQUESTS_PER_MINUTE=10000
# ENABLE_CHAR_STREAMING=true
# AUTO_UPDATE_URLS=true
```

### 4. 启动服务

一切准备就绪后，使用 `docker-compose` 启动服务。

```bash
docker-compose up -d
```

服务将在后台启动，默认监听宿主机的 `38888` 端口。您可以通过 `docker-compose logs -f` 查看实时日志。

## 📖 API 用法

### 端点

-   `POST /v1/chat/completions`

### 模型命名规则

通过 `model` 字段指定翻译行为：

-   **指定源语言和目标语言**: `deeplx-{SOURCE_LANG}-{TARGET_LANG}`
    -   `deeplx-EN-ZH`: 英语 ➡ 中文
    -   `deeplx-ZH-JA`: 中文 ➡ 日语
-   **自动检测源语言**: `deeplx-{TARGET_LANG}`
    -   `deeplx-ZH`: 自动检测源语言 ➡ 中文
    -   `deeplx-EN`: 自动检测源语言 ➡ 英语

### 调用示例

#### 1. 标准请求 (非流式)

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

**预期响应:**

```json
{
    "id": "chatcmpl-...",
    "object": "chat.completion",
    "created": 1709348239,
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

#### 2. 流式请求

使用 `stream: true` 来获取流式响应。使用 cURL 时建议添加 `--no-buffer` 选项以立即看到输出。

```bash
curl --no-buffer -X POST http://localhost:38888/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
    "model": "deeplx-ZH",
    "messages": [
        {
            "role": "user",
            "content": "Hi"
        }
    ],
    "stream": true
}'
```

**预期响应流:**

```plaintext
data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"deeplx-ZH","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"deeplx-ZH","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"deeplx-ZH","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## 🔧 环境配置

您可以通过修改 `.env` 文件或 `docker-compose.yml` 中的 `environment` 部分来调整服务行为。

| 环境变量                  | 默认值      | 描述                                                                    |
| ------------------------- | ----------- | ----------------------------------------------------------------------- |
| `TRANSLATION_API_URLS`    | (空)        | **(必填)** DeepLX 后端 URL 列表，用逗号 `,` 分隔。                         |
| `UVICORN_WORKERS`         | `1`         | Uvicorn 启动的工作进程数。对于 IO 密集型任务，`1` 通常足够。            |
| `CHECK_INTERVAL`          | `300`       | 自动健康检查的周期（秒）。                                              |
| `ENABLE_CHAR_STREAMING`   | `true`      | 是否启用字符级流式（打字机效果）。设为 `false` 则按块发送。             |
| `AUTO_UPDATE_URLS`        | `true`      | 健康检查后是否自动更新内存中的可用 URL 列表。                           |
| `MAX_REQUESTS_PER_MINUTE` | `10000`     | 全局请求速率限制（每分钟请求数）。                                      |
| `DISABLE_RATE_LIMIT`      | `false`     | 设为 `true` 可禁用速率限制功能。                                        |
| `TIMEOUT`                 | `300`       | 对后端 DeepLX 服务的请求超时时间（秒）。                                |
| `MAX_CONSECUTIVE_FAILURES`| `15`        | 一个 URL 连续失败多少次后，在一段时间内不再使用它。                     |
| `EXPORT_PATH`             | `./results/useful.txt` | 健康检查结果的导出文件路径。                                            |
| `LOG_LEVEL`               | `info`      | 日志级别，可选 `debug`, `info`, `warning`, `error`。                      |

## 🩺 监控与诊断

项目提供了一些端点用于监控服务状态：

-   `GET /health`: 提供服务整体健康状况的快速摘要。
-   `GET /v1/urls/status`: 获取所有已配置的后端 URL 的详细状态，包括延迟、失败次数等。
-   `POST /v1/check-and-export-urls`: 手动触发一次对所有 URL 的健康检查，并将可用列表写入文件。

## 📝 许可证

本项目采用 [MIT License](https://opensource.org/licenses/MIT) 授权。
