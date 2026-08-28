import asyncio

from app.domain.models.app_config import AgentConfig
from app.domain.models.event import MessageEvent
from app.domain.models.plan import ExecutionStatus, Plan, Step
from app.domain.services.agents.planner import PlannerAgent


class DummySessionRepository:
    async def get_memory(self, session_id, agent_name):
        return None

    async def save_memory(self, session_id, agent_name, memory):
        pass


class FixedJSONParser:
    """返回固定解析结果，隔离 Planner 的 LLM 输出。"""

    def __init__(self, payload):
        self._payload = payload

    async def invoke(self, text, default_value=None):
        return self._payload


class FixedPlannerAgent(PlannerAgent):
    """invoke 直接产出 MessageEvent，避免真实调用 LLM。"""

    async def invoke(self, query, format=None):
        yield MessageEvent(message="ignored")


def _make_planner(payload) -> PlannerAgent:
    return FixedPlannerAgent(
        session_id="session-1",
        session_repository=DummySessionRepository(),
        agent_config=AgentConfig(),
        llm=None,
        json_parser=FixedJSONParser(payload),
        tools=[],
    )


def test_update_plan_preserves_pending_steps_when_llm_returns_empty():
    plan = Plan(steps=[
        Step(id="1", description="步骤1", status=ExecutionStatus.COMPLETED, success=True),
        Step(id="2", description="步骤2"),
        Step(id="3", description="步骤3"),
    ])
    step = plan.steps[0]
    planner = _make_planner({"steps": []})

    async def run():
        events = []
        async for event in planner.update_plan(plan, step):
            events.append(event)
        return events

    events = asyncio.run(run())

    # LLM 返回空步骤时，未完成步骤必须被保留，不得整体删除
    assert [s.id for s in plan.steps] == ["1", "2", "3"]
    assert plan.steps[0].done is True
    assert plan.steps[1].done is False
    assert plan.steps[2].done is False
    assert any(event.type == "plan" for event in events)


def test_update_plan_still_replans_with_non_empty_steps():
    plan = Plan(steps=[
        Step(id="1", description="步骤1", status=ExecutionStatus.COMPLETED, success=True),
        Step(id="2", description="旧步骤2"),
        Step(id="3", description="旧步骤3"),
    ])
    step = plan.steps[0]
    planner = _make_planner({"steps": [
        {"id": "2", "description": "修订后的步骤2"},
        {"id": "3", "description": "修订后的步骤3"},
    ]})

    async def run():
        async for _ in planner.update_plan(plan, step):
            pass

    asyncio.run(run())

    # 非空返回仍应正常替换未完成步骤，保持已完成步骤不变
    assert [s.id for s in plan.steps] == ["1", "2", "3"]
    assert plan.steps[1].description == "修订后的步骤2"
    assert plan.steps[2].description == "修订后的步骤3"
