import asyncio
from types import SimpleNamespace

from app.infrastructure.external.sandbox import docker_sandbox
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


def test_get_creates_a_fresh_client_for_each_agent_task(monkeypatch):
    async def run():
        monkeypatch.setattr(
            docker_sandbox,
            "get_settings",
            lambda: SimpleNamespace(sandbox_address="127.0.0.1"),
        )

        first = await DockerSandbox.get("mooc-manus-sandbox")
        await first.client.aclose()
        second = await DockerSandbox.get("mooc-manus-sandbox")

        try:
            assert first is not second
            assert first.client.is_closed
            assert not second.client.is_closed
        finally:
            await second.client.aclose()

    asyncio.run(run())
