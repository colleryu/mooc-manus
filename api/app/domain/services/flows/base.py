
from abc import ABC, abstractmethod
from enum import Enum
from typing import AsyncGenerator
from app.domain.models.message import Message
from app.domain.models.event import BaseEvent

class FlowStatus(str, Enum):
    """流状态类型枚举"""
    IDLE = "idle"  #空闲中
    PLANNING = "planning" #规划中
    EXECUTTING="executting" #执行中
    SUMMARIZING="summarizing" #汇总中
    UPDATING="updating" #更新中
    COMPLETED="completed" #已完成

class BaseFlow(ABC):
    """基础流抽象类"""

    @abstractmethod
    async def invoke(self, message:Message)->AsyncGenerator[BaseEvent,None]:
        """流调用函数，返回可迭代的基础事件"""
        ...

    @property
    @abstractmethod
    def done(self)->bool:
        """只读属性，用于返回流是否结束"""
        ...
    