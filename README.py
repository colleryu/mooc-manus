"""MoocManus 项目总览。

从零实现的 Manus 风格通用 AI Agent 学习项目。核心技术包括 OpenAI 兼容
Chat Completions、Function Calling、Planner-ReAct、MCP（stdio/SSE/
Streamable HTTP）、A2A、FastAPI、PostgreSQL、Redis Streams、Docker
Sandbox、Playwright/CDP，以及 Next.js + SSE + noVNC 可观察前端。

数据流：UI 通过 REST 提交任务；Planner-ReAct Flow 驱动 LLM 和工具；
任务事件经 Redis Streams 与 PostgreSQL 保存，再由 SSE 增量推送至 UI；
Shell、文件和浏览器动作在会话级 Docker Sandbox 内执行。

完整说明见 README.md；模块说明见 api/README.md、sandbox/README.md、
ui/README.md。
"""

PROJECT = {
    "name": "MoocManus",
    "modules": ["api", "sandbox", "ui"],
    "agent_patterns": ["Function Calling", "Planner-ReAct", "MCP", "A2A"],
    "event_flow": "REST -> Agent Task -> Redis Streams -> SSE -> UI",
}

if __name__ == "__main__":
    print(__doc__)
