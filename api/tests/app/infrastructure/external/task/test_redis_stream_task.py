import asyncio

from app.infrastructure.external.task.redis_stream_task import RedisStreamTask


class WaitingRunner:
    def __init__(self):
        self.started = asyncio.Event()
        self.destroyed = False
        self.done = False

    async def invoke(self, task):
        self.started.set()
        await asyncio.Event().wait()

    async def on_done(self, task):
        self.done = True

    async def destroy(self):
        self.destroyed = True


def test_stop_can_preserve_session_level_resources():
    async def run():
        runner = WaitingRunner()
        task = RedisStreamTask(runner)

        await task.invoke()
        await runner.started.wait()
        await task.stop(destroy_runner=False)

        assert runner.done
        assert not runner.destroyed
        assert RedisStreamTask.get(task.id) is None

    asyncio.run(run())
