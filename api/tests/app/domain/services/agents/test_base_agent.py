import asyncio

from app.domain.models.app_config import AgentConfig
from app.domain.models.memory import Memory
from app.domain.services.agents.base import BaseAgent


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.responses = [
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "先判断应该调用哪个工具",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            },
            {"role": "assistant", "content": "完成", "tool_calls": None},
        ]

    async def invoke(self, messages, **kwargs):
        self.calls.append(messages)
        return self.responses.pop(0)


class FakeSessionRepository:
    def __init__(self):
        self.memory = Memory()

    async def get_memory(self, session_id, agent_name):
        return self.memory

    async def save_memory(self, session_id, agent_name, memory):
        self.memory = memory


def test_reasoning_content_is_kept_for_follow_up_tool_request():
    async def run():
        llm = FakeLLM()
        agent = BaseAgent(
            session_id="session-1",
            session_repository=FakeSessionRepository(),
            agent_config=AgentConfig(),
            llm=llm,
            json_parser=None,
            tools=[],
        )

        first = await agent._invoke_llm([{"role": "user", "content": "查询黄金价格"}])
        await agent._invoke_llm(
            [{"role": "tool", "tool_call_id": "call-1", "content": "搜索结果"}]
        )

        assert first["reasoning_content"] == "先判断应该调用哪个工具"
        tool_call_message = next(message for message in llm.calls[1] if message.get("tool_calls"))
        assert tool_call_message["reasoning_content"] == "先判断应该调用哪个工具"

    asyncio.run(run())
