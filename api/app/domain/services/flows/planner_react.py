from typing import Optional

from app.application.errors.exceptions import TaskExecutionError
from app.domain.external.browser import Browser
from app.domain.external.json_parser import JSONParser
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.app_config import AgentConfig
from app.domain.models.plan import ExecutionStatus, Plan
from app.domain.models.session import SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.planner import PlannerAgent
from app.domain.services.agents.react import ReActAgent
from app.domain.services.tools.a2a import A2ATool
from app.domain.services.tools.browser import BrowserTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.mcp import MCPTool
from app.domain.services.tools.message import MessageTool
from app.domain.services.tools.search import SearchTool
from app.domain.services.tools.shell import ShellTool
from .base import BaseFlow, FlowStatus
from app.domain.models.event import DoneEvent, MessageEvent, PlanEvent, PlanEventStatus, TitleEvent
import logging

logger = logging.getLogger(__name__)


class PlannerReActFlow(BaseFlow):
    """规划与执行流"""

    def __init__(
            self,
            llm:LLM,#大语言模型
            agent_config:AgentConfig,  #智能体配置
            session_id: str, #会话id
            session_repository: SessionRepository, #会话仓库
            json_parser: JSONParser, #JSON解析器
            sandbox: Sandbox, #沙箱
            browser:Browser, #浏览器
            search_engine:SearchEngine, #搜索引擎
            mcp_tool: MCPTool, #MCP工具
            a2a_tool:A2ATool, #A2A远程agent
        ):
        super().__init__()
        """构造函数，完成规划与执行流的初始化"""
        #1.初始化数据配置
        self._session_id = session_id
        self._session_repository = session_repository
        self.status = FlowStatus.IDLE
        self.plan : Optional[Plan] = None


        #2.初始化agent预设工具列表
        tools = [
            FileTool(sandbox=sandbox),
            ShellTool(sandbox=sandbox),
            BrowserTool(browser=browser),
            SearchTool(search_engine=search_engine),
            MessageTool(),
            mcp_tool,
            a2a_tool,
        ]

        #3.创建规划agent
        self.planner = PlannerAgent(
            session_id=session_id,
            session_repository=session_repository,
            agent_config=agent_config,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
        )

        #4.创建执行agent
        self.react = ReActAgent(
            session_id=session_id,
            session_repository=session_repository,
            agent_config=agent_config,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
        )
        logger.debug(f"创建执行agent成功，会话id：{session_id}")
    
    async def invoke(self, message):
        """传递消息，运行流，在流中调用planner和react agent"""
        #1.调用会话仓库查询会话是否存在
        session = await self._session_repository.get_by_id(self._session_id)
        if not session:
            raise ValueError(f"会话[{self._session_id}]不存在，请核实后重试")

        #2.判断会话的状态是否是空闲
        #如果不是则可能有两个状态
        # - 任务未结束，还在运行，但是用户有传递一条消息
        # - Agent在等待人类输入， 这个时候人类输入了
        # 着生活均需要处理历史消息列表，避免ai(工具调用消息)后直接接上人类消息
        if session.status != SessionStatus.PENDING:
            logger.debug(f"会话[{self._session_id}]未处于空闲状态，回滚数据确保消息列表格式")
            await self.planner.roll_back(message=message)
            await self.react.roll_back(message=message)

        #3.如果会话状态等于运行中，则流需要重新规划内容
        if session.status == SessionStatus.RUNNING:
            logger.debug(f"会话[{self._session_id}]处于运行状态并传递了新消息")
            self.status = FlowStatus.PLANNING

        #4.如果会话状态等于等待人类输入
        if session.status == SessionStatus.WAITING:
            logger.debug(f"会话[{self._session_id}]等待状态并传递了新消息")
            self.status = FlowStatus.EXECUTTING

        #5.更新会话状态为运行中
        await self._session_repository.update_status(self._session_id,SessionStatus.RUNNING)

        #6.获取当前会话中的最新事件
        self.plan = session.get_latest_plan()
        logger.info(f"Planner&ReAct流接受到消息：{message.message[:50]}...")

        #7.定义当前正在执行的子步骤
        step = None

        #8.创建死循环执行任务，根据不同的状态执行不同的操作
        while True:
            #9.如果流的状态为空闲，则只需要将状态修改为规划中
            if self.status == FlowStatus.IDLE:
                logger.info(f"Planner&ReAct状态从{FlowStatus.IDLE}变成{FlowStatus.PLANNING}")
                self.status = FlowStatus.PLANNING
            elif self.status == FlowStatus.PLANNING:
                #10.流状态为规划中，则调用规划Agent
                logger.info(f"Planner&ReAct流开始创建计划/Plan")
                async for event in self.planner.create_plan(message=message):
                    #11.判断规划Agent是否返回规划事件
                    if isinstance(event, PlanEvent) and event.status == PlanEventStatus.CREATED:
                        #12.创建计划成功时需要更新计划
                        self.plan = event.plan
                        logger.info(f"Planner&ReAct流成功创建计划,共计：{len(event.plan.steps)}步")

                        #13.在计划中同步生成了会话标题+初始ai消息
                        yield TitleEvent(title=event.plan.title)
                        yield MessageEvent(role="assistant", message=event.plan.message)
                    #14.将生成的事件直接输出(一般来说是PlanEvent)
                    yield event
                #15.计划创建完成，更新流状态为执行中
                logger.info(f"Planner&ReAct流状态从{FlowStatus.PLANNING}变成{FlowStatus.EXECUTTING}")
                self.status = FlowStatus.EXECUTTING

                #16.判断计划是否生成，步骤是否正常
                if not self.plan or len(self.plan.steps) == 0:
                    logger.info(f"Planner&ReAct流创建计划失败或无子步骤")
                    self.status = FlowStatus.COMPLETED
            elif self.status == FlowStatus.EXECUTTING:
                #17.流的状态为执行中，先将计划状态跳转为运行中，同时调用执行Agent完成每个步骤
                self.plan.status = ExecutionStatus.RUNNING

                #18.获取当前计划的下一个需要执行的子步骤
                step = self.plan.get_next_step()

                #19.如果不存在下一个需要执行的子计划，则更新流状态并执行后续步骤
                if not step:
                    logger.info(f"Planner&ReAct流状态从{FlowStatus.EXECUTTING}变为{FlowStatus.SUMMARIZING}")
                    self.status = FlowStatus.SUMMARIZING
                    continue
                #20.调用执行agent执行对应的步骤
                logger.info(f"Planner&ReAct流开始执行步骤{step.id}:{step.description[:50]}...")
                async for event in self.react.execute_step(self.plan,step=step,message=message):
                    yield event

                #20.1 步骤失败则标记计划失败并中止流程，不得继续更新计划伪装成功
                if step.status == ExecutionStatus.FAILED:
                    self.plan.status = ExecutionStatus.FAILED
                    self.plan.error = step.error or "步骤执行失败"
                    logger.error(f"Planner&ReAct流步骤{step.id}执行失败：{self.plan.error}")
                    yield PlanEvent(status=ExecutionStatus.FAILED, plan=self.plan)
                    raise TaskExecutionError(self.plan.error)

                #21.压缩执行agent记忆，避免上下文腐化+消耗大量token
                logger.info(f"压缩{self.react.name} Agent记忆/上下文")
                await self.react.compact_memory()

                #22.将状态更新为updating
                self.status = FlowStatus.UPDATING

            elif self.status == FlowStatus.UPDATING:
                #23.流状态为更新则表示需要更新计划
                logger.info(f"Planner&ReAct流开始更新计划")
                async for event in self.planner.update_plan(self.plan,step):
                    yield event

                #24.计划更新完成，需要执行相应的子步骤
                logger.info(f"Planner&ReAct流状态从{FlowStatus.UPDATING}变成{FlowStatus.EXECUTTING}")
                self.status = FlowStatus.EXECUTTING

            elif self.status == FlowStatus.SUMMARIZING:
                #25.流状态为总结中，则以为着所有子步骤都执行完成
                logger.info(f"Planner&ReAct流开始总结")
                async for event in self.react.summarize():
                    yield event
                #26.总结完毕，意味着流即将结束
                logger.info(f"Planner&ReAct流状态从{FlowStatus.SUMMARIZING}变为{FlowStatus.COMPLETED}")
                self.status = FlowStatus.COMPLETED
            elif self.status == FlowStatus.COMPLETED:
                #27.计划状态已完成则更新plan状态，发送计划事件通知api已完成
                self.plan.status = ExecutionStatus.COMPLETED
                self.status = FlowStatus.IDLE
                yield PlanEvent(status=ExecutionStatus.COMPLETED,plan=self.plan)
                break
        #28.任务已经结束，则返回结束事件
        yield  DoneEvent()
        logger.info(f"Planner&ReAct流处理任务消息已完毕")
        
    @property
    def done(self):
        """只读属性，放回流是否结束"""
        return self.status == FlowStatus.IDLE