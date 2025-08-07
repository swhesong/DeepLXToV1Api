🚀 快速开始
1. 环境准备
确保您的系统已安装 Git 和 Docker / Docker Compose。
2. 克隆并配置项目
<BASH>
# 克隆仓库
git clone <your-repository-url>
cd <repository-directory>
# 创建必要的目录并设置权限
# 这将确保容器内的应用有权限写入结果和日志文件
mkdir -p ./results ./logs
chmod 777 ./results ./logs
# (可选但推荐) 设置目录所有者为容器内用户(non-root)
# 注意：本项目 docker-compose.yml 中使用了 root 用户，此步骤可跳过，但为最佳实践
# sudo chown -R 1000:1000 ./results ./logs 2>/dev/null || true
3. 配置环境变量
在项目根目录下创建一个 .env 文件，用于存放您的配置。这是最关键的一步。

<BASH>
# 创建 .env 文件
touch ./app/.env
然后编辑 ./app/.env 文件，填入您的 DeepLX 后端 URL。

.env 文件内容示例：

<ENV>
# 必填：您的 DeepLX 后端服务 URL，用逗号分隔
# 示例：
TRANSLATION_API_URLS=http://127.0.0.1:1188/translate,https://deeplx.example.com/translate
# 可选：其他高级配置，请参考下文的“环境配置”章节
# CHECK_INTERVAL=300
# MAX_REQUESTS_PER_MINUTE=10000
# ENABLE_CHAR_STREAMING=true
# AUTO_UPDATE_URLS=true
4. 启动服务
一切准备就绪后，使用 docker-compose 启动服务。

<BASH>
docker-compose up -d
服务将在后台启动，默认监听宿主机的 38888 端口。您可以通过 docker-compose logs -f 查看实时日志。

📖 API 用法
端点
POST /v1/chat/completions
模型命名规则
通过 model 字段指定翻译行为：

指定源语言和目标语言: deeplx-{SOURCE_LANG}-{TARGET_LANG}
deeplx-EN-ZH: 英语 ➡ 中文
deeplx-ZH-JA: 中文 ➡ 日语
自动检测源语言: deeplx-{TARGET_LANG}
deeplx-ZH: 自动检测源语言 ➡ 中文
deeplx-EN: 自动检测源语言 ➡ 英语
调用示例
1. 标准请求 (非流式)
<BASH>
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
预期响应:

<JSON>
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
2. 流式请求
使用 stream: true 来获取流式响应。使用 cURL 时建议添加 --no-buffer 选项以立即看到输出。

<BASH>
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
预期响应流:

<PLAINTEXT>
data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"deeplx-ZH","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}
data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"deeplx-ZH","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}
data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"deeplx-ZH","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
data: [DONE]
🔧 环境配置
您可以通过修改 .env 文件或 docker-compose.yml 中的 environment 部分来调整服务行为。

环境变量	默认值	描述
TRANSLATION_API_URLS	(空)	(必填) DeepLX 后端 URL 列表，用逗号 , 分隔。
UVICORN_WORKERS	1	Uvicorn 启动的工作进程数。对于 IO 密集型任务，1 通常足够。
CHECK_INTERVAL	300	自动健康检查的周期（秒）。
ENABLE_CHAR_STREAMING	true	是否启用字符级流式（打字机效果）。设为 false 则按块发送。
AUTO_UPDATE_URLS	true	健康检查后是否自动更新内存中的可用 URL 列表。
MAX_REQUESTS_PER_MINUTE	10000	全局请求速率限制（每分钟请求数）。
DISABLE_RATE_LIMIT	false	设为 true 可禁用速率限制功能。
TIMEOUT	300	对后端 DeepLX 服务的请求超时时间（秒）。
MAX_CONSECUTIVE_FAILURES	15	一个 URL 连续失败多少次后，在一段时间内不再使用它。
EXPORT_PATH	./results/useful.txt	健康检查结果的导出文件路径。
LOG_LEVEL	info	日志级别，可选 debug, info, warning, error。
🩺 监控与诊断
项目提供了一些端点用于监控服务状态：

GET /health: 提供服务整体健康状况的快速摘要。
GET /v1/urls/status: 获取所有已配置的后端 URL 的详细状态，包括延迟、失败次数等。
POST /v1/check-and-export-urls: 手动触发一次对所有 URL 的健康检查，并将可用列表写入文件。
📝 许可证
本项目采用 MIT License 授权。
