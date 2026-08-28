
from pydantic import BaseModel,Field
from typing import Optional, List


class SearchResultItem(BaseModel):
    """搜索结果条目数据类型"""
    url: str #搜索条目url信息
    title: str #搜索条目标题
    snippet: str = "" #搜索条目摘要信息


class SearchResults(BaseModel):
    """搜索结果数据模型"""
    query: str #查询query
    date_range: Optional[str] = None #日期筛选范围
    total_results: int = 0 #搜索结果条数
    results : List[SearchResultItem] = Field(
        default_factory=list #搜索结果
    )
    provider: str = "bing" #搜索提供方
    raw_count: int = 0 #解析出的原始结果数（过滤前）
    filtered_count: int = 0 #相关性过滤后的结果数

