# MoocManus 前端实现与项目跑通计划

## 1. 项目目标

本项目的最终目标不是只完成一套静态前端页面，而是实现一个可以完整运行、交互方式尽量接近 Manus 的通用 Agent 应用。

最终需要跑通以下完整链路：

```text
用户创建任务
  → 上传附件（可选）
  → 创建会话并发送消息
  → Agent 生成计划
  → 前端实时显示步骤和工具调用
  → Agent 返回结果和生成文件
  → 用户下载文件或继续追问
  → 刷新页面后恢复完整会话
```

前端只访问 `api` 服务，不直接访问 `sandbox`。`sandbox` 继续作为 Agent 的内部工具运行环境，由后端负责调用、管理和销毁。

## 2. Manus 风格产品形态

前端尽量模仿 Manus 的信息结构、操作流程和视觉体验，但不追求逐像素复制。重点复刻以下产品特征：

- 左侧是会话历史和“新建任务”入口。
- 中间是任务对话、Agent 执行过程和最终结果。
- 底部是始终可用的任务输入框与附件区域。
- 执行时实时展示计划、当前步骤、工具调用和任务状态。
- 工具过程默认简洁，用户可以按需展开查看搜索、浏览器、终端、文件等详情。
- Agent 生成的文件作为清晰的结果卡片展示，并支持下载。
- 页面刷新后能够从后端恢复任务进度和历史记录。
- 桌面端保持 Manus 式宽屏任务空间，移动端将左侧栏收进抽屉。

## 3. 当前项目情况

### 3.1 已有基础

- `ui` 已使用 Next.js 16、React 19、TypeScript、Tailwind CSS 4 和 shadcn/Base UI。
- 首页、会话页、侧栏、输入框、计划面板和设置弹窗已有静态骨架。
- 后端已有 Session、Plan、Step、Message 和 File 等领域模型。
- 后端已定义完整的 Agent 事件类型：`plan`、`title`、`step`、`message`、`tool`、`wait`、`error`、`done`。
- 后端已有 AgentTaskRunner、Redis Stream、PostgreSQL 会话仓库、文件存储和 Sandbox 调用实现。
- 已公开状态检查、文件和应用配置接口。

### 3.2 当前关键缺口

后端核心能力已经存在，但尚未提供前端完成任务链路所需要的会话和实时事件公开接口。目前路由只挂载了：

- `/api/status`
- `/api/files`
- `/api/app-config/*`

因此第一阶段需要先补齐 Session、Message、Cancel 和 SSE 接口，否则 UI 只能继续使用静态数据，无法真正运行 Agent。

## 4. 总体技术方案

### 4.1 前端技术选择

- 保留 Next.js App Router，不更换框架。
- 使用 TypeScript 定义与后端 Pydantic 模型对应的数据类型。
- 使用原生 `fetch` 封装 REST API。
- 使用 SSE 接收 Agent 实时事件；不优先使用 WebSocket，因为当前主要是后端向前端单向推送。
- 使用 Zustand 管理当前会话、事件流和运行状态。
- 使用 `react-markdown`、`remark-gfm` 渲染 Markdown、代码块和表格。
- 使用现有 shadcn/Base UI 组件完成弹窗、菜单、提示和响应式交互。

### 4.2 推荐目录结构

```text
ui/
├── app/
│   ├── page.tsx
│   └── sessions/[id]/page.tsx
├── components/
│   ├── chat/
│   │   ├── chat-input.tsx
│   │   ├── message-list.tsx
│   │   ├── message-item.tsx
│   │   ├── markdown-content.tsx
│   │   ├── tool-event-card.tsx
│   │   ├── plan-card.tsx
│   │   └── file-card.tsx
│   ├── layout/
│   │   ├── left-panel.tsx
│   │   └── session-header.tsx
│   └── settings/
│       ├── agent-settings.tsx
│       ├── llm-settings.tsx
│       ├── mcp-settings.tsx
│       └── a2a-settings.tsx
├── hooks/
│   ├── use-file-upload.ts
│   └── use-session-stream.ts
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   ├── files.ts
│   │   ├── sessions.ts
│   │   └── settings.ts
│   ├── events/
│   │   └── reducer.ts
│   └── types/
│       ├── api.ts
│       ├── event.ts
│       └── session.ts
└── stores/
    └── session-store.ts
```

## 5. 后端接口补全计划

### 5.1 会话接口

| 功能 | 方法与路径 | 说明 |
| --- | --- | --- |
| 获取会话列表 | `GET /api/sessions` | 左侧栏使用，按最近更新时间倒序 |
| 创建会话 | `POST /api/sessions` | 返回新 Session |
| 获取会话详情 | `GET /api/sessions/{session_id}` | 返回历史事件、文件和当前状态 |
| 删除会话 | `DELETE /api/sessions/{session_id}` | 删除会话并释放关联任务/Sandbox |
| 发送消息 | `POST /api/sessions/{session_id}/messages` | 支持文本和附件 ID |
| 停止任务 | `POST /api/sessions/{session_id}/cancel` | 取消正在运行的 Agent 任务 |
| 标记已读 | `POST /api/sessions/{session_id}/read` | 清空未读消息数 |

### 5.2 实时事件接口

新增：

```http
GET /api/sessions/{session_id}/events
Accept: text/event-stream
```

SSE 数据建议保持后端现有 Event 模型，不再发明第二套协议：

```text
id: redis-stream-id
event: tool
data: {"type":"tool","tool_call_id":"...","status":"calling",...}
```

接口需要支持：

- 心跳，避免代理层关闭空闲连接。
- 使用事件 ID 去重。
- 支持 `Last-Event-ID` 或查询参数恢复断开的事件流。
- 会话结束后发送 `done` 并关闭连接。
- 浏览器重连后不会重复渲染已经持久化的事件。

### 5.3 后端联调检查

在接入 UI 前验证：

- 创建 Session 能正确提交数据库事务。
- 第一条消息能创建 RedisStreamTask 并启动 AgentTaskRunner。
- 用户消息本身会写入 Session events，而不只是进入输入队列。
- Agent 输出事件同时写入 Redis Stream 和 PostgreSQL。
- `wait` 后可以发送追问并重新启动或继续任务。
- `cancel` 会发送 `done`、更新状态并释放 Sandbox。
- 文件上传、同步到 Sandbox、生成文件回传和下载链路可用。
- 服务异常时会产生用户可理解的 `error` 事件。

## 6. 前端实施阶段

### 阶段一：建立 API 和类型层

工作内容：

1. 增加 `.env.example`，定义 `NEXT_PUBLIC_API_BASE_URL`。
2. 定义 `ApiResponse<T>`、Session、File、Plan、Step 和 Event 联合类型。
3. 封装统一 API Client，处理 JSON、错误、超时和请求取消。
4. 实现 sessions、files、settings 请求模块。
5. 实现 Session Store 和事件 reducer。

事件 reducer 需要按照业务语义合并事件：

- 使用事件 `id` 去重。
- 相同 `tool_call_id` 的 `calling` 和 `called` 合并成一条工具记录。
- `plan` 创建或替换当前计划。
- `step` 更新计划中对应步骤的状态和结果。
- `title` 同时更新会话页标题和左侧会话列表。
- `message` 追加为用户或 Agent 消息。
- `wait`、`done`、`error` 更新任务运行状态。

完成标准：前端可以使用测试数据稳定重放一整套事件，并得到正确 UI 状态。

### 阶段二：首页与新建任务

改造首页和输入框，完成：

- Manus 风格欢迎区域和任务输入框。
- 文本输入自动增高。
- Enter 发送、Shift+Enter 换行。
- 多附件选择、上传、移除、进度和失败重试。
- 空消息且无附件时禁止发送。
- 首次发送时依次完成“上传附件 → 创建会话 → 发送消息 → 跳转会话页”。
- 支持新建任务快捷键。

完成标准：用户从首页发出任务后能进入真实 Session 页面，Agent 后端开始运行。

### 阶段三：会话页与实时事件

实现会话页核心能力：

- 请求并恢复会话历史。
- 连接 SSE 并实时消费事件。
- 显示用户消息、Agent 消息、计划、步骤、工具调用和错误。
- Agent 回复支持 Markdown、GFM 表格、代码块和链接。
- 新事件到达时自动滚动到底部。
- 用户主动向上滚动后暂停自动跟随，并显示“回到最新”按钮。
- SSE 断开时自动重连并显示轻量状态提示。
- 运行期间发送按钮切换为停止按钮。
- `waiting` 状态允许用户继续提供信息。
- Session 不存在时展示友好的 404 状态。

完成标准：无需刷新即可看到 Agent 从规划到完成的全过程；刷新后内容不丢失。

### 阶段四：Manus 风格工具过程展示

根据 `tool_name` 实现不同工具卡片：

- `search`：搜索关键词、结果标题、摘要和来源链接。
- `browser`：访问地址、运行状态和浏览器截图。
- `shell`：命令、执行状态和终端输出。
- `file`：文件路径、内容摘要和生成文件入口。
- `mcp`：服务名、函数名、参数和结果。
- `a2a`：远程 Agent、任务状态和结果。
- 未识别工具：通用 JSON/文本卡片，保证系统可以兼容新增工具。

展示原则：

- 默认只展示“正在做什么”和最终状态。
- 参数、控制台和原始结果默认折叠。
- 正在运行、成功、失败使用统一图标和颜色。
- 工具失败不能导致整个消息列表渲染失败。

完成标准：Agent 的每类内置工具都能以可理解的方式展示，而不是直接输出原始 JSON。

### 阶段五：计划与结果文件

计划面板：

- 显示计划标题、目标和完成进度。
- 展示 pending、running、completed、failed 四种状态。
- 当前步骤突出显示。
- 支持折叠与展开。
- 步骤结果和错误信息可以进一步展开。

文件结果：

- 消息附件和 Session 文件使用统一 FileCard。
- 图片可预览，其他文件显示类型、大小和文件名。
- Agent 生成文件提供明确的下载按钮。
- 下载通过 `/api/files/{file_id}/download` 完成。

完成标准：用户可以清晰看到 Agent 当前执行到哪一步，并能下载 Agent 的最终产物。

### 阶段六：会话侧栏

替换当前静态会话列表，实现：

- 加载真实会话列表。
- 显示标题、最新消息、时间、状态和未读数量。
- 当前 Session 高亮。
- 新事件到达后实时更新排序与摘要。
- 删除前二次确认。
- 新建任务入口。
- 加载骨架、空状态和失败重试。
- 移动端使用 Sheet/Drawer 展示侧栏。

完成标准：创建、切换、刷新和删除会话行为完整可用。

### 阶段七：设置中心接入

保留当前设置弹窗的整体结构，将静态表单接入真实接口：

- LLM 配置读取与保存。
- Agent 最大迭代次数、重试次数、搜索数量读取与保存。
- MCP Server 新增、删除、启用和禁用。
- A2A Agent 新增、删除、启用和禁用。
- 表单初始化、校验、提交中、成功和失败反馈。
- API Key 留空表示不修改，前端不回显已有密钥。

将当前大组件拆成独立设置模块，降低维护成本。

完成标准：所有现有 `/api/app-config/*` 接口都能通过 UI 操作。

### 阶段八：项目整体跑通与交付

补齐项目运行相关内容：

- 统一 API、UI、PostgreSQL、Redis、COS/对象存储和 Sandbox 的环境变量说明。
- 检查并补充 Docker Compose；如果项目已有部署方式，则在现有方式上完善。
- 增加根目录启动说明和最短启动命令。
- 提供开发模式与生产模式配置。
- 确保 Next.js 能访问 API，API 能访问 PostgreSQL、Redis、对象存储和 Sandbox。
- 增加服务健康检查和启动依赖。
- 检查 CORS、上传大小、SSE 代理缓冲和超时设置。
- 清理 UI 中所有假 Session、假文件、假计划和占位文字。

## 7. 页面与组件细节

### 7.1 首页

- 左侧保持历史会话栏。
- 中间使用大留白和简洁欢迎文案。
- 输入框是最突出元素。
- 推荐问题可以保留，但需要点击后自动填充或直接发送。
- 不显示任何假附件。

### 7.2 会话页

桌面端建议结构：

```text
┌──────────────┬────────────────────────────────────────┐
│ 会话历史     │ 标题 / 状态 / 文件                     │
│              ├────────────────────────────────────────┤
│ 新建任务     │ 用户消息                               │
│              │ Agent 计划                             │
│ Session A    │ 工具调用与步骤                         │
│ Session B    │ Agent 最终结果                         │
│ Session C    │                                        │
│              ├────────────────────────────────────────┤
│              │ 计划进度（可折叠）                     │
│              │ 附件 + 输入框 + 发送/停止              │
└──────────────┴────────────────────────────────────────┘
```

中间内容宽度继续保持适合阅读的约 768px，工具截图或复杂结果可以适当突破正文宽度。

### 7.3 任务状态

统一定义前端任务状态：

| 后端状态 | 前端表现 |
| --- | --- |
| `pending` | 等待用户发起任务 |
| `running` | 显示动态状态，发送按钮变为停止 |
| `waiting` | 提示 Agent 正在等待用户补充信息 |
| `completed` | 输入框恢复，可继续追问 |
| `error` 事件 | 显示错误卡片并允许重试或继续输入 |

## 8. 测试计划

### 8.1 后端接口测试

- Session 创建、查询、列表和删除。
- 消息发送和附件 ID 校验。
- SSE 事件顺序、断线恢复、去重和完成关闭。
- Agent cancel 和资源释放。
- 文件上传、同步、生成、下载。
- wait 后继续任务。

### 8.2 前端测试

- TypeScript 类型检查。
- ESLint。
- Next.js production build。
- Event reducer 单元测试。
- 文件上传失败和重试测试。
- SSE 重连和重复事件测试。
- Markdown 和超长工具输出测试。
- 桌面端和移动端布局测试。

### 8.3 端到端测试

至少覆盖以下场景：

1. 发送普通文本任务并得到回答。
2. 上传文件并让 Agent 处理。
3. Agent 使用搜索、浏览器、Shell 和文件工具。
4. Agent 生成文件并由用户下载。
5. 用户停止正在运行的任务。
6. Agent 等待输入后，用户继续回复。
7. 页面刷新后恢复历史和当前进度。
8. 创建多个会话、切换会话和删除会话。
9. 修改 LLM、Agent、MCP 和 A2A 配置。

## 9. 最终验收标准

满足以下条件才视为“项目跑通”：

- 所有核心页面不再依赖硬编码假数据。
- 用户能从首页创建真实任务。
- 文本与附件消息都能到达 Agent。
- 前端能实时显示完整 Agent 事件流。
- 计划、步骤和各种工具调用均有对应 UI。
- Agent 生成的文件可以展示和下载。
- 用户能停止任务、继续追问和响应 wait。
- 会话历史可查询、切换、刷新恢复和删除。
- 设置中心可以操作后端已有配置接口。
- API、UI、数据库、Redis、对象存储和 Sandbox 可以通过文档化命令启动。
- 后端测试、前端 lint、类型检查和 production build 通过。
- 至少一条包含工具调用和文件产出的真实端到端任务通过。

## 10. 推荐执行顺序

严格按照以下顺序实现，避免在静态 UI 上反复返工：

1. 补全并测试 Session、Message、Cancel、SSE 后端接口。
2. 修复真实任务链路中暴露的 Session、Redis Stream、事务和 Sandbox 问题。
3. 建立前端类型、API Client、Store 和事件 reducer。
4. 跑通无附件的单轮 Agent 任务。
5. 完成事件时间线、计划和工具卡片。
6. 跑通附件上传、Sandbox 同步、生成文件和下载。
7. 完成历史会话、继续追问、wait 和 cancel。
8. 接入 LLM、Agent、MCP、A2A 设置。
9. 完成响应式、异常恢复、测试和部署配置。
10. 使用真实模型执行端到端验收任务，并修复全部阻塞问题。

实现过程中优先保证数据链路和 Agent 运行状态正确，再逐步提高与 Manus 的视觉接近程度。任何视觉效果都不能以破坏事件恢复、错误处理或移动端可用性为代价。
