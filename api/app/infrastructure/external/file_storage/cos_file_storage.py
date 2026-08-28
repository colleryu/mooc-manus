
from datetime import datetime
import logging
import os
from typing import BinaryIO, Tuple
import uuid

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool

from app.domain.external.file_storage import FileStorage
from app.domain.models.file import File
from app.domain.repositories.file_repository import FileRepository
from app.infrastructure.storage.cos import Cos


logger = logging.getLogger(__name__)

class CosFileStorage(FileStorage):
    """基于Cos的文件存储扩展"""

    def __init__(self,bucket:str, cos:Cos, file_repository:FileRepository)->None:
        super().__init__()
        """构造函数，完成cos文件存储桶扩展初始化"""
        self.bucket = bucket
        self.cos = cos
        self.file_repository = file_repository

    @staticmethod
    def _resolve_file_size(upload_file:UploadFile)->int:
        """计算文件真实大小。

        内部通过 BytesIO 构造的 UploadFile 不会填充 ``size``，此时使用
        seek/tell 兜底计算，不能假设 ``UploadFile.size`` 一定存在。
        """
        if upload_file.size is not None and upload_file.size >= 0:
            return upload_file.size
        try:
            file_obj = upload_file.file
            current = file_obj.tell()
            file_obj.seek(0, 2)
            size = file_obj.tell()
            file_obj.seek(current)
            return size
        except Exception:
            return 0

    @staticmethod
    def _rewind_file(file_obj:BinaryIO)->None:
        """将文件指针重置到起始位置，确保 COS 收到完整内容。"""
        try:
            file_obj.seek(0)
        except Exception:
            logger.warning("无法重置文件指针到起始位置，上传内容可能不完整")

    async def _delete_cos_object(self, cos_key:str)->None:
        """删除 COS 对象，用于数据库保存失败后的补偿清理。"""
        try:
            await run_in_threadpool(
                self.cos.client.delete_object,
                Bucket=self.bucket,
                Key=cos_key,
            )
            logger.info(f"补偿删除COS对象成功：{cos_key}")
        except Exception:
            logger.exception(f"补偿删除COS对象失败：{cos_key}")

    async def upload_file(self, upload_file:UploadFile)->File:
        """根据传递的文件源将文件上传到腾讯云cos。

        顺序保证原子性：先计算并校验 File 模型，再上传 COS，最后保存数据库；
        数据库保存失败时删除已上传对象，避免产生孤儿。
        """
        filename = upload_file.filename or ""
        content_type = upload_file.content_type or ""
        try:
            #1.生成随机的uuid文件id并获取文件扩展名
            file_id = str(uuid.uuid4())
            _, file_extension = os.path.splitext(filename)
            file_extension = file_extension.lower()

            #2.统一计算文件大小，不能依赖 UploadFile.size（内部构造时可能为 None）
            size = self._resolve_file_size(upload_file)

            #3.生成日期路径并拼接最终Key
            date_path = datetime.now().strftime("%Y/%m/%d")
            cos_key = f"{date_path}/{file_id}{file_extension}"

            #4.先构造并校验 File 模型，避免上传成功但模型校验失败留下孤儿对象
            file = File(
                id=file_id,
                filename=filename,
                key=cos_key,
                extension=file_extension,
                mime_type=content_type,
                size=size,
            )

            #5.确保文件指针位于起始位置后再上传
            self._rewind_file(upload_file.file)

            #6.使用fastapi的线程池来上传文件
            await run_in_threadpool(
                self.cos.client.put_object,
                Bucket=self.bucket,
                Body=upload_file.file,
                Key=cos_key,
            )
            logger.info(f"文件上传成功：{filename}(ID:{file_id})")

            #7.保存数据库记录，失败时删除已上传的 COS 对象作为补偿
            try:
                await self.file_repository.save(file=file)
            except Exception:
                logger.exception(f"文件[{filename}]数据库记录保存失败，触发补偿删除")
                await self._delete_cos_object(cos_key)
                raise
            return file
        except Exception as e:
            logger.error(f"上传文件[{filename}]失败：{str(e)}")
            raise


    async def download_file(self, file_id:str)->Tuple[BinaryIO,File]:
        """根据文件id查询数据并下载文件"""
        try:
            #1.查询对应的文件记录是否存在
            file= await self.file_repository.get_by_id(file_id=file_id)
            if not file:
                raise ValueError(f"该文件不存在，文件id：{file_id}")
            #2.使用线程池来下载文件
            reponse = await run_in_threadpool(
                self.cos.client.get_object,
                Bucket=self.bucket,
                Key=file.key,
            )
            #3.返回文件流+文件信息
            return reponse["Body"],file
        except Exception as e:
            logger.error(f"下载文件[{file_id}]失败：{str(e)}")
            raise