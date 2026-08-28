from app.domain.models.event import Event, MessageEvent, PlanEvent, PlanEventStatus
from app.domain.models.message import Message
from app.domain.models.plan import Plan, Step

from .base import BaseAgent
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.planner import (
    PLAN_SYSTEM_PROMPT,
    CREATE_PLAN_PROMPT,
    UPDATTE_PLAN_PROMPT,
)
from typing import Optional, AsyncGenerator

import logging

logger = logging.getLogger(__name__)
""""
多Agent 系统 = Planner Agent + ReActAgent

顺序：
1.PlannerAgent生成规划；
2.循环取出规划中的子步骤，让ReActAgent 执行，依次迭代；
3.ReActAgent执行完每一个子步骤之后，需要将子步骤结果 + Plan 传递给PlannerAgent 让其更新计划/Plan
4.循环取出规划中的子步骤，让ReActAgent 执行，依次迭代；
5. ...
6. 直到所有子任务/步骤都完成，这时候子步骤的所有结果汇总进行总结(ReActAgent)


PlannerAgent： 
- 功能: 将用户的需求拆解成为多个子任务 + 根据已完成的子任务更新规划
- 提示词：提示词：创建规划的 prompt 更新规划的prompt

ReActAgent：
- 功能： 迭代执行完每一个子任务、汇总所有的子任务进行总结
- 提示词： 执行任务的promop、汇总总结prompt
"""

class PlannerAgent(BaseAgent):
    """规划agent，用于将用户的任务、需求拆解成多个子任务"""
    name: str = "planner"
    _system_prompt: str = SYSTEM_PROMPT + PLAN_SYSTEM_PROMPT
    _format: Optional[str] = "json_object"
    _tool_choice: Optional[str] = "none"


    async def create_plan(self, message:Message)->AsyncGenerator[Event,None]:
        """根据用户传递的消息创建计划/规划，迭代返回对应的事件"""
        #1.根据用户传递的信息生成创建plan的提示词
        query = CREATE_PLAN_PROMPT.format(
            message= message.message,
            attachments = "\n".join(message.attachments),
        )

        #2.调用invoke()函数返回迭代事件
        async for event in self.invoke(query):
            #3.规划智能体业务使用json_object,正常情况下会返回MessageEvent
            if isinstance(event,MessageEvent):
                #4.记录日志并使用json解析器解析得到对应的数据
                logger.info(f"PlannerAgent消息：{event.message}")
                parsed_obj = await self._json_parser.invoke(event.message)

                #5.将解析对象转换成Plan计划
                plan = Plan.model_validate(parsed_obj)

                #6.返回PlanEvent事件表示创建成功
                yield PlanEvent(plan=plan,status=PlanEventStatus.CREATED)
            else:
                #返回不是消息事件的事件
                yield event

    async def update_plan(self, plan:Plan, step:Step) -> AsyncGenerator[Event,None]:
        """根据传递的原始规划 + 子步骤更新事件"""
        #1.使用plan + step 创建更新Plan
        query = UPDATTE_PLAN_PROMPT.format(
            plan=plan.model_dump_json(),
            step=step.model_dump_json(),
        )

        #2.调用invoke获取对应的事件
        async for event in self.invoke(query):
            #3.判断规划Agent生成的事件是否是消息事件
            if isinstance(event, MessageEvent):
                #4.记录日志并解析json
                logger.info(f"PlannerAgent生成消息：{event.message}")
                parsed_obj = await self._json_parser.invoke(event.message)

                #5.将解析对象转换成Plan
                update_plan = Plan.model_validate(parsed_obj)

                #6.拷贝更新计划中的steps，避免造成数据污染
                new_steps = [Step.model_validate(step) for step in update_plan.steps]

                #7.查询旧计划中第一个未完成的计划
                first_pending_index = None
                for idx, old_step in enumerate(plan.steps):
                    if not old_step.done:
                        first_pending_index = idx
                        break

                #8.判断是否有未完成的步骤，如果有则执行更新
                if first_pending_index is not None:
                    #9.获取历史已完成的子步骤并更新
                    updated_steps = plan.steps[:first_pending_index]

                    #10.LLM 返回空步骤但计划仍有未完成步骤时，不能据此删除它们。
                    # 执行 Agent 可能越界完成了其他步骤，此时 Planner 若直接返回空数组
                    # 会把所有待执行步骤整体删除，导致流程提前进入总结。
                    if new_steps:
                        updated_steps.extend(new_steps)
                    else:
                        logger.warning(
                            "PlannerAgent 返回空步骤，但计划仍存在 %d 个未完成步骤，保留原剩余步骤防止误删",
                            len(plan.steps) - first_pending_index,
                        )
                        updated_steps.extend(plan.steps[first_pending_index:])

                    #11.更新plan规划
                    plan.steps = updated_steps

                #11.返回规划更新事件
                yield PlanEvent(plan=plan, status=PlanEventStatus.UPDATED)

            else:
                #其他事件则直接返回
                yield event