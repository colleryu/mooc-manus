import asyncio

from app.infrastructure.external.search import bing_search
from app.infrastructure.external.search.bing_search import BingSearchEngine


class FakeResponse:
    text = """
    <html><body>
      <li class="b_algo">
        <h2><a href="https://example.com/gold">今日黄金价格</a></h2>
        <p>这里是超过二十个字符的黄金价格测试摘要信息。</p>
      </li>
    </body></html>
    """
    cookies = {}

    def raise_for_status(self):
        return None


class FakeAsyncClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, params):
        return FakeResponse()


def test_search_without_date_range_still_invokes_bing(monkeypatch):
    monkeypatch.setattr(bing_search.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(BingSearchEngine().invoke("今日黄金价格"))

    assert result is not None
    assert result.success is True
    assert result.data.query == "今日黄金价格"
    assert result.data.results[0].url == "https://example.com/gold"


class IrrelevantFakeResponse:
    text = """
    <html><body>
      <li class="b_algo">
        <h2><a href="https://example.com/x">b站三连是什么意思</a></h2>
        <p>这是哔哩哔哩网站的科普内容，介绍弹幕互动机制。</p>
      </li>
      <li class="b_algo">
        <h2><a href="https://example.com/y">MSDN系统库下载</a></h2>
        <p>Windows系统下载网站与Office下载资源。</p>
      </li>
    </body></html>
    """
    cookies = {}

    def raise_for_status(self):
        return None


class IrrelevantFakeAsyncClient:
    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def get(self, url, params):
        return IrrelevantFakeResponse()


def test_irrelevant_results_are_filtered_and_fail(monkeypatch):
    monkeypatch.setattr(bing_search.httpx, "AsyncClient", IrrelevantFakeAsyncClient)

    result = asyncio.run(BingSearchEngine().invoke("故宫 天坛 开放时间"))

    assert result.success is False
    assert result.data.results == []
    assert result.data.provider == "bing"
    assert result.data.raw_count == 2
    assert result.data.filtered_count == 0


def test_is_relevant_keyword_coverage():
    # 完全无关的标题/摘要应判定为不相关
    assert BingSearchEngine._is_relevant("北京 故宫 天坛", "b站三连是什么意思", "哔哩哔哩科普") is False
    # 标题包含查询关键词时应判定为相关
    assert BingSearchEngine._is_relevant("北京 故宫 天坛", "故宫博物院开放时间", "故宫门票预约") is True
    # 无关键词可提取时不误杀
    assert BingSearchEngine._is_relevant("", "任意标题", "任意摘要") is True
