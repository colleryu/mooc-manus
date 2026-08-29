# API 模块：Agent 的大脑与编排中心

`api` 是 MoocManus 的核心：既提供 HTTP 接口，也负责 Agent 规划执行、Function Calling、MCP/A2A、沙箱调度、异步任务、事件持久化和文件交付。

## 功能

- 管理会话创建、查询、删除、发消息、停止和已读状态。
- 运行 Planner–ReAct 工作流，生成计划、逐步执行、更新计划并总结。
- 向 LLM 暴露工具 Schema，解析 `tool_calls`，执行后把结果写回上下文。
- 管理 Shell、文件、浏览器、搜索、用户交互、MCP、A2A 七类工具包。
- 为会话创建/恢复 Docker Sandbox，通过 HTTP 和 CDP 控制环境。
- 保存会话、Memory、计划、事件和文件元数据，上传/下载任务产物。
- 通过 Redis Streams 驱动任务，通过 SSE 实时推送事件。
- 提供 LLM、Agent、MCP、A2A 动态配置和基础设施健康检查。

## 技术与实现

### Function Calling

`domain/services/tools/base.py` 的 `@tool` 装饰器把名称、描述、参数和必填项注册为 OpenAI Function Schema。`BaseAgent` 把 Schema 传给模型，读取 `tool_calls`，完成 JSON 参数修复、工具路由、调用重试和 Tool Result 回填。内置 `ShellTool`、`FileTool`、`BrowserTool`、`SearchTool`、`MessageTool`、`MCPTool`、`A2ATool`。

### Planner–ReAct

- `PlannerAgent` 通过结构化 JSON 创建 `Plan`，并按步骤结果动态更新计划。
- `ReActAgent` 围绕单步循环“推理 → 工具调用 → 观察”，最后生成步骤结果。
- `PlannerReActFlow` 串联 `PLANNING → EXECUTING → UPDATING → SUMMARIZING → COMPLETED`。
- Memory 按会话和 Agent 分开持久化，步骤间压缩上下文，兼顾连续性和 Token 成本。

### MCP

`MCPClientManager` 使用官方 Python SDK 管理多个 Server，支持 **stdio、SSE、Streamable HTTP**。它负责连接、`list_tools` 发现、Schema 缓存、名称路由、`call_tool` 和异步清理。配置可由 API 新增、删除、启停，无需修改 Agent 主循环。

### A2A

`A2AClientManager` 请求 `/.well-known/agent-card.json` 获取远程 Agent 能力并缓存；执行时通过带 `A2A-Version` 的 JSON-RPC `SendMessage` 把子任务委派给远程 Agent。

### 异步任务与事件流

- `RedisStreamTask` 为每次运行提供输入、输出 Stream 和后台 asyncio Task。
- `AgentTaskRunner` 消费消息、构建 Flow，并持久化 Plan/Step/Tool/Message/Error/Done 事件。
- `/sessions/{id}/events` 通过 SSE 推送，支持 `Last-Event-ID`/`after` 游标、心跳和续传。
- PostgreSQL 保存历史，Redis Streams 保存运行态消息，前端断线不会丢失完整过程。

### 分层架构与基础设施

```text
interfaces       FastAPI Routes / Schema / DI / Exception Handler
      ↓
application      Session / File / Config / Status 用例
      ↓
domain           Models / Repository Protocol / Agent / Flow / Tool
      ↓
infrastructure   OpenAI / PostgreSQL / Redis / COS / Docker / Playwright
```

Domain 通过 Protocol 依赖 LLM、Sandbox、Browser、Search、Storage 和 Repository，基础设施层提供适配器，体现依赖倒置和可替换基础设施。

### 数据、文件与安全

- SQLAlchemy 2 Async + asyncpg 操作 PostgreSQL，Alembic 管迁移，JSONB 保存事件与 Memory。
- Redis 承担消息流和运行态任务协调；COS 适配器保存附件与生成产物。
- API 返回配置时排除 `api_key`，日志包含敏感数据过滤，密钥通过本地配置注入。

## 代码导航

```text
app/
├── domain/services/agents/       # BaseAgent、PlannerAgent、ReActAgent
├── domain/services/flows/        # PlannerReActFlow
├── domain/services/tools/        # Function Calling、MCP、A2A、内置工具
├── domain/models/event.py        # 领域事件模型
├── application/services/         # 会话、文件、配置、状态用例
├── infrastructure/external/      # LLM、Task、Sandbox、Browser、Search
├── infrastructure/repositories/  # PostgreSQL/File Config 仓库
├── infrastructure/storage/       # PostgreSQL、Redis、COS
└── interfaces/endpoints/         # FastAPI 路由
```

## 运行与验证

```bash
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run pytest
```

API 文档：<http://localhost:8000/docs>；健康检查：<http://localhost:8000/api/status>。

## 学习成果

这一模块把 LLM 调用从一次性问答升级成有状态、可执行、可扩展的 Agent Runtime。我掌握了 Tool Schema 如何连接模型与真实能力，Planner 和 ReAct 如何协作处理长任务，MCP/A2A 如何解除能力耦合，以及任务流、事件流、存储、错误处理和资源释放如何共同保证 Agent 可靠运行。
