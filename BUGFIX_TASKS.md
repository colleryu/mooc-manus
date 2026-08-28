# MoocManus 长任务稳定性 Bug 修复说明

> 本文档用于交给 Claude 或其他开发 Agent 直接实施修复。请先阅读完整文档，再按优先级逐项修改和验证。不要只处理截图中的红色错误提示；当前问题是前端事件归属、文件交付、错误传播、搜索质量、Agent 调度、上下文膨胀和日志配置共同造成的。

## 1. 修复目标

让 MoocManus 在执行“北京 7 日游规划”这类需要搜索、浏览器、MCP 和文件生成的长任务时具备以下特征：

1. 当前任务不会显示历史任务的错误。
2. Agent 声称交付的文件必须真实上传成功并可下载。
3. 文件或关键步骤失败时，任务不能仍显示“圆满完成”。
4. 搜索结果明显不相关时，工具不能返回伪成功。
5. 长任务的工具调用次数、执行时间和上下文大小可控。
6. SSE 临时断线后能够正确恢复，不丢事件、不串任务。
7. 前端不会因为大量工具事件和超大 JSON 结果明显卡顿。
8. 日志能够定位 session/task/tool，同时不泄露 API Key。

## 2. 当前已确认的现场数据

故障分析使用的会话：

```text
session_id: 6d9b7d8c-da90-4bb9-be2c-14ff52a00578
current task_id: 192637c6-1267-4a21-ba17-98e74470a5b9
```

“北京 7 日游景点与美食计划表”本轮任务实际执行情况：

```text
开始时间：2026-08-28 23:00:57
完成时间：2026-08-28 23:07:19
耗时：约 6 分 22 秒
最终 Session 状态：completed
最终事件：plan(completed) + done
```

截图中显示的错误：

```text
AgentTaskRunner出错：在经过30次尝试后任无法确认Sandbox Supervisor状态信息
```

该错误实际发生于：

```text
2026-08-28 22:48:47
```

它属于同一会话中的历史任务，不属于当前北京旅游任务。当前任务没有产生新的 `ErrorEvent`。

当前北京旅游任务的负载数据：

```text
当前任务事件数：127
整个会话事件数：150
整个会话事件 JSON：约 658 KB
Agent 记忆 JSON：约 320 KB
React 记忆消息数：135
React 工具消息数：63
本轮已完成工具调用：58
```

工具调用构成：

| 工具 | 次数 | 显式失败 |
| --- | ---: | ---: |
| 高德 `maps_text_search` | 19 | 0 |
| 高德 `maps_search_detail` | 15 | 0 |
| `browser_navigate` | 4 | 1 |
| 内置 `search_web` | 3 | 0，但结果严重不相关 |
| `browser_view` | 3 | 0 |
| `write_file` | 3 | 0 |
| 其他 MCP、文件、Shell、消息工具 | 11 | 0 |

文件交付数据：

```text
浏览器 called 事件：8
包含 screenshot/tool_content 的浏览器事件：0
Agent 最终声称生成的攻略文件：4
Session 实际 files：0
最终 assistant 消息实际 attachments：0
```

## 3. 已修复的 Sandbox 生命周期问题

以下修改已经存在，不要回退：

1. `DockerSandbox.get()` 不再缓存 `DockerSandbox` 实例。
2. 每轮 Agent 任务使用独立的 `httpx.AsyncClient` 连接同一个会话 Sandbox。
3. 用户取消当前任务时保留会话级 Sandbox，以便继续追问。

涉及文件：

- `api/app/infrastructure/external/sandbox/docker_sandbox.py`
- `api/app/infrastructure/external/task/redis_stream_task.py`
- `api/app/application/services/session_service.py`

现有回归测试：

- `api/tests/app/infrastructure/external/sandbox/test_docker_sandbox.py`
- `api/tests/app/infrastructure/external/task/test_redis_stream_task.py`

后续修改不得重新给 `DockerSandbox.get()` 增加实例级缓存，否则会再次出现第二轮任务拿到已关闭客户端的问题。

---

## 4. P0：修复历史错误被当成当前任务错误

### 4.1 现象

当前任务正常运行或已经完成，但底部红色提示显示以前任务的错误。

### 4.2 根因

`ui/app/sessions/[id]/page.tsx` 在 SSE 断线同步会话后执行类似逻辑：

```ts
const latestError = [...latest.events]
  .reverse()
  .find((event) => event.type === "error")
```

它搜索的是整个会话历史，没有判断错误是否属于当前 `task_id`。长任务期间只要 SSE 出现一次关闭或恢复，就可能把数分钟前甚至数小时前的历史错误重新显示在当前任务区域。

当前事件模型也没有 `task_id`，前端无法可靠判断事件属于哪一轮任务。

### 4.3 推荐修复

优先采用后端事件携带任务标识的方案，不要只依赖时间字符串猜测。

#### 后端

1. 给 `BaseEvent` 增加可选字段：

```py
task_id: Optional[str] = None
```

2. 在 `AgentTaskRunner._put_and_add_event()` 中，在序列化和写入 Redis/数据库前设置：

```py
event.task_id = task.id
```

3. `SessionService.send_message()` 创建用户 `MessageEvent` 时也设置当前新建 task 的 ID。
4. SSE 返回的所有实时事件必须包含 `task_id`。
5. 历史数据没有 `task_id` 时允许解析，保持向后兼容。

#### 前端

1. 在 TypeScript 的 `BaseEvent` 中增加：

```ts
task_id?: string | null
```

2. 当前 SSE 只处理或突出显示 `event.task_id === session.task_id` 的终态错误。
3. 断线后重新拉取 Session 时：
   - 当前 task 有 `error`：展示该错误。
   - Session 仍为 `running` 且没有当前 task 的错误：展示“连接恢复中”，然后重连。
   - Session 已 `completed` 且有 `done`：清空连接错误。
   - 不得从整个历史中直接取最后一个 ErrorEvent。
4. `send()` 开始新任务时清空上一轮的临时错误状态。
5. 历史 ErrorEvent 可以保留在历史消息流中，但不能显示为当前任务的固定底部错误条。

### 4.4 涉及文件

- `api/app/domain/models/event.py`
- `api/app/domain/services/agent_task_runner.py`
- `api/app/application/services/session_service.py`
- `api/app/interfaces/endpoints/session_routes.py`
- `ui/lib/types/api.ts`
- `ui/app/sessions/[id]/page.tsx`
- `ui/lib/events/reducer.ts`

### 4.5 验收标准

1. 会话先产生一次错误，再发送一个成功任务，成功任务执行期间不显示旧错误。
2. SSE 中途断开再恢复，不显示其他 task 的 ErrorEvent。
3. 当前 task 真正失败时，显示后端返回的具体错误。
4. 页面刷新后仍能正确识别最新任务的终态。

### 4.6 必须补充的测试

- 后端：事件写入 Redis 和 Session 时包含正确 `task_id`。
- 前端 reducer/辅助函数：只选择当前 task 的错误。
- SSE 集成测试：旧 error + 新 task + 新 done 的事件序列不会串台。

---

## 5. P0：修复生成文件和浏览器截图上传失败

### 5.1 现象

Agent 声称生成了以下文件：

```text
/home/ubuntu/beijing_travel_guide.md
/home/ubuntu/beijing_attractions.md
/home/ubuntu/beijing_food.md
/home/ubuntu/beijing_7day_plan.md
```

但 Session 中 `files=[]`，最终消息 `attachments=[]`，前端无法下载。

浏览器工具调用也没有任何截图内容。

### 5.2 后台错误

```text
pydantic_core.ValidationError: 1 validation error for File
size
  Input should be a valid integer
  input_value=None
```

### 5.3 根因

`AgentTaskRunner` 使用 `BytesIO` 创建内部 `UploadFile`：

```py
upload_file = UploadFile(
    file=file_data,
    filename=filename,
)
```

这种内部构造方式不会自动填充 `upload_file.size`。随后 `CosFileStorage.upload_file()` 使用：

```py
File(size=upload_file.size)
```

而领域模型要求 `size: int`，因此校验失败。

更严重的是，当前流程先调用 COS `put_object`，之后才构造 `File`。因此可能出现：

```text
COS 已上传对象
→ File 模型校验失败
→ 数据库没有记录
→ Session 没有附件
→ COS 留下孤儿对象
```

### 5.4 推荐修复

#### 正确计算文件大小

在上传前统一计算 size，不能假设 `UploadFile.size` 一定存在。

对于可 seek 的文件对象：

```py
current = upload_file.file.tell()
upload_file.file.seek(0, 2)
size = upload_file.file.tell()
upload_file.file.seek(current)
```

上传前应确保文件指针位于正确位置，通常需要 `seek(0)`。

也可以在内部创建 `UploadFile` 时显式传入 `size`，但 `CosFileStorage` 仍应保留兜底计算，避免其他调用方再次传入 `None`。

#### 调整上传原子性

推荐顺序：

1. 计算并校验 filename、extension、mime_type、size。
2. 先构造并验证 `File` 模型。
3. 上传 COS。
4. 保存数据库记录。
5. 保存数据库失败时，尝试删除刚上传的 COS 对象作为补偿。

#### 替换旧附件时避免先删后传

`_sync_file_to_storage()` 当前会先移除旧记录，再上传新文件。应改为：

1. 新文件上传并保存成功。
2. Session 指向新文件。
3. 最后删除旧记录和旧 COS 对象。

否则新上传失败时会把原本可用的附件记录也删掉。

#### 区分必要附件和可选截图

- Agent 最终声明的 attachments 属于任务交付物：上传失败必须让任务进入失败或部分失败状态，不能静默丢弃。
- 浏览器截图属于增强展示：上传失败可以降级为无截图，但必须记录结构化 warning，不能影响浏览器工具本身的成功结果。

### 5.5 涉及文件

- `api/app/domain/services/agent_task_runner.py`
- `api/app/infrastructure/external/file_storage/cos_file_storage.py`
- `api/app/domain/models/file.py`
- `api/app/infrastructure/storage/cos.py`
- `api/app/infrastructure/repositories/db_file_repository.py`

### 5.6 验收标准

1. Agent 生成 4 个 Markdown 文件后，Session `files` 中存在 4 条记录。
2. 最终 MessageEvent 的 `attachments` 包含 4 个可下载文件。
3. 下载接口返回的内容与 Sandbox 文件内容一致。
4. 浏览器截图上传成功时，ToolEvent 包含截图文件 ID。
5. COS 上传或 DB 保存失败时，不产生不可追踪的孤儿对象。
6. 必要交付文件上传失败时，前端必须看到明确失败状态。

### 5.7 必须补充的测试

- `BytesIO` 且 `UploadFile.size=None` 时能够正确计算大小。
- 上传前后文件指针位置正确，COS 收到完整内容。
- COS 成功、DB 失败时触发补偿删除。
- 替换旧附件失败时旧附件仍保留。
- 多附件中一个失败时，返回明确的部分失败信息，不伪装全部成功。
- 浏览器截图失败时工具仍可返回，但包含可观测 warning。

---

## 6. P0：修复异常被吞掉、任务状态伪成功

### 6.1 现象

文件同步抛出异常，但最终页面仍显示：

```text
任务已圆满完成
```

计划状态也是 `completed`。

### 6.2 根因

#### 文件同步异常被捕获后只写日志

以下方法会捕获异常但不继续抛出：

- `AgentTaskRunner._sync_file_to_storage()`
- `AgentTaskRunner._sync_message_attachments_to_storage()`
- `AgentTaskRunner._handle_tool_event()`

因此主任务不知道附件已经交付失败。

#### Step 失败状态可能被覆盖

`ReActAgent.execute_step()` 收到 `ErrorEvent` 时会把 Step 设为 `FAILED`，但方法结束前又无条件执行：

```py
step.status = ExecutionStatus.COMPLETED
```

这可能把失败状态重新覆盖为成功。

#### Session 缺少明确 failed 状态

当前异常路径通常把 Session 更新为 `completed`，只能依靠 ErrorEvent 猜测任务是否失败。

### 6.3 推荐修复

1. 为 `SessionStatus` 增加 `FAILED`，同时更新前端联合类型和状态展示。
2. `AgentTaskRunner` 捕获顶层异常时更新为 `FAILED`，不要更新为 `COMPLETED`。
3. 文件交付失败应抛出明确的领域异常，例如 `ArtifactDeliveryError`。
4. Step 收到 ErrorEvent 后立即 `return`，不得在末尾覆盖成 completed。
5. Step 最终成功必须同时满足：
   - 执行 Agent 返回结构合法；
   - `success=true`；
   - 所有必要附件交付成功。
6. Plan 中任一步骤失败时，Plan 应为 `failed` 或进入明确的重试/降级流程。
7. 最终总结不得使用“圆满完成”等成功文案，除非任务状态和交付物均验证成功。

### 6.4 涉及文件

- `api/app/domain/models/session.py`
- `api/app/domain/models/plan.py`
- `api/app/domain/services/agents/react.py`
- `api/app/domain/services/agent_task_runner.py`
- `api/app/domain/services/flows/planner_react.py`
- `ui/lib/types/api.ts`
- `ui/components/session-header.tsx`
- `ui/components/plan-panel.tsx`

### 6.5 验收标准

1. 附件交付失败时 Session 状态为 `failed` 或明确的 `partial_failed`，不能是普通 completed。
2. Step 失败后不会被覆盖为 completed。
3. 前端显示可理解的失败原因和可重试入口。
4. 成功任务必须满足附件记录与实际交付一致。

---

## 7. P1：修复内置 Bing 搜索返回无关结果但标记成功

### 7.1 现场结果

查询：

```text
北京必去景点 故宫 天坛 颐和园 长城 开放时间 门票价格
```

返回：

```text
b站三连是什么意思
合伙人入驻平台_百度知道
哔哩哔哩客服人工电话
```

查询：

```text
颐和园门票价格 旺季 淡季 联票
```

返回：

```text
MSDN系统库
Windows系统下载网站
MSDN原版Office下载
```

工具仍然返回 `success=true`。

### 7.2 根因

`BingSearchEngine` 直接抓取和解析 Bing HTML：

- HTML 结构和反爬返回不稳定。
- 没有检测验证码、异常页面、地区污染或重定向页面。
- 没有对标题、摘要与查询做最基本的相关性判断。
- 只要成功解析出 `li.b_algo` 就视为成功。
- 当前 `Accept-Language` 偏英文，不适合中文搜索。

### 7.3 推荐修复

1. 如果 Jina 搜索 MCP 已启用，复杂事实检索优先使用 Jina；内置 Bing 作为降级方案。
2. 内置搜索至少增加：
   - 查询关键词与标题/摘要的覆盖率检查；
   - 空 URL、重复 URL、明显导航/下载站结果过滤；
   - 异常 HTML、验证码和反爬页面识别；
   - 结果全部不相关时返回 `success=false`；
   - 中文查询使用合适的语言和地区参数。
3. 不建议仅靠硬编码域名黑名单解决，应使用可解释的相关性规则或轻量重排。
4. 使用 `AgentConfig.max_search_results` 真正限制结果数量。
5. ToolResult 中增加 provider、原始结果数、过滤后结果数和失败原因，便于日志分析。

### 7.4 涉及文件

- `api/app/infrastructure/external/search/bing_search.py`
- `api/app/domain/services/tools/search.py`
- `api/app/domain/models/search.py`
- Agent 工具选择 Prompt

### 7.5 验收标准

1. 上述两个北京旅游查询不再返回 B 站、MSDN 等完全无关结果。
2. 无有效结果时返回明确失败，不返回空的伪成功。
3. 搜索结果包含 provider 和过滤统计。
4. 使用固定 HTML fixture 编写解析回归测试，不依赖真实网络才能通过单元测试。

---

## 8. P1：控制工具调用次数与长任务耗时

### 8.1 现状

`AgentConfig.max_iterations=100`。

`BaseAgent._invoke_llm()` 会执行：

```py
filtered_message["tool_calls"] = message.get("tool_calls")[:1]
```

也就是强制每轮只保留一个工具调用。本轮 34 次高德 POI 查询全部串行执行，导致总耗时超过 6 分钟。

### 8.2 风险

- 任意一个外部服务慢 5～30 秒，整体耗时都会线性增加。
- 长时间 SSE 更容易遇到网络切换、浏览器休眠或代理超时。
- 每个工具结果都会再次传给 LLM，Token 和费用快速增长。
- `max_iterations=100` 允许模型陷入很长的工具循环。
- Planner 创建了 4 个步骤，但 React 在第一个步骤中完成了几乎整个任务，计划粒度没有被遵守。

### 8.3 推荐修复

#### 工具并行能力

不要简单并行所有工具。给工具增加能力声明，例如：

```py
parallel_safe: bool
stateful: bool
```

建议：

- 搜索、独立 MCP POI 查询：允许并行。
- Browser：同一页面会话内保持串行。
- Shell：同一 shell session 内保持串行。
- File 写入：涉及同一路径时保持串行。

保留 LLM 返回的多个 tool calls，对 `parallel_safe` 的调用使用 `asyncio.gather()`，其他调用按顺序执行。

#### 增加执行预算

至少增加以下配置：

```text
max_iterations_per_step
max_tool_calls_per_step
max_total_tool_calls
task_timeout_seconds
tool_timeout_seconds
max_concurrent_tools
```

建议默认值不要直接照搬，先结合现有任务测试确定；初始可从单步骤 20～30 次迭代、并发 3～5 个只读工具开始。

#### 约束步骤边界

执行 Prompt 中明确要求：

- 只完成当前 step 描述范围内的工作。
- 不提前执行后续步骤。
- 达到预算时返回已有结果和未完成原因。

Planner 更新计划时不得因为第一步做得过多而无提示删除全部后续步骤。

### 8.4 涉及文件

- `api/app/domain/models/app_config.py`
- `api/app/domain/services/agents/base.py`
- `api/app/domain/services/agents/react.py`
- `api/app/domain/services/flows/planner_react.py`
- `api/app/domain/services/tools/base.py`
- `api/app/domain/services/prompts/react.py`

### 8.5 验收标准

1. 多个独立高德查询可以受控并发执行。
2. Browser/Shell 等有状态工具不会被错误并发。
3. 超出预算时产生明确 ErrorEvent/失败状态，不无限循环。
4. 相同北京旅游任务的工具调用次数和总耗时明显下降。
5. 当前 step 不再无边界地完成整个计划。

---

## 9. P1：控制 Agent 记忆和 Session 事件膨胀

### 9.1 现状

当前 `Memory.compact()` 只把以下工具结果替换成 `(remove)`：

```text
browser_view
browser_navigate
```

搜索、MCP、文件和 Shell 的大结果仍然完整保存在 React 记忆中。

当前会话已经达到：

```text
React messages: 135
React tool messages: 63
React memory: 约 277 KB
Planner memory: 约 44 KB
```

继续追问时，这些历史工具结果会重复发送给 LLM。

### 9.2 推荐修复

1. 每个 Step 完成后，将原始工具结果压缩为结构化摘要。
2. 原始结果保留在事件/外部存储中，LLM 记忆只保留：
   - 工具名称；
   - 查询参数摘要；
   - 成功/失败；
   - 关键结果；
   - 可追溯的 event ID。
3. 对 MCP/Search/File/Shell 结果设置最大字符数。
4. 新任务开始前，将上一任务压缩为用户请求、最终结果、附件和错误的摘要，不携带全部工具轨迹。
5. Planner 与 React 记忆分别设置大小上限，并在超限前压缩，而不是只在 Step 完成后处理。
6. 不要破坏 DeepSeek thinking/tool-call 所要求的消息顺序；压缩只能发生在已经闭合的工具调用链上。

### 9.3 涉及文件

- `api/app/domain/models/memory.py`
- `api/app/domain/services/agents/base.py`
- `api/app/domain/services/flows/planner_react.py`
- Session memory repository

### 9.4 验收标准

1. 完成 50 次工具调用后，LLM 记忆不会线性保留全部原始结果。
2. 新一轮追问仍能理解上一轮结果，但不会携带全部搜索页面正文。
3. 压缩后工具调用消息顺序仍符合 LLM API 要求。
4. 提供记忆字节数或 Token 估算日志指标。

---

## 10. P1：增强 SSE 长任务恢复能力

### 10.1 当前风险

- 任务可能持续数分钟。
- 浏览器标签页可能休眠。
- 反向代理可能关闭空闲连接。
- 前端当前把部分连接关闭直接转换成固定错误提示。
- 事件没有 task ID 时，重连后容易混入历史终态。

### 10.2 推荐修复

1. 保留服务端每 15 秒 heartbeat。
2. SSE 客户端记录最新 `Last-Event-ID`，重连时从该位置继续。
3. 前端区分：
   - `CONNECTING`：正在自动重连，不立即报错；
   - `CLOSED` 且 Session 仍 running：主动重建 EventSource；
   - 收到当前 task 的 error/done/wait：正常关闭。
4. 重连时必须校验 `task_id`。
5. 服务端任务已从内存 registry 移除时，应根据数据库中的 Session 状态和终态事件返回准确结果，而不只是无条件构造 done。
6. 设置有限次数、带退避的重连；达到上限后仍可通过 Session 轮询恢复最终状态。

### 10.3 涉及文件

- `api/app/interfaces/endpoints/session_routes.py`
- `api/app/infrastructure/external/task/redis_stream_task.py`
- `ui/app/sessions/[id]/page.tsx`
- `ui/lib/api/sessions.ts`

### 10.4 验收标准

1. 执行任务时主动断开 SSE，再恢复后事件不丢失、不重复。
2. 重连不会显示历史 ErrorEvent。
3. 任务正常完成后前端收到 done 并停止重连。
4. API 进程重启后，前端可以从 Session 快照恢复任务终态。

---

## 11. P2：优化前端大量工具事件渲染

### 11.1 现状

`MessageList` 会渲染会话内全部 message、tool、error、wait 事件。当前会话已有 150 个事件，ToolCard 展开后直接执行：

```ts
JSON.stringify(event.tool_content, null, 2)
```

工具结果很大时会创建大量 DOM 文本，影响滚动和响应速度。

### 11.2 推荐修复

1. 默认只展开当前或最近的工具事件。
2. 历史工具事件按 Step 分组折叠。
3. 原始 JSON 设置预览长度，例如 20～50 KB，超出部分提示下载或查看详情。
4. 大列表使用分页、窗口化或“加载更早事件”。
5. PlanPanel 只展示当前 task 的最新 PlanEvent，避免历史计划干扰。
6. ErrorEvent 明确显示所属任务和发生时间。

### 11.3 涉及文件

- `ui/components/message-list.tsx`
- `ui/components/plan-panel.tsx`
- `ui/lib/events/reducer.ts`
- `ui/app/sessions/[id]/page.tsx`

### 11.4 验收标准

1. 500 个事件的会话仍能顺畅滚动。
2. 超大工具结果不会一次性渲染完整 JSON。
3. 当前计划和历史计划不会混淆。

---

## 12. P1：降低日志量并隐藏敏感信息

### 12.1 现状

一次约 6 分钟的任务产生了约 15 MB 调试输出，主要包括：

- SQLAlchemy 完整 SQL 和参数；
- MCP 初始化与完整工具 Schema；
- HTTP Core DEBUG；
- 完整工具结果；
- MCP URL 查询参数。

高德 MCP Key 当前放在 URL query 中，可能直接进入日志。

### 12.2 推荐修复

1. 默认运行级别改为 `INFO`。
2. 关闭或降低以下 logger：
   - `sqlalchemy.engine`
   - `httpcore`
   - `httpx/httpx2`
   - `mcp.client`
3. 添加统一日志脱敏器，至少处理：
   - `key`
   - `api_key`
   - `token`
   - `authorization`
   - Cookie
4. 不记录完整工具 Schema 和大结果，只记录名称、耗时、结果大小和 success。
5. 每条 Agent/Tool 日志增加：

```text
session_id
task_id
step_id
tool_call_id
function_name
duration_ms
success
```

6. 为每个工具设置慢调用日志阈值。

### 12.3 验收标准

1. 同类任务日志量显著下降。
2. 日志中搜索不到真实 API Key。
3. 仍然可以使用 session_id/task_id 快速还原一次任务时间线。

---

## 13. 建议实施顺序

请按以下顺序实施，避免大范围并行修改导致问题难以定位。

### 第一阶段：正确性

1. 当前 task 与历史 ErrorEvent 隔离。
2. 文件 size、COS 原子性和附件交付修复。
3. Step/Plan/Session 失败状态传播修复。
4. 为以上问题补单元测试和集成测试。

### 第二阶段：稳定性

1. SSE 重连与 task_id 校验。
2. 工具调用预算与超时。
3. 只读工具受控并发。
4. Agent 记忆压缩。

### 第三阶段：质量与性能

1. Bing 搜索质量校验和 Provider 降级策略。
2. 前端事件分组、截断和虚拟化。
3. 日志降噪、脱敏与结构化指标。

## 14. 最低回归测试清单

### 后端

运行：

```bash
cd api
uv run pytest
```

必须新增并覆盖：

1. 同一会话连续两轮任务，第二轮不会复用已关闭 Sandbox 客户端。
2. 每个事件带正确 task_id。
3. 旧 ErrorEvent 不影响新 task。
4. BytesIO 上传能得到正确 size。
5. 四个 Markdown 附件均写入数据库并可下载。
6. COS/DB 任一失败时状态一致且无孤儿记录。
7. ErrorEvent 不会被覆盖为 completed。
8. 搜索不相关结果不会被标记为成功。
9. 达到工具预算或任务超时时正确失败。
10. 记忆压缩后仍符合 LLM 工具消息顺序。

### 前端

运行：

```bash
cd ui
npm run lint
npm run build
```

建议补充前端测试工具，并覆盖：

1. 历史 error + 当前 running task。
2. 当前 task error。
3. SSE 断开、重连、done。
4. 500 个历史事件的渲染。
5. 大工具结果截断。
6. 附件卡片下载链接。

### 真实链路测试

至少执行以下场景：

1. 创建新会话，发送简单消息，等待 done。
2. 在同一会话继续发送第二条消息，确认 Sandbox 可用。
3. 在同一会话先制造一次失败，再运行成功任务，确认不显示旧错误。
4. 执行北京 7 日游任务，确认：
   - 搜索结果相关；
   - 有持续进度；
   - SSE 可恢复；
   - 最终文件真实存在；
   - 所有附件可下载；
   - Session/Plan/Step 状态一致。

## 15. 完成定义

只有同时满足以下条件才算本轮 Bug 修复完成：

- 当前任务不再显示历史错误。
- 复杂任务生成的附件真实可下载。
- 失败不会被包装成成功。
- 搜索明显不相关时能够识别并降级。
- 长任务有调用预算、超时和可靠重连。
- 后续追问不会携带无限增长的原始工具上下文。
- 前端在大量事件下仍可用。
- 日志不包含密钥，并能按 session/task 定位问题。
- 后端完整测试、前端 lint/build 和真实连续对话测试全部通过。

## 16. 给实现 Agent 的约束

1. 修改前先检查工作区现有改动，不要覆盖已经完成的 Sandbox 生命周期修复。
2. 优先做小范围、可测试的修改，不要一次重写整个 Agent 架构。
3. 不要通过隐藏错误提示来“修复”问题；必须修复事件归属和状态传播。
4. 不要通过把 `File.size` 改成可选类型掩盖文件大小缺失；必须正确计算真实大小。
5. 不要只增加更长的 timeout；需要减少串行调用并增加预算。
6. 不要简单删除历史事件或记忆；应保留可追溯信息，同时给 LLM 和前端使用摘要。
7. 涉及密钥的日志必须脱敏，提交说明中不得粘贴真实 Key。
8. 每完成一个阶段都运行对应测试，并记录真实验证结果。

