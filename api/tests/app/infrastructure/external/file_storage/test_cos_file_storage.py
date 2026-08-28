import asyncio
import io

import pytest
from fastapi import UploadFile

from app.infrastructure.external.file_storage.cos_file_storage import CosFileStorage


class FakeCosClient:
    def __init__(self):
        self.put_calls = []
        self.delete_calls = []

    def put_object(self, Bucket, Body, Key):
        self.put_calls.append({"bucket": Bucket, "key": Key, "body": Body.read()})
        return {}

    def delete_object(self, Bucket, Key):
        self.delete_calls.append({"bucket": Bucket, "key": Key})
        return {}


class FakeCos:
    def __init__(self):
        self.client = FakeCosClient()


class FailingFileRepository:
    async def save(self, file):
        raise RuntimeError("数据库保存失败")

    async def get_by_id(self, file_id):
        return None


def test_resolve_file_size_with_bytesio_and_none_size():
    content = b"hello world" * 100
    upload = UploadFile(file=io.BytesIO(content), filename="guide.md")
    # 内部构造的 UploadFile 不会填充 size
    assert upload.size is None
    size = CosFileStorage._resolve_file_size(upload)
    assert size == len(content)


def test_upload_file_deletes_cos_object_on_db_failure():
    async def run():
        cos = FakeCos()
        storage = CosFileStorage(bucket="b", cos=cos, file_repository=FailingFileRepository())
        content = b"guide content"
        upload = UploadFile(file=io.BytesIO(content), filename="guide.md")

        with pytest.raises(RuntimeError):
            await storage.upload_file(upload)

        assert len(cos.client.put_calls) == 1
        assert len(cos.client.delete_calls) == 1
        # 补偿删除的 key 必须与已上传对象的 key 一致
        assert cos.client.delete_calls[0]["key"] == cos.client.put_calls[0]["key"]

    asyncio.run(run())


def test_upload_file_reads_complete_content_from_start():
    async def run():
        cos = FakeCos()
        storage = CosFileStorage(bucket="b", cos=cos, file_repository=FailingFileRepository())
        content = b"abcdefgh"
        upload = UploadFile(file=io.BytesIO(content), filename="x.txt")

        with pytest.raises(RuntimeError):
            await storage.upload_file(upload)

        # 上传前文件指针已重置，COS 收到完整内容
        assert cos.client.put_calls[0]["body"] == content

    asyncio.run(run())
