
import time
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx

from app.domain.external.search import SearchEngine
from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults, SearchResultItem

logger = logging.getLogger(__name__)

# 命中任一标记说明页面是验证码/反爬/异常页面，不应把其中的结果当作正常搜索
_BLOCKED_MARKERS = [
    "captcha",
    "unusual traffic",
    "we detected",
    "robot check",
    "安全验证",
    "验证码",
    "访问异常",
    "检测到异常",
    "请完成以下验证",
]


class BingSearchEngine(SearchEngine):
    """bing搜索引擎"""

    def __init__(self):
        """构造函数，初始化bing搜索引擎的相关信息"""
        super().__init__()
        self.base_url = "https://www.bing.com/search"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36 Edg/151.0.0.0",
            # 中文查询使用中文语言与地区参数，避免偏向英文结果
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        self.cookies = httpx.Cookies()

    @staticmethod
    def _extract_keywords(query: str) -> List[str]:
        """从查询中提取关键词。

        中文长词拆成 2-gram，便于与标题/摘要中的子串匹配；英文/短词按空白切分。
        """
        tokens = re.split(r"[\s,，。！？!?;；:：、/\\·]+", query.strip())
        keywords: List[str] = []
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            # 纯中文且长度足够的长词拆成 2-gram，覆盖标题中出现的子串
            if len(token) >= 4 and re.fullmatch(r"[一-鿿]+", token):
                keywords.extend(token[i:i + 2] for i in range(len(token) - 1))
            else:
                keywords.append(token)
        return keywords

    @classmethod
    def _is_relevant(cls, query: str, title: str, snippet: str) -> bool:
        """基于关键词覆盖率做可解释的相关性判断。

        至少命中一个查询关键词才认为相关，用于过滤完全无关的结果
        （例如查询「故宫 天坛」却返回「b站三连」这类结果）。
        """
        keywords = cls._extract_keywords(query)
        if not keywords:
            return True
        haystack = (title or "") + " " + (snippet or "")
        haystack_lower = haystack.lower()
        matched = sum(1 for kw in keywords if kw.lower() in haystack_lower)
        return matched >= 1

    @classmethod
    def _detect_blocked_page(cls, html: str, result_count: int) -> bool:
        """识别验证码、反爬或异常页面。"""
        if result_count == 0:
            lowered = html.lower()
            for marker in _BLOCKED_MARKERS:
                if marker.lower() in lowered:
                    return True
        return False

    @staticmethod
    def _normalize_url(url: str) -> str:
        """补全相对路径，并过滤无协议、非 http(s) 的链接。"""
        if not url:
            return ""
        url = url.strip()
        if url.startswith("//"):
            return "https:" + url
        if url.startswith("/"):
            return "https://www.bing.com" + url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ""
        return url

    async def invoke(self, query: str, date_range: Optional[str] = None) -> ToolResult[SearchResults]:
        """根据传递的query + date_range调用bing搜索获取搜索内容"""
        # 1.构建请求参数
        params = {"q": query}

        date_range = date_range or "all"
        if date_range:
            # 2.获取当前日期距离1970-01-01的天数
            days_since_epoch = int(time.time() / (24 * 60 * 60))

            # 3.创建日期检索日期映射
            date_mapping = {
                "past_hour": "ex1%3a\"ez1\"",
                "past_day": "ex1%3a\"ez1\"",
                "past_week": "ex1%3a\"ez2\"",
                "past_month": "ex1%3a\"ez3\"",
                "past_year": f"ex1%3a\"ez5_{days_since_epoch-365}_{days_since_epoch}\"",
            }
            if date_range in date_mapping:
                params["filters"] = date_mapping[date_range]

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                cookies=self.cookies,
                timeout=60,
                follow_redirects=True,
            ) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                self.cookies.update(response.cookies)

                soup = BeautifulSoup(response.text, "html.parser")
                result_items = soup.find_all("li", class_="b_algo")

                # 检测验证码/反爬页面
                if self._detect_blocked_page(response.text, len(result_items)):
                    return ToolResult(
                        success=False,
                        message="Bing 返回了验证码/反爬页面，无法获取有效搜索结果",
                    )

                parsed_results: List[SearchResultItem] = []
                for item in result_items:
                    try:
                        title, url = ("", "")
                        title_tag = item.find("h2")
                        if title_tag:
                            a_tag = title_tag.find("a")
                            if a_tag:
                                title = a_tag.get_text(strip=True)
                                url = a_tag.get("href", "")

                        if not title:
                            a_tags = item.find_all("a")
                            for a_tag in a_tags:
                                text = a_tag.get_text(strip=True)
                                if len(text) > 10 and not text.startswith("http"):
                                    title = text
                                    url = a_tag.get("href", "")
                                    break

                        if not title:
                            continue

                        snippet = ""
                        snippet_items = item.find_all(
                            ["p", "div"],
                            class_=re.compile(r"b_lineclamp|b_descrip|b_caption"),
                        )
                        if snippet_items:
                            snippet = snippet_items[0].get_text(strip=True)

                        if not snippet:
                            p_tags = item.find_all("p")
                            for p in p_tags:
                                text = p.get_text(strip=True)
                                if len(text) > 20:
                                    snippet = text
                                    break

                        if not snippet:
                            all_text = item.get_text(strip=True)
                            sentences = re.split(r"[.!?\n。！]", all_text)
                            for sentence in sentences:
                                clean_sentence = sentence.strip()
                                if len(clean_sentence) > 20 and clean_sentence != title:
                                    snippet = clean_sentence
                                    break

                        url = self._normalize_url(url)
                        if not url:
                            continue

                        parsed_results.append(SearchResultItem(
                            url=url,
                            title=title,
                            snippet=snippet,
                        ))
                    except Exception as e:
                        logger.warning(f"bing搜索结果解析失败:{str(e)}")
                        continue

                raw_count = len(parsed_results)

                # 过滤无关结果、空 URL 和重复 URL
                seen_urls = set()
                filtered_results: List[SearchResultItem] = []
                for result in parsed_results:
                    if result.url in seen_urls:
                        continue
                    seen_urls.add(result.url)
                    if self._is_relevant(query, result.title, result.snippet):
                        filtered_results.append(result)

                # 提取总结果数
                total_results = 0
                result_stats = soup.find_all(string=re.compile(r"\d+[, \d+]\s*results"))
                if result_stats:
                    for stat in result_stats:
                        match = re.search(r"([\d,]+)\s*results", stat)
                        if match:
                            try:
                                total_results = int(match.group(1).replace(",", ""))
                                break
                            except Exception:
                                continue
                if total_results == 0:
                    count_elements = soup.find_all(
                        ["span", "p", "div"],
                        class_=re.compile(r"sb_count|b_focusTextMedium"),
                    )
                    for element in count_elements:
                        text = element.get_text(strip=True)
                        match = re.search(r"([\d,]+)\s*results", text)
                        if match:
                            try:
                                total_results = int(match.group(1).replace(",", ""))
                                break
                            except Exception:
                                continue

                results = SearchResults(
                    query=query,
                    date_range=date_range,
                    total_results=total_results,
                    results=filtered_results,
                    provider="bing",
                    raw_count=raw_count,
                    filtered_count=len(filtered_results),
                )

                # 全部结果都不相关时返回明确失败，不返回空的伪成功
                if not filtered_results:
                    return ToolResult(
                        success=False,
                        message=f"Bing 未返回与查询相关的有效结果（原始 {raw_count} 条，过滤后 0 条）",
                        data=results,
                    )

                return ToolResult(success=True, data=results)
        except Exception as e:
            logger.error(f"Bing搜索出错：{str(e)}")
            error_result = SearchResults(
                query=query,
                date_range=date_range,
                total_results=0,
                results=[],
                provider="bing",
                raw_count=0,
                filtered_count=0,
            )
            return ToolResult(
                success=False,
                message=f"bing搜索出错：{str(e)}",
                data=error_result,
            )


if __name__ == "__main__":
    import asyncio

    async def test():
        search_engine = BingSearchEngine()
        result = await search_engine.invoke("小米股价", "past_day")
        print(result)
        for item in result.data.results:
            print(item)

    asyncio.run(test())
