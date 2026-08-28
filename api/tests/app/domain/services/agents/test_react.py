import asyncio

from app.domain.models.app_config import AgentConfig
from app.domain.models.event import ErrorEvent
from app.domain.models.message import Message
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.agents.react import ReActAgent


class DummySessionRepository:
    async def get_memory(self, session_id, agent_name):
        return None

    async def save_memory(self, session_id, agent_name, memory):
        pass


class ErrorYieldingReActAgent(ReActAgent):
    """在 invoke 阶段直接返回 ErrorEvent 的 Agent，用于验证失败状态不被覆盖。"""

    async def invoke(self, query, format=None):
        yield ErrorEvent(error="boom")


def test_execute_step_marks_failed_and_does_not_overwrite():
    async def run():
        agent = ErrorYieldingReActAgent(
            session_id="session-1",
            session_repository=DummySessionRepository(),
            agent_config=AgentConfig(),
            llm=None,
            json_parser=None,
            tools=[],
        )
        plan = Plan()
        step = Step(description="执行某步骤")
        events = []

        async for event in agent.execute_step(plan, step, Message(message="hello")):
            events.append(event)

        assert step.status == ExecutionStatus.FAILED
        assert step.error == "boom"
        # 失败状态不能被末尾的 completed 覆盖
        assert not any(
            getattr(event, "status", None) == "completed" for event in events
        )

    asyncio.run(run())
