# Sandbox 模块：Agent 的隔离执行环境

`sandbox` 是 MoocManus 的“手和工作台”。API 不直接在宿主机执行模型生成的命令，而是把 Shell、文件和浏览器操作交给独立 Docker 容器，通过受控 HTTP API 访问。

## 功能

- 异步执行 Shell 命令，返回退出码、标准输出和错误输出。
- 创建、读取、写入、替换、删除、搜索和列举文件，并限制路径逃逸。
- 通过 Supervisor 查询、启动、停止和重启容器内进程。
- 托管 Chromium，开放 CDP 端口供 API 的 Playwright 客户端操作。
- 使用 Xvfb 提供虚拟显示，以 x11vnc + websockify 输出 WebSocket VNC。
- 记录最后活动时间；长时间空闲后自动退出，配合 API 回收资源。

## 使用的技术

| 技术 | 作用 |
| --- | --- |
| Docker / Ubuntu 22.04 | 提供与宿主机隔离、可销毁和可重建的环境 |
| FastAPI + Pydantic | 提供类型化 Shell、File、Supervisor 控制接口 |
| asyncio subprocess | 非阻塞运行命令并收集 stdout/stderr/exit code |
| Supervisor | 管理 API、Chromium、Xvfb、x11vnc、websockify 进程 |
| Chromium + CDP | 提供真实浏览器和远程调试协议 |
| Xvfb + x11vnc | 在无物理显示器的容器中运行和观察 GUI |
| websockify / noVNC | 将 VNC TCP 流桥接为浏览器可用的 WebSocket |
| Python 3.10 / Node.js | 支持 Agent 生成并执行 Python、前端或脚本任务 |

## 内部结构

```text
app/
├── main.py                       # FastAPI 入口与生命周期
├── core/                         # 配置和活动时间中间件
├── interfaces/endpoints/         # Shell、File、Supervisor 接口
├── interfaces/schema/            # Pydantic 请求/响应 Schema
├── models/                       # 领域模型
└── services/                     # Shell、File、Supervisor 实现
```

```text
supervisord
├── Sandbox FastAPI :8080
├── Xvfb virtual display
├── Chromium :9222 (CDP)
├── x11vnc :5900
└── websockify :5901 → VNC WebSocket
```

## 与 API 的数据流

1. API 为会话创建独立容器并保存 `sandbox_id`。
2. Shell/File Tool 通过 Sandbox HTTP 接口执行动作。
3. Browser Tool 由 API 侧 Playwright 连接 Sandbox 的 CDP 地址。
4. UI 观察桌面时，以 noVNC 连接容器 WebSocket。
5. 会话删除或达到空闲 TTL 后销毁容器；后续追问可重建环境。

这种设计让模型获得明确工具接口，而不是 API 主机的无限制执行权。

## 运行

```bash
# 推荐：仓库根目录
docker compose up -d sandbox

# 独立开发
cp .env.example .env
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080
```

健康状态：<http://localhost:8080/api/supervisor/status>。

## 学习成果

我不仅实现了 Agent “会调用 Shell”，还处理了执行隔离、路径边界、异步子进程、浏览器远程控制、图形桌面转发、多进程托管和空闲回收。这让我理解了 Agent 工具能力越强，运行环境隔离和生命周期治理就越重要。
