from datetime import datetime
from typing import Any, Dict, List
import uuid

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.domain.models.session import Session
from app.infrastructure.models.base import Base
from sqlalchemy import(
    DateTime,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
    Integer,
)
class SessionModel(Base):
    """会话ORM模型"""
    __tablename__="sessions"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_sessions_id"),
    )

    id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    ) #会话id

    sandbox_id: Mapped[str] = mapped_column(
        String(255),
        nullable=True
    )#沙箱id
    task_id:Mapped[str] = mapped_column(String(255),nullable=True) #任务id
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    )  #会话标题
    unread_message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    ) #未读消息数
    latest_message:Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("''::text")
    )  #最后一条消息
    latest_message_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=True,
    )#最后一条消息时间
    events: Mapped[List[Dict[str,Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    ) #事件列表

    files: Mapped[List[Dict[str,Any]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    memories: Mapped[Dict[str,Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ) #会话两个Agent的记忆
    status: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''::character varying"),
    ) #会话状态

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        onupdate=datetime.now,
        server_default=text("CURRENT_TIMESTAMP(9)"),
    ) #更新时间
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(9)"),
    ) #创建时间

    @classmethod
    def from_domain(cls, session:Session)->"SessionModel":
        """从会话领域模型构建ORM模型"""
        return cls(
            #1.基础字段，使用Basemodel提供的python字典格式转换
            **session.model_dump(
                mode="python",
                exclude={"memories","files","events","updated_at","created_at"},
            ),
            #2.复杂字段，使用Basemodel提供的json字典转换格式
            **session.model_dump(
                mode="json",
                include={"memories","files","events"},
            )
        )
    def to_domain(self)->Session:
        """将会话ORM模型转换成领域模型"""
        return Session.model_validate(self,from_attributes=True)

    def update_from_domain(self, session:Session)->None:
        """从传递的领域模型更新ORM模型"""
        #1.基础字段：python模式
        base_data = session.model_dump(
            mode="python",
            exclude={"memories","files","events","updated_at","created_at"},
        )
        #2.复杂字段：JSON模型
        json_data = session.model_dump(
            mode="json",
            include={"memories","files","events"},
        )

        #3.合并更新
        for filed, value in {**base_data,**json_data}.items():
            setattr(self,filed,value)


