

from datetime import datetime
from typing import List, Optional

from sqlalchemy import cast, delete, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from app.domain.models.event import BaseEvent
from app.domain.models.file import File
from app.domain.models.memory import Memory
from app.domain.models.session import Session, SessionStatus
from app.domain.repositories.session_repository import SessionRepository
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.session import SessionModel

class DBSessionRepository(SessionRepository):
    """Postgres数据库的会话仓库"""

    def __init__(self, dbsession:AsyncSession, auto_commit: bool = False)->None:
        super().__init__()
        """构造函数，挖不出数据库会话初始化"""
        self.db_session = dbsession
        self.auto_commit = auto_commit

    async def _finish_write(self)->None:
        """后台 Agent 不在 FastAPI 请求事务中，需要自行提交写操作。"""
        if self.auto_commit:
            await self.db_session.commit()

    async def save(self, session:Session)->None:
        """根据传递的领域模型更新会话或新增会话"""
        #1.根据id查询会话是否存在
        stmt = select(SessionModel).where(SessionModel.id == session.id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        #2.如果会话不存在则新建会话
        if not record:
            record = SessionModel.from_domain(session)
            self.db_session.add(record)
            await self._finish_write()
            return
        #3.会话存在则更新会话
        record.update_from_domain(session)
        await self._finish_write()

    async def get_all(self)->List[Session]:
        """获取所有会话列表"""
        #1.构建sql查询所有记录
        stmt = select(SessionModel).order_by(SessionModel.latest_message_at.desc())

        result = await self.db_session.execute(stmt)
        records = result.scalars().all()

        #2.将数据循环转换从Domain模型
        return [record.to_domain() for record in records]

    async def get_by_id(self, session_id: str)->Optional[Session]:
        """根据会话id获取会话数据"""
        #1.构建sql查询数据是否存在
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        #2.判断会话记录是否存在并返回
        return record.to_domain() if record is not None else None

    async def delete_by_id(self, session_id:str)->None:
        """根据会话id删除会话"""
        #1.构建sql删除数据
        stmt = delete(SessionModel).where(SessionModel.id == session_id)


        #2.执行sql同时无需检查是否删除成功
        await self.db_session.execute(stmt)
        await self._finish_write()

    async def update_title(self, session_id:str, title:str)->None:
        """更新会话标题"""
        #1.构建sql更新会话并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(title=title)
        )
        result = await self.db_session.execute(stmt)

        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()


    async def update_latest_message(self, session_id:str, message:str, timestamp:datetime):
        """更新会话最新消息"""
        #1.构建sql更新会话消息并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                latest_message=message,
                latest_message_at=timestamp,
            )
        )
        result = await self.db_session.execute(stmt)

        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()


    async def add_event(self, session_id:str, event:BaseEvent)->None:
        """往会话中新增事件"""
        #1.将event序列化为json
        event_data = event.model_dump(mode="json")

        #2.构造原则更新sql并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                events=func.coalesce(SessionModel.events, cast([],JSONB)).op("||")(cast([event_data],JSONB)),
            )
        )
        result = await self.db_session.execute(stmt)
        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()

    async def add_file(self, session_id:str, file:File)->None:
        """往会话中新增数据"""
        #1.将file序列化为json
        file_data = file.model_dump(mode="json")

        #2.构造原则更新sql并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                files=func.coalesce(SessionModel.files, cast([],JSONB)).op("||")(cast([file_data],JSONB)),
            )
        )
        result = await self.db_session.execute(stmt)
        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()


    async def remove_file(self, session_id:str, file_id:str)->None:
        """删除会话中指定的文件"""
        #1.查询会话记录并加锁
        stmt = select(SessionModel).where(SessionModel.id == session_id).with_for_update()
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        #2.检查会话记录是否存在
        if not record:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        #3.会话记录存在，则在内存中过滤file
        if not record.files:
            return
        original_length = len(record.files)
        new_files = [file for file in record.files if file.get("id") != file_id]

        #4.判断文件长度是否有变化
        if len(new_files) == original_length:
            return

        #5.更新文件数据
        record.files = new_files
        await self._finish_write()

    async def get_file_by_path(self, session_id:str, filepath:str)->Optional[File]:
        """根据文件路径获取文件信息"""
        #1.构建sql查询会话记录
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        result = await self.db_session.execute(stmt)
        record = result.scalar_one_or_none()

        #2.判断会话记录或文件列表是否为空
        if not record or not record.files:
            return None

        #3.遍历查找数据返回文件信息
        for file in record.files:
            if file.get("filepath","") == filepath:
                return File(**file)

        return None
    

    async def update_status(self, session_id:str, status:SessionStatus)->None:
        """更新会话状态"""
        #1.构建sql更新会话消息并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                status=status.value
            )
        )
        result = await self.db_session.execute(stmt)

        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()

    async def update_unread_message_count(self, session_id:str, count:int)->None:
        """更新会话的未读消息数"""
        #1.构建sql更新会话消息并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                unread_message_count=count
            )
        )
        result = await self.db_session.execute(stmt)

        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()


    async def increment_unread_message_count(self, session_id:str)->None:
        """更新会话中的未读消息数"""
        #1.构建sql完成数据更新
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                unread_message_count = func.coalesce(SessionModel.unread_message_count,0)+1,
            )
        )
        result = await self.db_session.execute(stmt)

        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()

    async def decrement_unread_message_count(self, session_id:str)->None:
        """将会话中未读消息数-1"""
        #1.构建sql完成数据更新
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                unread_message_count = func.greatest(
                    func.coalesce(SessionModel.unread_message_count,0) - 1,
                    0,
                ),
            )
        )
        result = await self.db_session.execute(stmt)

        #2.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()


    async def save_memory(self, session_id:str, agent_name:str, memory:Memory):
        """存储或更新会话中的记忆(字典直接覆盖)"""
        #1.将memory转换为json结构
        memory_data = memory.model_dump(mode="json")

        #2.构建要打补丁的字典
        patch_data = {agent_name:memory_data}

        #3.创建sql并执行
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                memories=func.coalesce(SessionModel.memories,cast({},JSONB)).op("||")(cast(patch_data,JSONB)),
            )
        )
        result = await self.db_session.execute(stmt)

        #4.检查是否更新成功
        if result.rowcount == 0:
            raise ValueError(f"会话[{session_id}]不存在，请核实后重试")
        await self._finish_write()

    async def get_memory(self, session_id:str, agent_name:str)->Memory:
        """获取指定会话的agent记忆"""
        #1.构造sql查询会话
        stmt = (
            select(SessionModel.memories[agent_name])
            .where(SessionModel.id == session_id)
        )
        result = await self.db_session.execute(stmt)
        memory_data = result.scalar_one_or_none()

        #2.如果记忆存在则转换为domain格式
        if memory_data:
            return Memory(**memory_data)

        #3.如果记忆不存在，则创建一个空记忆后返回
        return Memory(messages=[])
