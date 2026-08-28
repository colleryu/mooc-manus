from typing import Protocol,Optional
from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults

class SearchEngine(Protocol):
    """搜索引擎api接口协议"""


    async def invoke(self, query: str, date_range: Optional[str] = None)->ToolResult:
        """根据传递的query + date_range(事件筛选)调用搜索引擎获取工具"""
        ...
        