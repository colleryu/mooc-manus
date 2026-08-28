# MoocManus

MoocManus 是一个采用 Manus 式任务交互的通用 Agent 项目。浏览器只访问 API；API 负责会话、事件流、模型、MCP/A2A、文件存储，并调用隔离的 Sandbox 执行工具。

## 服务结构

```text
Next.js UI (:3000)
       ↓ REST + SSE
FastAPI API (:8000)
       ├── PostgreSQL (:5432)
       ├── Redis (:6379)
       ├── 对象存储
       └── Sandbox (:8080 / CDP :9222)
```

## 首次配置

1. 复制 `api/.env.example` 为 `api/.env`，填写对象存储和 Sandbox 配置。
2. 检查 `api/config.yaml` 中的 LLM、MCP 和 A2A 配置。
3. 如需修改前端 API 地址，复制 `ui/.env.example` 为 `ui/.env.local`。
4. 安装 Docker、Docker Compose、uv 和 Node.js。

不要提交真实 API Key、对象存储密钥或 MCP Token。

## 一键开发启动

```bash
./dev.sh
```

脚本会启动 PostgreSQL、Redis、Sandbox，执行 Alembic 迁移，然后启动 API 和 UI。

- UI：http://localhost:3000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/status

按 `Ctrl+C` 停止 UI 和 API。基础容器可以使用下面的命令停止：

```bash
docker compose down
```

## 分别启动

```bash
docker compose up -d postgres redis sandbox

cd api
uv run alembic upgrade head
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

cd ../ui
npm install
npm run dev
```

## 验证

```bash
cd api
uv run pytest

cd ../ui
npm run lint
npx tsc --noEmit
npm run build -- --webpack
```

完整验收应从首页创建任务，并在会话页看到 `plan`、`step`、`tool`、`message` 和 `done` 实时事件。任务完成后刷新页面，历史事件仍应完整恢复。

详细实施与验收方案见 [plan.md](./plan.md)。
