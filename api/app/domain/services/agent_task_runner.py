

import asyncio
import io
import logging
from typing import AsyncGenerator, Awaitable, Callable, List, Optional
import uuid

from fastapi import UploadFile
from pydantic import TypeAdapter
from app.application.errors.exceptions import ArtifactDeliveryError
from app.domain.external.browser import Browser
from app.domain.external.file_storage import FileStorage
from app.domain.external.json_parser import JSONParser
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task, TaskRunner
from app.domain.models.app_config import A2AConfig, AgentConfig, MCPConfig
from app.domain.models.event import A2AToolContent, BaseEvent, BrowserToolContent, DoneEvent, ErrorEvent, Event, FileToolContent, MCPToolContent, MessageEvent, SearchToolContent, ShellToolContent, TitleEvent, ToolEvent, ToolEventStatus, WaitEvent
from app.domain.models.file import File
from app.domain.models.session import SessionStatus
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.file_repository import FileRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.flows.planner_react import PlannerReActFlow
from app.domain.services.tools.a2a import A2ATool
from app.domain.services.tools.mcp import MCPTool
from app.domain.models.message import Message
from app.domain.models.search import SearchResults
logger = logging.getLogger(__name__)

class AgentTaskRunner(TaskRunner):
    """基于agent智能体的任务运行器"""

    def __init__(
            self,
            llm:LLM,  #大语言模型
            agent_config: AgentConfig, #智能体配置
            mcp_config: MCPConfig, #MCP配置
            a2a_config: A2AConfig, #A2A配置
            session_id: str, #会话id
            session_repository: SessionRepository, #会话仓库
            file_storage: FileStorage, #文件存储桶
            file_repository:FileRepository, #文件数据仓库
            json_parser: JSONParser, #json解析器
            browser: Browser, #浏览器
            search_engine: SearchEngine, #搜索引擎
            sandbox: Sandbox, #沙箱
            on_task_done: Optional[Callable[[], Awaitable[None]]] = None,
        ):
        super().__init__()
        """构造函数，完成Agent任务运行器的创建"""
        self._session_id = session_id
        self._session_repository = session_repository
        self._sandbox = sandbox
        self._mcp_config = mcp_config
        self._mcp_tool = MCPTool()
        self._a2a_config = a2a_config
        self._a2a_tool = A2ATool()
        self._file_storage = file_storage
        self._file_repository = file_repository
        self._browser = browser
        self._on_task_done = on_task_done
        self._flow = PlannerReActFlow(
            llm=llm,
            agent_config=agent_config,
            session_id=session_id,
            session_repository=session_repository,
            json_parser=json_parser,
            browser=browser,
            sandbox=sandbox,
            search_engine=search_engine,
            mcp_tool=self._mcp_tool,
            a2a_tool=self._a2a_tool,
        )
    async def _put_and_add_event(self, task:Task, event:Event)->None:
        """往指定任务的消息队列中添加事件"""
        #0.在序列化和写入 Redis/数据库前标记事件所属任务，便于前端隔离历史任务错误
        event.task_id = task.id

        #1.往任务的输出消息队列中新增事件
        event_id = await task.output_stream.put(event.model_dump_json())
        event.id = event_id

        #2.将事件添加到对应的会话中
        await self._session_repository.add_event(self._session_id,event)

    @classmethod
    async def _pop_event(cls, task:Task)->Event:
        """从任务的输入流中获取事件信息"""
        #1.从任务task中读取数据
        event_id, event_str = await task.input_stream.pop()
        if event_str is None:
            logger.warning(f"AgentTaskRunner接收到空消息")
            return
        #2.使用pydantic + type类型将字符串转换成事件
        event = TypeAdapter(Event).validate_json(event_str)
        event.id = event_id
        return event

    async def _async_file_to_sandbox(self,file_id:str)->File:
        """根据文件id将文件同步到沙箱中"""
        try:
            #1.调用文件存储下载信息
            file_data, file = await self._file_storage.download_file(file_id)

            #2.组装沙箱文件路径
            filepath = f"/home/ubuntu/upload/{file.filename}"

            #3.调用沙箱将文件上传至沙箱
            tool_result = await self._sandbox.upload_file(
                file_data=file_data,
                filepath=filepath,
                filename=file.filename
            )
            #4.判断是否上传成功
            if tool_result.success:
                file.filepath = filepath
                await self._file_repository.save(file) #可以更新也可以不更新
                return file
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步文件[{file_id}]失败：{str(e)}")

    async def _sync_message_attachments_to_sandbox(self, event:MessageEvent)->None:
        """将消息事件中的附件同步到沙箱中"""
        #1.定义附件列表
        attachments: List[str] = []
        try:
            #2.判断消息中是否存在附件
            if event.attachments:
                #3.循环遍历所有的消息附件
                for attachment in event.attachments:
                    #4.工具同步文件的id将数据同步到沙箱中
                    file = await self._async_file_to_sandbox(attachment.id)
                    #5.判断是否同步成功
                    if file:
                        attachments.append(file)
                        await self._session_repository.add_file(self._session_id,file=file)
                #6.更新消息事件中的attachments
                event.attachments = attachments   
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步消息附件到沙箱失败：{str(e)}")


    async def _sync_file_to_storage(self, filepath:str)->File:
        """将沙箱中指定的文件路径数据同步到存储桶中。

        新文件上传并保存成功后再移除旧记录，避免新上传失败时把原本可用的
        附件记录也删掉。交付物上传失败会抛出 ArtifactDeliveryError 向上传播。
        """
        try:
            #1.根据文件路径从会话中查找旧文件记录
            old_file = await self._session_repository.get_file_by_path(self._session_id, filepath)

            #2.从沙箱中下载文件
            file_data = await self._sandbox.download_file(filepath)

            #3.提取文件名字并上传到存储桶
            filename = filepath.split("/")[-1]
            upload_file = UploadFile(
                file=file_data,
                filename=filename,
            )
            new_file = await self._file_storage.upload_file(upload_file=upload_file)
            new_file.filepath = filepath

            #4.往会话中新增新的文件信息
            await self._session_repository.add_file(self._session_id, new_file)

            #5.新文件上传并保存成功后，最后再移除旧记录
            if old_file:
                await self._session_repository.remove_file(self._session_id, old_file.id)
            return new_file
        except ArtifactDeliveryError:
            raise
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步文件[{filepath}]到存储桶失败：{str(e)}")
            raise ArtifactDeliveryError(f"文件交付失败：{filepath}") from e

    async def _sync_message_attachments_to_storage(self, event:MessageEvent)->None:
        """将消息事件的附件同步到文件存储桶中。

        附件属于任务交付物，任一附件上传失败必须让任务失败，不能静默丢弃。
        """
        #1.定义附件列表存储数据
        attachments: List[File] = []
        try:
            #2.判断消息中是否存在附件
            if event.attachments:
                #3.循环遍历所有附件
                for attachment in event.attachments:
                    #4.根据文件路径将数据同步到文件存储桶中
                    file = await self._sync_file_to_storage(attachment.filepath)
                    if file:
                        attachments.append(file)
            #5.更新事件中的附件列表资源
            event.attachments = attachments
        except ArtifactDeliveryError:
            raise
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步消息附件到存储桶失败：{str(e)}")
            raise ArtifactDeliveryError("附件交付失败") from e

    async def _get_browser_screenshot(self)->str:
        """获取浏览器截图并返回截图文件对应的id"""
        #1.调用浏览器完成截图
        screenshot = await self._browser.screenshot()

        #2.将浏览器截图上传到文件存储中
        file = await self._file_storage.upload_file(UploadFile(
            file=io.BytesIO(screenshot),
            filename=f"{str(uuid.uuid4())}.png",
        ))
        return file.id

    async def _handle_tool_event(self, event:ToolEvent)->None:
        """额外处理工具消息，使其前端交互更友好"""
        try:
            #1.如果事件状态为以调用则执行以下代码
            if event.status == ToolEventStatus.CALLED:
                #2.工具为浏览器则补全工具浏览器内容。截图属于增强展示，失败降级为无截图。
                if event.tool_name == "browser":
                    try:
                        screenshot_id = await self._get_browser_screenshot()
                    except Exception as e:
                        logger.warning(f"浏览器截图上传失败，降级为无截图：{str(e)}")
                        screenshot_id = ""
                    event.tool_content = BrowserToolContent(screenshot=screenshot_id)
                elif event.tool_name == "search":
                    #3.工具为搜索则添加搜索工具内容
                    search_results: ToolResult[SearchResults] = event.function_result
                    logger.info(f"搜索工具结果：{search_results}")
                    event.tool_content = SearchToolContent(results=search_results.data.results)
                elif event.tool_name == "shell":
                    #4.工具为shell则生成shell工具内容
                    if "session_id" in event.function_args:
                        shell_result = await self._sandbox.read_shell_output(event.function_args["session_id"],console=True)
                        event.tool_content = ShellToolContent(console=shell_result.data.get("console_records", []))
                    else:
                        event.tool_content=ShellToolContent(console="(No concole)")
                elif event.tool_name == "file":
                    #5.工具为file则同步到对象存储
                    if "filepath" in event.function_args:
                        filepath = event.function_args["filepath"]
                        file_read_result = await self._sandbox.read_file(filepath)
                        file_content: str = file_read_result.data.get("content", "") if file_read_result.data else ""
                        event.tool_content = FileToolContent(content=file_content)
                        # 写文件属于交付物，同步失败必须向上传播；读/替换等失败可降级
                        try:
                            await self._sync_file_to_storage(filepath)
                        except ArtifactDeliveryError:
                            if event.function_name == "write_file":
                                raise
                            logger.warning(f"文件[{filepath}]同步到存储失败（{event.function_name}，非交付写操作，降级处理）")
                    else:
                        event.tool_content = FileToolContent(content="(No Content)")
                elif event.tool_name  in ["mcp","a2a"]:
                    #6.工具为mcp或a2a则处理调用结果
                    logger.info(f"处理MCP/A2A工具事件，function_result:{event.function_result}")
                    if event.function_result:
                        #7.如果结果包含data则提取data
                        if hasattr(event.function_result,"data") and event.function_result.data:
                            logger.info(f"MCP/A2A工具调用结果：{event.function_result.data}")
                            event.tool_content = MCPToolContent(result=event.function_result.data) \
                                if event.tool_name == "mcp" \
                                else A2AToolContent(a2a_result=event.function_result.data)
                        elif hasattr(event.function_result,"success")and event.function_result.success:
                            #8.mcp/a2a工具调用成功，但无结果
                            logger.info(f"MCP/A2A工具调用成功返回，但无结果：{event.function_result}")
                            result_data = event.function_result.model_dump() \
                                if hasattr(event.function_result,"model_dump")\
                                else str(event.function_result)
                            event.tool_content = MCPToolContent(result=result_data) \
                                if event.tool_name == "mcp" \
                                else A2AToolContent(a2a_result=result_data)
                        else:
                            #9.其他情况将结果转换为字符串进行传递
                            logger.info(f"MCP/A2A工具结果：{event.function_result}")
                            event.tool_content = MCPToolContent(result=str(event.function_result)) \
                                    if event.tool_name == "mcp" \
                                    else A2AToolContent(a2a_result=str(event.function_result))
                    else:
                        logger.warning(f"MCP/A2A工具调用结果未发现")
                        event.tool_content = MCPToolContent(result="(MCP工具无可用结果)") \
                                if event.tool_name == "mcp" \
                                else A2AToolContent(a2a_result="(A2A工具无可用结果)")

        except ArtifactDeliveryError:
            # 文件交付失败必须向上传播，让任务进入失败状态
            raise
        except Exception as e:
            logger.exception(f"AgentTaskRunner上传工具内容失败：{str(e)}")

    async def _run_flow(self,message:Message)->AsyncGenerator[BaseEvent,None]:
        """根据消息对象运行PlannerReActFlow"""
        #1.判断传递的消息是否为空
        if not message.message:
            logger.warning(f"AgentTaskRunner接收了一条空消息")
            yield ErrorEvent(error="空消息错误")
            return 

        #2.调用流并运行获取事件消息
        async for event in self._flow.invoke(message):
            #3.判断是否为工具事件，如果是则额外处理
            if isinstance(event,ToolEvent):
                await self._handle_tool_event(event)
                pass
            elif isinstance(event,MessageEvent):
                #4.如果是消息事件则将ai消息事件中的附件同步到存储中
                await self._sync_message_attachments_to_storage(event)
            #5.将事件直接返回
            yield event
    
    async def invoke(self, task:Task)->None:
        """工具传递的任务处理agent消息队列并运行agent流"""
        try:
            #1.确保沙箱/mcp/a2a均初始化完成
            logger.info(f"AgentTaskRunner任务处理开始")
            await self._sandbox.ensure_sandbox()
            await self._mcp_tool.initialize(self._mcp_config)
            await self._a2a_tool.initialize(self._a2a_config)

            #2.循环读取任务中的输入消息队列
            while not await task.input_stream.is_empty():
                #3.从输入流中获取数据
                event = await self._pop_event(task)
                message = ""

                #4.判断事件类型是否是消息事件，如果是则处理消息并将附件同步到沙箱中
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                    await self._sync_message_attachments_to_sandbox(event)
                    logger.info(f"AgentTaskRunner接收到新消息：{message[:50]}...")

                #5.将消息事件转换为消息对象
                message_obj = Message(
                    message=message,
                    attachments=[attachment.filepath for attachment in event.attachments]
                )
                #6.传递消息对象并运行PlannerReActFlow
                async for event in self._run_flow(message_obj):
                    #7.将得到的事件添加到消息队列中
                    await self._put_and_add_event(task,event)

                    #8.如果事件类型为标题事件则更新会话标题
                    if isinstance(event,TitleEvent):
                        await self._session_repository.update_title(self._session_id,event.title)
                    elif isinstance(event,MessageEvent):
                        #9.如果事件为消息事件，则更新为最新消息并新增未读消息数
                        await self._session_repository.update_latest_message(self._session_id,event.message,event.create_at)
                        await self._session_repository.increment_unread_message_count(self._session_id)

                    elif isinstance(event, WaitEvent):
                        #10.如果事件是等待，则更新会话状态并终止程序
                        await self._session_repository.update_status(self._session_id,SessionStatus.WAITING)
                        return
                #11.判断如果输入消息队列为空则跳出巡抚
                if not await task.input_stream.is_empty():
                    break

            #12.更新会话状态为已完成
            await self._session_repository.update_status(self._session_id,SessionStatus.COMPLETED)
        except asyncio.CancelledError:
            #13.异步任务被取消，推送结束事件并更新状态
            logger.info(f"AgentTaskRunner任务运行取消")
            await self._put_and_add_event(task,DoneEvent())
            await self._session_repository.update_status(self._session_id,SessionStatus.COMPLETED)

        except Exception as e:
            #14.记录日志并往消息队列写入异常事件并更新会话状态为失败
            logger.exception(f"AgentTaskRunner运行出错：{str(e)}")
            await self._put_and_add_event(task, ErrorEvent(error=f"AgentTaskRunner出错：{str(e)}"))
            await self._session_repository.update_status(self._session_id,SessionStatus.FAILED)


    async def destroy(self):
        """销毁任务运行器并释放资源"""
        #1.清除沙箱
        logger.info(f"开始清除AgentTaskRunner资源")
        if self._sandbox:
            logger.info("销毁AgentTaskRunner中的沙箱环境")
            await self._sandbox.destroy()

        #2.清除mcp工具
        if self._mcp_tool:
            logger.info("销毁AgentTaskRunner中的mcp工具")
            await self._mcp_tool.cleanup()

        #3.销毁a2a工具
        if self._a2a_tool:
            logger.info("销毁AgentTaskRunner中的a2a工具")
            await self._a2a_tool.manager.cleanup()

    async def on_done(self, task:Task)->None:
        """任务结束时执行的回调函数"""
        logger.info(f"AgentTaskRunner任务执行结束")
        try:
            await self._mcp_tool.cleanup()
            if self._a2a_tool.manager:
                await self._a2a_tool.manager.cleanup()
            if self._browser:
                await self._browser.cleanup()
            if self._sandbox and getattr(self._sandbox, "client", None):
                await self._sandbox.client.aclose()
        finally:
            if self._on_task_done:
                await self._on_task_done()
