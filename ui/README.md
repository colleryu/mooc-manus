# UI 模块：可观察的 Agent 工作台

`ui` 将复杂的 Agent 运行过程转换为用户能理解和干预的界面。它不只显示最终答案，还实时呈现计划、步骤、工具调用、等待状态、附件、生成文件和沙箱浏览器画面。

## 功能

- 首页创建任务，支持推荐问题、文本输入和多文件上传。
- 会话列表展示标题、最新消息、状态和未读数，支持删除与切换。
- 实时接收 `plan/step/tool/message/error/done` 事件并归并为时间线。
- 展示 Planner 计划和步骤状态，将工具调用挂载到对应步骤。
- 为 Bash、File、Search、Browser、MCP、A2A、Message 提供差异化展示。
- 支持 Markdown/GFM、附件、生成文件列表、预览和下载。
- 使用 noVNC 查看或操作 Sandbox 内的 Chromium 桌面。
- 可视化管理 LLM 参数、Agent 参数、MCP Server 和 A2A Agent。

## 使用的技术

| 技术 | 作用 |
| --- | --- |
| Next.js 16 App Router | 页面路由、布局与前端工程骨架 |
| React 19 + Hooks | 会话状态、事件订阅、预览面板和组件组合 |
| TypeScript | 为 API、SSE、Plan、Step、Tool 建立类型边界 |
| Tailwind CSS 4 | 响应式布局和视觉样式 |
| Radix UI | Dialog、Dropdown、Tooltip、ScrollArea、Switch 等基础组件 |
| Server-Sent Events | 实时接收 Agent 执行过程、心跳和终态 |
| noVNC | 在网页连接 Sandbox 的 VNC WebSocket |
| react-markdown + remark-gfm | 渲染模型 Markdown、表格和任务列表 |
| Sonner | 成功、失败和异常提示 |

## 前端数据流

```text
页面/组件
   ↓
SessionsProvider + useSessions / useSessionDetail
   ↓
类型化 API Client（REST + SSE）
   ↓
normalizeEvents → eventsToTimeline
   ↓
ChatMessage / PlanPanel / ToolUse / Preview / VNC
```

`useSessionDetail` 同时处理历史与实时数据：

1. REST 获取会话详情、历史事件和文件。
2. 任务为 `running` 时建立 SSE 连接。
3. 用事件 ID 去重并保存游标，断线或流结束后刷新状态。
4. 收到 `title/wait/done/error/message` 时同步本地会话状态。
5. `eventsToTimeline` 合并步骤状态，并将工具事件归属到对应步骤。

## 代码结构

```text
src/
├── app/                          # 首页、会话列表、动态详情路由
├── components/
│   ├── session-*.tsx             # 会话列表和详情工作区
│   ├── chat-*.tsx                # 消息展示与输入
│   ├── plan-panel.tsx            # 计划/步骤可视化
│   ├── tool-use/                 # 七类工具展示
│   ├── file-preview-panel.tsx    # 文件与产物预览
│   ├── vnc-*.tsx                 # Sandbox 桌面连接
│   ├── manus-settings.tsx        # LLM、Agent、MCP、A2A 设置
│   └── ui/                       # 可复用 UI 组件
├── hooks/                        # 会话列表、详情、SSE 生命周期
├── lib/api/                      # API Client、请求封装和类型
├── lib/session-events.ts         # 事件标准化与时间线归并
└── providers/                    # 跨页面会话状态
```

## 运行与验证

```bash
cp .env.example .env.local
npm install
npm run dev

npm run lint
npx tsc --noEmit
npm run build
```

默认访问 <http://localhost:3000>，API 地址由 `NEXT_PUBLIC_API_BASE_URL` 控制。

## 学习成果

这个模块让我实践了“Agent 可观察性”：用户需要看见系统规划什么、执行到哪一步、调用了什么能力、为何暂停以及生成了哪些产物。我完成了 REST 与 SSE 的状态协同、历史和增量事件归并、断线恢复、强类型事件模型、工具差异化展示和 VNC 实时桌面，把后台 Agent Runtime 转换成完整产品体验。
