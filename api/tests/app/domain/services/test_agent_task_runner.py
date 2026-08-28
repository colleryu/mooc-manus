import asyncio
import io
import json

import pytest

from app.application.errors.exceptions import ArtifactDeliveryError
from app.domain.models.event import DoneEvent
from app.domain.models.file import File
from app.domain.services.agent_task_runner import AgentTaskRunner


class FakeOutputStream:
    def __init__(self):
        self.put_calls = []

    async def put(self, data):
        self.put_calls.append(data)
        return "event-1"


class FakeTask:
    def __init__(self):
        self.id = "task-1"
        self.output_stream = FakeOutputStream()


class RecordingSessionRepository:
    def __init__(self, old_file=None):
        self.old_file = old_file
        self.events = []
        self.added = []
        self.removed = []

    async def add_event(self, session_id, event):
        self.events.append(event)

    async def get_file_by_path(self, session_id, filepath):
        return self.old_file

    async def add_file(self, session_id, file):
        self.added.append(file)

    async def remove_file(self, session_id, file_id):
        self.removed.append(file_id)


class FakeSandbox:
    def __init__(self, download_raises=False):
        self.download_raises = download_raises

    async def download_file(self, filepath):
        if self.download_raises:
            raise RuntimeError("sandbox 下载失败")
        return io.BytesIO(b"content")


class FakeFileStorage:
    def __init__(self, raise_on_upload=False):
        self.raise_on_upload = raise_on_upload

    async def upload_file(self, upload_file):
        if self.raise_on_upload:
            raise RuntimeError("COS 上传失败")
        return File(filename=upload_file.filename, size=7)


def _make_runner(session_repository, sandbox=None, file_storage=None):
    runner = AgentTaskRunner.__new__(AgentTaskRunner)
    runner._session_id = "session-1"
    runner._session_repository = session_repository
    runner._sandbox = sandbox if sandbox is not None else FakeSandbox()
    runner._file_storage = file_storage if file_storage is not None else FakeFileStorage()
    return runner


def test_put_and_add_event_sets_task_id():
    async def run():
        repo = RecordingSessionRepository()
        runner = _make_runner(repo)
        task = FakeTask()
        event = DoneEvent()

        await runner._put_and_add_event(task, event)

        assert event.task_id == "task-1"
        assert repo.events[0].task_id == "task-1"
        # 写入消息队列的 JSON 也必须包含 task_id
        payload = json.loads(task.output_stream.put_calls[0])
        assert payload["task_id"] == "task-1"

    asyncio.run(run())


def test_sync_file_to_storage_replaces_old_after_new_succeeds():
    async def run():
        old = File(id="old-1", filename="guide.md")
        repo = RecordingSessionRepository(old_file=old)
        runner = _make_runner(repo)

        new_file = await runner._sync_file_to_storage("/home/ubuntu/guide.md")

        assert new_file.filepath == "/home/ubuntu/guide.md"
        # 新文件先 add，旧文件后 remove，顺序不能颠倒
        assert [f.id for f in repo.added] == [new_file.id]
        assert repo.removed == ["old-1"]

    asyncio.run(run())


def test_sync_file_to_storage_raises_on_upload_failure():
    async def run():
        old = File(id="old-1", filename="guide.md")
        repo = RecordingSessionRepository(old_file=old)
        runner = _make_runner(repo, file_storage=FakeFileStorage(raise_on_upload=True))

        with pytest.raises(ArtifactDeliveryError):
            await runner._sync_file_to_storage("/home/ubuntu/guide.md")

        # 上传失败时旧附件记录必须保留，不能被提前删除
        assert repo.removed == []
        assert repo.added == []

    asyncio.run(run())
