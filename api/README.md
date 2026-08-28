我已经把项目代码完整读了一遍（从 main.py 入口到 domain/infrastructure 各层，以及 prompts、alembic、工具集、浏览器、沙箱、任务队列）。下面是发现的 bug，按严重程度排序，都没有改动任何代码。

---
一、致命：核心路径构造/启动即崩溃

1. ShellTool.__init__ 自赋值 — app/domain/services/tools/shell.py:16
self.sanbox = self.sanbox
1. RHS 访问不存在的 self.sanbox → AttributeErinit__ 会构造

  Thought for 3s, searched for 1 pattern, read 2 files

README 为空。让我并行阅读核心文件：入口、配置、以及各层的实现。

  Thought for 6m 34s, read 91 files, ran 3 shell commands

我已经把项目代码完整读了一遍（从 main.py 入口到 domain/infrastructure 各层，以及
prompts、alembic、工具集、浏览器、沙箱、任务 重程度排序，都没有改动任何代码。

---
一、致命：核心路径构造/启动即崩溃
                                                                                        1. ShellTool.__init__ 自赋值 — app/domain/ser
self.sanbox = self.sanbox
1. RHS 访问不存在的 self.sanbox → AttributeError。而且 PlannerReActFlow.__init__ 会构造 ShellTool(sandbox=sandbox)（flows/planner_rea流程一构建就崩。参数名还拼错了（sanbox/sandbox）。
2. DBSessionRepository.__init__ 自赋值 — app/infrastructure/repositories/db_session_repository.py:23
self.db_session = self.db_session
2. 同上，构造即 AttributeError，应改为 self.db_session = dbsession。
3. SearchTool 完全不可用 — app/domain/services/tools/search.py
  - __init__(self) 不接收 search_engine 参数 SearchTool(search_engine=...) → TypeError。
  - 没调用 super().__init__()，_tool_cache 未初始化，get_tools() 会 AttributeError。
  - search_web 调用了不存在的 self.search_eng）。
4. MCPTool 无法被 Agent 调用 — app/domain/services/tools/mcp.py:359
重写的是 has_tools（复数），但 BaseAgent._get，agents/base.py:66）。MCP 工具永远匹配不到 →ValueError: 未知工具。
5. RedisStreamTask.invoke 逻辑错乱 — app/infrastructure/external/task/redis_stream_task.py:67-88
async def invoke(self):
    if self.done:
        self._execute_task = asyncio.create_task(self._execute_task())
  - 把创建的 Task 赋值给了方法名 _execute_task（覆盖了方法本身），而 done 属性读的是 _execution_task（永远 None→True）。
  - cancel() 里 self._execution_task.cancel()rror。
  - 另外多处 async 函数没
await：self._on_task_done()（:64）、self._cle 、_task_runner.on_done（:48），都会产生未await 的协程，清理逻辑实际不执行。
6. DockerSandbox.ensure_sandbox 把方法当字典 /sandbox/docker_sandbox.py:215
tool_result = ToolResult.from_sandbox(**response.json)   # 少了 ()
6. response.json 是方法对象，** 解包非 mapping → TypeError，沙箱永远无法确认就绪。
7. DockerSandbox IP 解析没 await — docker_san :183（get）
_get_container_ip/_resolve_hostname_to_ip 都是 async def，却直接 ip = cls._get_container_ip(container) 没 await，得到的是协程对象，拼进 f"http://{ip}:8080"。
8. PlaywrightBrowser 把 scroll_up 拼成 scrool_up — playwright_borwser.py:409
协议与 BrowserTool.browser_scroll_up 调的是 browser.scroll_up(...)，实际方法叫 scrool_up → AttributeError。
9. AgentTaskRunner._pop_event 返回类而非实例
return Event      # 应为 return event
9. 调用方 invoke 里 isinstance(event, Message.attachments 会 AttributeError。

---
二、高危：核心 Agent 流程运行期错误

10. BaseAgent._add_to_memory 把列表当单条消息 append — agents/base.py:148
self._memory.add_message(messages)，但 messages 是 List[Dict]，add_message 会把它整体塞进记忆，get_messages() 返回
[system, [列表]] → 发给 LLM 时结构错误。应调
11. BaseAgent.invoke 的 for/else 挂错位置 — agents/base.py:259
else: 挂在内层 for tool_call 上（该循环无 break），所以每执行一次工具都会 yield 一条 ErrorEvent("超过最大迭代次数")，本意应是外层循环耗尽时提示。
12. BaseAgent._invoke_llm 重试耗尽后无返回 — agents/base.py:80-116
所有重试都异常后循环直接结束、返回 None，invo") → AttributeError。
13. PlannerAgent.update_plan 查找“第一个未完成步骤”的循环恒返回 0 — agents/planner.py:94-97
for idx, step in enumerate(plan.steps):
    first_pending_index = idx
    break          # 第一次就 break
13. 结果 plan.steps[:0] 为空，等于丢弃所有已完成步骤、用新步骤整体覆盖。
14. ReActAgent.summarize 字段名写错 — agents/react.py:116
MessageEvent(..., attachment=attachments)，模c 默认忽略未知字段 → 附件被静默丢弃。
15. SessionModel.created_at 误加 onupdate — infrastructure/models/session.py:87
created_at 上挂了 onupdate=datetime.now，每次更新会话都会把创建时间一起改掉；应该是 updated_at 才有 onupdate。
16. Session.latest_message_at 默认值是元组 — domain/models/session.py:32
latest_message_at: Optional[datetime] = None,   # 末尾逗号 → 默认值是 (None,)                                 16. 已验证 Session().latest_message_at == (No,) 塞进 DateTime 列，出错。
17. JSONB 用 + 拼接（Postgres 不合法） — db_session_repository.py:113 / 131 / 263                             events = coalesce(...) + cast([...], JSONB)  没有此运算符，add_event/add_file/save_memory会直接 SQL 报错；应使用 ||。                                                                                  18. get_file_by_path 遍历的是 ORM 模型 — db_s
files = result.scalar_one_or_none() 拿到的是 SessionModel，for file in files: 遍历模型对象 → TypeError；应遍历record.files。
19. decrement_unread_message_count 的 greatest 只有单参数 — db_session_repository.py:238-240
func.greatest(coalesce(...)-1) 单参数不会钳制到 0，未读数可减成负数；应为 greatest(coalesce(...)-1, 0)。      20. AgentTaskRunner._handle_tool_event 把 Toorunner.py:228
file_read_result.get("content","")，ToolResult 是 pydantic 模型没有 .get → AttributeError。
21. AgentTaskRunner._sync_file_to_storage 参数错 + 空引用 — agent_task_runner.py:151/163                      remove_file(session_id, file.filepath)（该函 为 None 时 file.filepath = filepath 会崩。
22. 浏览器 JS 大量 inneText 拼写错误 — playwright_browser_fun.py（39/101/122/142/153 等）
innerText 被写成 inneText，文本/label 提取全部失效；select: selector 引用了未定义的                           selector（playwright_browser_fun.py:180，.js xt}。
23. PlaywrightBrowser.cleanup 两处错误 — playwright_borwser.py:239/246                                        pages = context.page（无此属性）和 await self
24. PlaywrightBrowser.input 漏 await / type() 无参 — playwright_borwser.py:347/358                            element = self._get_element_by_id(index)（漏 （缺 text）。
25. BrowserTool.browser_scroll_up/down 必填参数与 schema 矛盾 — browser.py:193/208                            to_top: Optional[bool]（无默认值），但 @tool(传时 method(**kwargs) 抛 TypeError。应加 =None。
26. FileTool.find_files 漏 await — file.py:202                                                                return self.sandbox.find_files(...) 返回协程
27. BaseTool.invoke 用 return 而非 raise — tools/base.py:108
return ValueError(f"工具[{tool_name}]未找到") 把异常对象当返回值返回，应 raise。

---                                                                                                           三、中危：HTTP 语义 / 安全 / 其它
                                                                                                              28. 健康检查失败仍返回 HTTP 200 — interfaces/-33
Response.fail(code=503,...) 只改业务 code，HTTP 状态仍是 200，健康检查形同虚设（探活/负载均衡会误判为正常）。 29. 在 Depends 依赖函数上用 @lru_cache —interfaces/service_dependencies.py（get_status_service/get_file_service）、schemas/repository_dependencies.py
每个请求注入的是新的 AsyncSession/RedisClient，缓存要么失效、要么缓存到已关闭的 session；若对象不可哈希会直接 TypeError。
30. 密钥明文入库且 .gitignore 未排除 — config.yaml（DeepSeek key、高德 MCP key、Jina token）、.env（COS SecretId/SecretKey）
当前都是未跟踪状态，一旦提交即泄露。.gitignore 只有 pycache/venv，没有 .env、config.yaml。
31. .env 里 COS_BUCKET= mooc-manus-... 等号后多了空格 — 值为 " mooc-manus-1319094570"，桶名带前导空格，COS 调用会失败。
32. CORS allow_origins=["*"] 与 allow_credent2
浏览器规范下 * + credentials 是无效组合（会被拒绝），也是安全隐患。
33. BingSearchEngine 兜底正则错误 — bing_sear
re.search(r"[\d,]+]\s*results", text) 多了个 ] 且无捕获组，永远匹配不上；即使匹配 match.group(1) 也会 IndexError。
34. past_hour 与 past_day 映射相同 — bing_sea 生效。
35. get_app_config_service 返回标注 ->None — service_dependencies.py:23，实际返回 AppConfigService。
36. get_a2a_servers 把 defaultInputModes 空串fig_service.py:176-177，agent_card.get(...,"") 在缺字段时给字符串空值，可能触发 pydantic 校验错误。

---
补充：目前实际可达性

现有路由只挂了 status / app-config / files（r 务队列这一整套核心路径还没有 HTTP入口。所以上面第 1–27 条大多是“潜伏 bug”，一旦接上 chat/session 端点就会集中爆发；而第 28–36 条里的健康检查、文件上传、CORS、密钥、COS 桶名空格是当前就能触发的。

---
需要的话，我可以按“先修致命→再修高危”的顺序帮 补丁（比如先把第 1、2、3、5、8、9 这些self.xxx = self.xxx / 拼写 / 漏 await 类硬伤清掉）。你说了先不动代码，我就只做只读排查，没改任何文件。