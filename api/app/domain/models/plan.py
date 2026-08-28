

from enum import Enum
import uuid

from pydantic import BaseModel, Field
from typing import List, Any, Optional

class ExecutionStatus(str, Enum):
    """规划、任务执行的状态"""
    PENDING = "pending" #空闲or等待
    RUNNING = "running" #执行中
    COMPLETED = "completed" #执行完成
    FAILED = "failed" #执行失败




class Step(BaseModel):
    """计划中的每一个步骤、子任务"""
    id:str =Field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    description : str = "" #步骤的描述信息
    status: ExecutionStatus = ExecutionStatus.PENDING
    result : Optional[str] = None #结果
    error:Optional[str] = None #错误信息
    success: bool = False #是否执行成功
    attachments: List[str] = Field(
        default_factory=list, #附件列表信息
    )

    @property
    def done(self)->bool:
        """只读属性，返回步骤是否结束"""
        return self.status in [ExecutionStatus.COMPLETED,ExecutionStatus.FAILED]


class Plan(BaseModel):
    """规划Domain模型，用于存储用户传递信息拆分出来的子任务、子步骤"""
    id : str = Field(
        default_factory=lambda: str(uuid.uuid4())
    )
    title: str = "" #任务标题
    goal: str = "" #任务目标
    language:str = "" #工作语言
    steps : List[Step] = Field(
        default_factory=list,
    )
    message: str = "" #用户传递的信息
    status: ExecutionStatus = ExecutionStatus.PENDING  #规划的状态
    error: Optional[str] = None  #错误信息




    @property
    def done(self)->bool:
        """"只读属性，用于判断计划是否结束"""
        return self.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]

    def get_next_step(self)->Optional[Step]:
        """获取需要执行的下一个步骤"""
        return next((step for step in self.steps if not step.done),None)
