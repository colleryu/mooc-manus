from datetime import datetime

from docker.errors import NotFound as DockerNotFound
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.errors.exceptions import BadRequestError, NotFoundError
from app.domain.models.event import MessageEvent, PlanEvent, ToolEvent, ToolEventStatus
from app.application.services.app_config_service import AppConfigService
from app.domain.models.session import Session, SessionStatus
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.infrastructure.external.file_storage.cos_file_storage import CosFileStorage
from app.infrastructure.external.json_parser.repair_json_parser import RepairJSONParser
from app.infrastructure.external.llm.openai_llm import OpenAILLM
from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox
from app.infrastructure.external.search.bing_search import BingSearchEngine
from app.infrastructure.external.task.redis_stream_task import RedisStreamTask
from app.infrastructure.repositories.db_file_repository import DBFileRepository
from app.infrastructure.repositories.db_session_repository import DBSessionRepository
from app.infrastructure.storage.cos import Cos
from app.infrastructure.storage.postgres import get_postgres
from core.config import Settings


class SessionService:
    """编排会话持久化、Agent 后台任务与事件流。"""

    def __init__(
        self,
        db_session: AsyncSession,
        cos: Cos,
        settings: Settings,
        app_config_service: AppConfigService,
    )->None:
        self.db_session = db_session
        self.repository = DBSessionRepository(db_session)
        self.cos = cos
        self.settings = settings
        self.app_config_service = app_config_service

    async def list_sessions(self)->list[Session]:
        return await self.repository.get_all()

    async def create_session(self, title: str = "")->Session:
        session = Session(title=title.strip())
        await self.repository.save(session)
        await self.db_session.commit()
        return session

    async def get_session(self, session_id: str)->Session:
        session = await self.repository.get_by_id(session_id)
        if not session:
            raise NotFoundError(f"会话[{session_id}]不存在")
        return session

    @staticmethod
    def _generated_filepaths(session: Session)->list[str]:
        """Return declared task deliverables, falling back to successful writes."""
        declared: list[str] = []
        written: list[str] = []
        for event in session.events:
            if isinstance(event, PlanEvent):
                for step in event.plan.steps:
                    declared.extend(step.attachments)
            elif isinstance(event, MessageEvent) and event.role == "assistant":
                declared.extend(file.filepath for file in event.attachments if file.filepath)
            elif (
                isinstance(event, ToolEvent)
                and event.status == ToolEventStatus.CALLED
                and event.function_name == "write_file"
                and event.function_result
                and event.function_result.success
            ):
                filepath = event.function_args.get("filepath")
                if isinstance(filepath, str):
                    written.append(filepath)

        paths = declared or written
        return list(dict.fromkeys(path for path in paths if path.startswith("/home/ubuntu/")))

    async def list_generated_files(self, session_id: str)->list[dict[str, str]]:
        session = await self.get_session(session_id)
        if not session.sandbox_id:
            return []
        try:
            sandbox = await DockerSandbox.get(session.sandbox_id)
        except DockerNotFound:
            # 兼容切换到独立容器前创建的共享 Sandbox 会话，便于下载旧产物。
            if session.sandbox_id == "mooc-manus-sandbox":
                sandbox = DockerSandbox(ip="127.0.0.1")
            else:
                return []
        try:
            files = []
            for filepath in self._generated_filepaths(session):
                result = await sandbox.check_file_exists(filepath)
                if result.success and result.data and result.data.get("exists"):
                    filename = filepath.rsplit("/", 1)[-1]
                    files.append({
                        "filepath": filepath,
                        "filename": filename,
                        "extension": filename.rsplit(".", 1)[-1] if "." in filename else "",
                    })
            return files
        finally:
            await sandbox.client.aclose()

    async def download_generated_file(self, session_id: str, filepath: str):
        session = await self.get_session(session_id)
        if not session.sandbox_id or filepath not in self._generated_filepaths(session):
            raise NotFoundError("文件不存在或不属于当前会话")
        try:
            sandbox = await DockerSandbox.get(session.sandbox_id)
        except DockerNotFound as exc:
            if session.sandbox_id == "mooc-manus-sandbox":
                sandbox = DockerSandbox(ip="127.0.0.1")
            else:
                raise NotFoundError("Sandbox 已因长时间无操作而回收") from exc
        try:
            return await sandbox.download_file(filepath)
        finally:
            await sandbox.client.aclose()

    async def delete_session(self, session_id: str)->None:
        session = await self.get_session(session_id)
        task = RedisStreamTask.get(session.task_id) if session.task_id else None
        if isinstance(task, RedisStreamTask):
            await task.stop()
        elif session.sandbox_id and session.sandbox_id != "mooc-manus-sandbox":
            try:
                sandbox = await DockerSandbox.get(session.sandbox_id)
            except DockerNotFound:
                # Sandbox 可能已经被空闲 TTL 自动回收，会话仍应能正常删除。
                pass
            else:
                await sandbox.destroy()
        await self.repository.delete_by_id(session_id)

    async def mark_read(self, session_id: str)->None:
        await self.get_session(session_id)
        await self.repository.update_unread_message_count(session_id, 0)

    async def cancel(self, session_id: str)->None:
        session = await self.get_session(session_id)
        task = RedisStreamTask.get(session.task_id) if session.task_id else None
        if isinstance(task, RedisStreamTask):
            # 停止当前 Agent 任务，但保留会话级 Sandbox，允许用户继续追问。
            await task.stop(destroy_runner=False)
        await self.repository.update_status(session_id, SessionStatus.COMPLETED)

    async def send_message(
        self,
        session_id: str,
        message: str,
        attachment_ids: list[str],
    )->Session:
        session = await self.get_session(session_id)
        if not message.strip() and not attachment_ids:
            raise BadRequestError("消息和附件不能同时为空")

        current_task = RedisStreamTask.get(session.task_id) if session.task_id else None
        if current_task and not current_task.done:
            raise BadRequestError("当前任务仍在运行，请先等待完成或停止任务")

        file_repository = DBFileRepository(self.db_session)
        attachments = []
        for file_id in attachment_ids:
            file = await file_repository.get_by_id(file_id)
            if not file:
                raise NotFoundError(f"附件[{file_id}]不存在")
            attachments.append(file)

        if session.sandbox_id and session.sandbox_id != "mooc-manus-sandbox":
            try:
                sandbox = await DockerSandbox.get(session.sandbox_id)
            except DockerNotFound:
                # 空闲回收后的会话在用户再次发消息时获得一个全新独立 Sandbox。
                sandbox = await DockerSandbox.create()
                session.sandbox_id = sandbox.id
        else:
            sandbox = await DockerSandbox.create()
            session.sandbox_id = sandbox.id

        task_db_session = get_postgres().session_factory()
        task_repository = DBSessionRepository(task_db_session, auto_commit=True)
        task_file_repository = DBFileRepository(task_db_session)
        file_storage = CosFileStorage(
            bucket=self.settings.cos_bucket,
            cos=self.cos,
            file_repository=task_file_repository,
        )
        app_config = await self.app_config_service._load_app_config()
        browser = await sandbox.get_browser()

        async def close_task_session()->None:
            await task_db_session.close()

        runner = AgentTaskRunner(
            llm=OpenAILLM(app_config.llm_config),
            agent_config=app_config.agent_config,
            mcp_config=app_config.mcp_config,
            a2a_config=app_config.a2a_config,
            session_id=session_id,
            session_repository=task_repository,
            file_storage=file_storage,
            file_repository=task_file_repository,
            json_parser=RepairJSONParser(),
            browser=browser,
            search_engine=BingSearchEngine(),
            sandbox=sandbox,
            on_task_done=close_task_session,
        )
        task = RedisStreamTask.create(runner)
        session.task_id = task.id
        session.status = SessionStatus.RUNNING
        await self.repository.save(session)

        # save(session) 会覆盖 JSONB 字段，因此用户事件必须在会话基础字段保存后追加。
        user_event = MessageEvent(
            role="user",
            message=message.strip(),
            attachments=attachments,
        )
        # 用户消息也属于本轮新建任务，标记 task_id 以便前端按任务归属判断事件。
        user_event.task_id = task.id
        await self.repository.add_event(session_id, user_event)
        await self.repository.update_latest_message(
            session_id,
            user_event.message or "发送了附件",
            datetime.now(),
        )
        await self.db_session.commit()

        await task.input_stream.put(user_event.model_dump_json())
        await task.invoke()
        return await self.get_session(session_id)
