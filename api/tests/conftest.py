
import pytest

from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session")
def client()->TestClient:
    """
    创建一个可提供所有测试用例的 TestClient 客户端。
    scope="session" 表示这个fixture 在整个测试用例只会用一次，这样可以提高效率
    """
    with TestClient(
        app 
    ) as c:
        yield c