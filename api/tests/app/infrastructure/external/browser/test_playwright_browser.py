import os

from app.infrastructure.external.browser.playwright_borwser import ensure_cdp_bypasses_proxy


def test_ensure_cdp_bypasses_proxy_preserves_existing_entries(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.delenv("no_proxy", raising=False)

    ensure_cdp_bypasses_proxy("http://172.17.0.5:9222")
    ensure_cdp_bypasses_proxy("http://172.17.0.5:9222")

    entries = os.environ["NO_PROXY"].split(",")
    assert entries == ["localhost", "127.0.0.1", "172.17.0.5"]
    assert os.environ["no_proxy"] == os.environ["NO_PROXY"]
