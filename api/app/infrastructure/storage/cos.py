

import logging
from core.config import Settings, get_settings
from typing import Optional
from qcloud_cos import CosS3Client,CosConfig
from functools import lru_cache
logger = logging.getLogger(__name__)

class Cos:
    """腾讯云Cos对象存储"""
    def __init__(self):
        """构造函数，完成配置获取+Cos客户端初始化赋值"""
        self._settings:Settings = get_settings()
        self._client: Optional[CosS3Client] = None

    async def init(self)->None:
        """完成cos腾讯云对象存储客户端的创建"""
        #1.判断客户端是否粗存在，如果存在则记录日志并终止程序
        if self._client is not None:
            logger.warning(f"腾讯云对象存储已经初始化，无需重复操作")
            return
        try:
            #2.创建cos配置
            config = CosConfig(
                Region=self._settings.cos_region,
                SecretId=self._settings.cos_secret_id,
                SecretKey=self._settings.cos_secret_key,
                Token=None ,
                Scheme=self._settings.cos_scheme,

            )
            self._client = CosS3Client(config)
            logger.info("Cos腾讯云对象存储初始化成功")

        except Exception as e:
            logger.error(f"Cos腾讯云对象存储初始化失败：{str(e)}")
            raise 


    async def shutdown(self)->None:
        """关闭Cos腾讯云对象存储"""
        if self._client is not None:
            self._client = None
            logger.info("关闭腾讯云Cos对象存储成功")
        get_cos.cache_clear()

    @property
    def client(self)->CosS3Client:
        """只读属性，返回腾讯云Cos对象存储客户端"""
        if self._client is None:
            raise RuntimeError("腾讯云Cos对象存储未初始化，请调用init()完成初始化")
        return self._client



@lru_cache
def get_cos()->Cos:
    """使用lru_cache实现单例模式，获得腾讯cos对象存储"""
    return Cos( )