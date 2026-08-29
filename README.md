# MoocManus：从零实现的通用 AI Agent

> 一个面向学习与工程实践的 Manus 风格通用智能体：先规划、再执行，按需调用本地工具、MCP 工具和远程 Agent，并实时展示完整过程。

MoocManus 不是对话框套壳，而是一套完整的 Agent 系统实践。项目贯通了 **LLM Function Calling、Planner–ReAct 多智能体协作、MCP、A2A、沙箱执行、浏览器自动化、事件流、持久化与全栈交互**，把课程中分散的概念组合成一个能运行、能观察、能扩展的工程。

## 我的学习成果

- 实现 Planner Agent 与 ReAct Agent 分工：规划、执行、动态更新计划、汇总结果。
- 自建 Function Calling 工具框架，将 Python 方法注册为 JSON Schema 并交给模型选择。
- 接入 MCP，管理 stdio、SSE、Streamable HTTP 服务的工具发现、调用和生命周期。
- 接入 A2A，通过 Agent Card 发现远程 Agent，再用 JSON-RPC 分派任务。
- 为每个会话提供 Docker Sandbox，支持 Shell、文件和 Chromium 浏览器操作。
- 使用 Redis Streams 连接后台任务与 SSE，实现可恢复、可去重的实时事件流。
- 使用 PostgreSQL 保存会话、记忆、计划、事件和文件元数据，对象存储保存产物。
- 用 Next.js 构建 Agent UI：计划、步骤、工具调用、附件、产物预览和 VNC 桌面。

## 系统架构

```text
┌──────────────── Next.js 16 / React 19 UI ────────────────┐
│ 会话管理 · 对话时间线 · Plan/Step/Tool 展示 · VNC · 设置 │
└──────────────────── REST + SSE ───────────────────────────┘
                              │
┌──────────────────── FastAPI API ──────────────────────────┐
│ Interfaces → Application → Domain → Infrastructure       │
│  Planner Agent ──计划/更新──┐                             │
│                             ├─ Planner–ReAct Flow         │
│  ReAct Agent ──推理/工具/总结┘                             │
│       ├─ Function Calling：Shell / File / Browser / Search│
│       ├─ MCP：stdio / SSE / Streamable HTTP               │
│       └─ A2A：Agent Card / JSON-RPC Remote Agent          │
└───────┬─────────────────┬───────────────────┬─────────────┘
        │                 │                   │
  PostgreSQL         Redis Streams      Object Storage
 会话/记忆/事件       任务输入输出          文件与产物
        │
┌───────▼──────── per-session Docker Sandbox ───────────────┐
│ FastAPI control API · Shell · File · Supervisor           │
│ Chromium · CDP 9222 · Xvfb/x11vnc · noVNC/WebSocket       │
└────────────────────────────────────────────────────────────┘
```

## 三个核心模块

| 模块 | 职责 | 关键技术 |
| --- | --- | --- |
| [`api`](./api/) | Agent 编排、工具调用、会话与事件、配置和存储 | FastAPI、Pydantic、Function Calling、Planner–ReAct、MCP、A2A、SQLAlchemy、PostgreSQL、Redis Streams、Playwright、COS |
| [`sandbox`](./sandbox/) | 隔离执行命令、文件操作并托管浏览器 | Docker、FastAPI、asyncio subprocess、Supervisor、Chromium、CDP、Xvfb、VNC、WebSocket |
| [`ui`](./ui/) | 将任务过程变成可交互、可观察的产品界面 | Next.js 16、React 19、TypeScript、Tailwind CSS 4、Radix UI、SSE、noVNC |

每个模块的实现细节和学习成果见各目录下的 `README.md`。

## 一次任务的数据流

1. 用户在 UI 创建会话、上传附件并发送任务，前端通过 REST 调用 API。
2. API 保存用户事件，为会话准备独立 Sandbox，并创建 `AgentTaskRunner` 与 Redis Stream 任务。
3. Planner Agent 根据需求输出结构化 `Plan`，产生 `title`、`message`、`plan` 事件。
4. ReAct Agent 执行当前步骤；模型返回 `tool_calls` 后，框架解析参数、调用工具，并把结果写回 Memory 继续推理。
5. 工具可在 Sandbox 操作 Shell/文件/浏览器，也可搜索、调用 MCP 工具或把子任务委派给 A2A Agent。
6. 每一步结果返回 Planner 更新后续计划；全部完成后 ReAct 汇总答案和产物。
7. 事件写入 Redis Streams 并持久化到 PostgreSQL；SSE 按事件 ID 推送，断线后可从游标续传。
8. UI 将事件归并为时间线，实时展示计划、步骤、工具状态、生成文件和浏览器画面。

## 技术栈

- **Agent 与模型**：OpenAI-compatible Async API、Chat Completions、Function Calling、JSON Schema、结构化输出、上下文压缩。
- **Agent 协议**：MCP Python SDK（stdio/SSE/Streamable HTTP）、A2A Agent Card 与 JSON-RPC。
- **后端**：Python 3.13、FastAPI、Pydantic 2、分层/端口适配器设计、asyncio、httpx。
- **数据与任务**：PostgreSQL、SQLAlchemy 2、Alembic、JSONB、Redis Streams、腾讯云 COS 适配器。
- **工具与隔离**：Docker SDK、会话级容器、Shell、文件系统、Bing 搜索、Playwright/CDP、Chromium。
- **前端**：Next.js 16 App Router、React 19、TypeScript、Tailwind CSS 4、Radix UI、SSE、noVNC。
- **工程化**：Docker Compose、uv、npm、ESLint、pytest、健康检查、配置脱敏和生命周期管理。

## 代码结构

```text
mooc-manus/
├── api/                         # Agent 核心与业务 API
│   ├── app/domain/              # 模型、仓库协议、Agent、Flow、Tools
│   ├── app/application/         # 会话、文件、设置、状态用例
│   ├── app/infrastructure/      # LLM、DB/Redis/COS/Sandbox 适配
│   ├── app/interfaces/          # FastAPI 路由、Schema、异常与依赖注入
│   └── alembic/                 # 数据库迁移
├── sandbox/                     # 隔离执行服务和浏览器桌面
├── ui/                          # Next.js Agent 工作台
├── docker-compose.yml           # PostgreSQL、Redis、Sandbox 编排
├── dev.sh                       # 本地一键开发启动
└── README.py                    # 可被 Python 导入的项目说明摘要
```

## 快速开始

前置条件：Docker + Docker Compose、Python/uv、Node.js/npm。

```bash
cp api/.env.example api/.env
cp ui/.env.example ui/.env.local
# 编辑 api/.env 与 api/config.yaml，配置模型、存储及可选 MCP/A2A
./dev.sh
```

- UI：<http://localhost:3000>
- OpenAPI：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/api/status>

分别启动与验证：

```bash
docker compose up -d postgres redis sandbox
cd api && uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

cd ../ui && npm install && npm run dev

# 验证
cd ../api && uv run pytest
cd ../ui && npm run lint && npx tsc --noEmit && npm run build
```

端到端验收的关键是会话页连续显示 `plan → step → tool → message → done`，刷新后历史事件仍可恢复，并能下载 Agent 生成的文件。

## 学习成果总结

这个项目让我完成了从“会调用大模型 API”到“能设计 Agent 系统”的跨越：理解模型如何通过 Tool Schema 获得行动能力，Planner–ReAct 如何控制长任务，MCP 和 A2A 如何扩展能力边界，沙箱如何限制执行风险，也理解了异步任务、事件持久化、实时 UI 和资源生命周期为什么同样是 Agent 工程的核心。

> 安全提示：不要提交真实 API Key、对象存储密钥、MCP Token、`api/.env` 或包含凭据的本地配置。
