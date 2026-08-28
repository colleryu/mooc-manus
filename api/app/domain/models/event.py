
from datetime import datetime
import uuid
from typing import Annotated, Dict, Literal,List,Any, Union,Optional
from enum import Enum
from pydantic import BaseModel, Field

from app.domain.models.plan import Plan,Step
from app.domain.models.search import SearchResultItem
from app.domain.models.tool_result import ToolResult
from .file import File

class PlanEventStatus(str, Enum):
    """规划事件状态"""
    CREATED = "created" #已创建
    UPDATED = "updated" #已更新
    COMPLETED = "completed" #已完成


class StepEventStatus(str,Enum):
    """步骤事件状态"""
    STARTED = "started" #已开始
    COMPLETED = "completed" #已完成
    FAILED = "failed" #失败
class BaseEvent(BaseModel):
    """基础事件类型"""
    id : str = Field(
        default_factory=lambda: str(uuid.uuid4()) #事件id
    )
    type:Literal[""]= ""     #事件的类型

    create_at:datetime = Field(
        default_factory=datetime.now  #事件创建时间
    )

    # 事件所属任务id。历史数据没有该字段时允许解析，保持向后兼容。
    task_id: Optional[str] = None


class ToolEventStatus(str,Enum):
    """工具事件状态类型枚举"""
    CALLING="calling" #调用中
    CALLED = "called" #调用完毕

class PlanEvent(BaseEvent):
    """规划事件类型"""
    type:Literal["plan"]="plan"
    plan:Plan #规划
    status : PlanEventStatus = PlanEventStatus.CREATED  #规划事件状态



class TitleEvent(BaseEvent):
    """标题事件类型"""
    type:Literal["title"] = "title"
    title : str = "" #标题


class StepEvent(BaseEvent):
    """子任务、步骤事件"""
    type:Literal["step"] = "step"
    step : Step  #步骤信息
    status : StepEventStatus = StepEventStatus.STARTED




class MessageEvent(BaseEvent):
    """消息事件，包含人类消息和ai消息"""
    type:Literal["message"] = "message"
    role: Literal["user", "assistant"] = "assistant" #消息角色
    message: str = "" #消息本身
 
    attachments: List[File] = Field(default_factory=list) #附件列表消息

class BrowserToolContent(BaseModel):
    """浏览器工具扩展类容"""
    screenshot: str #浏览器快照截图

class SearchToolContent(BaseModel):
    """搜索工具内容"""
    results:List[SearchResultItem] #搜索结果列表

class ShellToolContent(BaseModel):
    """shell工具内容"""
    console: Any #控制台内容

class FileToolContent(BaseModel):
    """文件工具内容"""
    content: str #文件内容

class MCPToolContent(BaseModel):
    """MCP工具内容"""
    result:Any  #MCP工具结果

class A2AToolContent(BaseModel):
    """A2A智能体工具内容"""
    a2a_result:Any #a2a工具结果
ToolContent = Union[
    BrowserToolContent,
    MCPToolContent,
    SearchToolContent,
    ShellToolContent,
    FileToolContent,
    A2AToolContent,
    ]

class ToolEvent(BaseEvent):
    """工具事件"""

    type: Literal["tool"] = "tool"
    tool_call_id: str #工具调用id
    tool_name:str #工具箱、工具集的名字
    tool_content: Optional[ToolContent] = None #工具扩展内容
    function_name:str #LLM调用工具、函数名字
    function_args:Dict[str,Any]  #LLM生成的工具调用参数
    function_result:Optional[ToolResult] = None #工具调用结果
    status: ToolEventStatus = ToolEventStatus.CALLING #工具事件状态

class WaitEvent(BaseEvent):
    """等待事件，等待用户输入确定"""
    type: Literal["wait"] = "wait"


class ErrorEvent(BaseEvent):
    """错误事件"""
    type: Literal["error"] = "error"
    error: str = "" #错误信息


class DoneEvent(BaseEvent):
    """结束事件"""
    type: Literal["done"] = "done"


Event = Annotated[ Union[
    PlanEvent,
    TitleEvent,
    StepEvent,
    MessageEvent,
    ToolEvent,
    WaitEvent,
    ErrorEvent,
    DoneEvent,
],
    Field(discriminator="type")
]