# 待办：拼写 / 命名清理清单

> 这是上一轮修复遗留的纯拼写/命名问题（内部一致、不影响运行，但应统一清理）。
> 行号是 2026-08-27 修复后的当前值，执行时以 `grep` 实际命中为准。
> 每个标识符类问题都已标注「跨文件同步」关系，改一处必须同步改引用处。

## A. 代码标识符拼写（真实方法名/变量名，改错会 ImportError/AttributeError）

### A1. `get_latest_plant` → `get_latest_plan`
- 定义：`app/domain/models/session.py:41`
- 引用：`app/domain/services/flows/planner_react.py:116`
- 跨文件同步：是（2 处）

### A2. `rool_back` → `roll_back`
- 定义：`app/domain/services/agents/base.py:161`
- 引用：`app/domain/services/flows/planner_react.py:99` 和 `:100`（`self.planner.rool_back` / `self.react.rool_back`）
- 跨文件同步：是（3 处）

### A3. `_session_rrpository` → `_session_repository`
- 定义/引用全在 `app/domain/services/flows/planner_react.py`：`:48`、`:88`、`:113`
- 跨文件同步：否（同一文件内 3 处，可用 replace_all）

### A4. `_aync_file_to_sandbox` → `_async_file_to_sandbox`
- 定义：`app/domain/services/agent_task_runner.py:96`
- 引用：同文件 `:129`
- 跨文件同步：否（同文件 2 处）

### A5. `browser_console_exex` → `browser_console_exec`
- `app/domain/services/tools/browser.py:214`（`@tool(name=...)`）和 `:224`（方法定义）
- ⚠️ 这是暴露给 LLM 的工具名，改名会改变模型调用契约，需确认前端/提示词无硬编码
- 跨文件同步：否（同文件 2 处）

### A6. `suggest_user_taskover` → `suggest_user_takeover`
- `app/domain/services/tools/message.py:49`（`@tool` 的 `parameters` 键）和 `:61`（方法参数）
- ⚠️ LLM 可见参数名，改名影响模型契约
- 跨文件同步：否（同文件 2 处）

### A7. `outpur` → `output`
- `app/infrastructure/external/task/redis_stream_task.py:25`：`f"task:outpur:{self._id}"`
- 仅 Redis stream 名，内部一致，改名不影响功能（旧流名会残留，可顺带 `clear()`）
- 跨文件同步：否（1 处）

## B. 纯文本 / 注释 / 提示词错别字（改字符串即可，不影响运行）

### B1. 系统提示词 `app/domain/services/prompts/system.py`
| 行 | 当前 | 应为 |
|---|---|---|
| 2 | `Agetn` | `Agent` |
| 12 | `软件开发意外的各类问题` | `软件开发以外的各类问题` |
| 29 | `Model Contex Protocol` | `Model Context Protocol` |
| 38 | `合并晚间时` | `合并文档时` |
| 55 | `课件返回的格式` | `可见元素返回的格式` |
| 101 | `把不要向用户交付戴白事项` | `不要向用户交付待办事项` |

### B2. 规划提示词 `app/domain/services/prompts/planner.py`
| 行 | 当前 | 应为 |
|---|---|---|
| 41 | `步骤表示符号` | `步骤标识符号` |
| 87 | `提娜佳` | `添加` |
| 104 | `步骤表示符` | `步骤标识符` |

### B3. 执行提示词 `app/domain/services/prompts/react.py`
| 行 | 当前 | 应为 |
|---|---|---|
| 21 | `而是直直接通过工具` | `而是直接通过工具` |
| 22 | `内容限制再一句话以内` | `内容限制在一句话以内` |
| 23 | `你打算使用上面工具` | `你打算使用什么工具` |
| 24 | `或者你通过工具完成了上面` | `或者你通过工具完成了什么` |

### B4. `跟新` → `更新`（大量注释/docstring/返回消息）
命中文件与行号：
- `app/application/services/app_config_service.py:188、192、210`
- `app/infrastructure/repositories/db_session_repository.py:72、108、126、160、183、199、216、217、233`
- `app/infrastructure/models/session.py:82`（`#跟新时间`）
- `app/interfaces/endpoints/app_config_routes.py:208`（`msg="跟新a2a服务器启用状态成功"`，这是**用户可见文案**）
- `app/domain/services/agents/planner.py:23、31、72、73`

### B5. 其它零散错别字
- `app/infrastructure/external/search/bing_search.py:24`：`gzip, deflare` → `gzip, deflate`
- `app/domain/services/tools/shell.py:90`：`雪茹进程的输入内容` → `写入进程的输入内容`
- `app/infrastructure/models/session.py:59`：`#时间列表` → `#事件列表`（events 字段的注释）
- `app/domain/external/sandbox.py:42`：`最加模型` → `追加模式`

## 验证方式（新 session 可执行）

```bash
# 代码标识符类，改完后确认无残留引用
grep -rn "get_latest_plant\|rool_back\|_session_rrpository\|_aync\|exex\|taskover\|outpur" app/

# 文本类，改完后确认无残留
grep -rn "跟新\|Agetn\|意外\|Contex\|晚间\|课件\|戴白\|雪茹\|提娜佳\|直直接\|上面工具\|完成了上面\|再一句话\|表示符\|最加模型\|时间列表\|deflare" app/

# 改完后验证可导入
python -c "import app.main"
```

## 建议执行顺序

1. 先做 A 类（真实标识符），每改一处同步 `grep` 确认引用处已同步、无残留，再 `python -c "import app.main"` 验证。
2. A5、A6 涉及 LLM 可见的契约名，改动前先确认没有外部/前端硬编码。
3. 再做 B 类（纯文案），B4 的 `跟新→更新` 可直接对上述文件 `replace_all`。
