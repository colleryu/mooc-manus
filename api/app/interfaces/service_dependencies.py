
import logging
from functools import lru_cache
from app.application.services.app_config_service import AppConfigService
from app.application.services.file_service import FileService
from app.infrastructure.external.file_storage.cos_file_storage import CosFileStorage
from app.infrastructure.external.health_checker.postgres_health_checker import PostgresHealthChecker
from app.infrastructure.repositories.db_file_repository import DBFileRepository
from app.infrastructure.repositories.file_app_config_repository import FileAppConfigRepository
from app.application.services.status_service import StatusService
from app.application.services.session_service import SessionService
from app.infrastructure.storage.cos import Cos, get_cos
from app.infrastructure.storage.postgres import get_db_session
from app.infrastructure.storage.redis import RedisClient, get_redis
from app.infrastructure.external.health_checker.redis_health_checker import RedisHealthChecker
from core.config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache()
def get_app_config_service()->AppConfigService:
    """获取应用配置服务"""
    #1.获取数据仓库并打印日志
    logger.info("加载获取AppConfigService")

    file_app_config_repository = FileAppConfigRepository(settings.app_config_filepath)

    #2.实例化AppConfigService
    return AppConfigService(app_config=file_app_config_repository)


def get_status_service(
    db_session : AsyncSession = Depends(get_db_session),
    redis_client: RedisClient = Depends(get_redis),
)->StatusService:
    """获取状态服务"""
    #1.初始化postgres和redis健康检查
    postgres_checker = PostgresHealthChecker(db_session)
    redis_checker = RedisHealthChecker(redis_client)

    #2.创建服务并返回
    logger.info("加载获取StatusService")
    return StatusService(
        checkers=[postgres_checker,redis_checker]
    )

def get_file_service(
    cos:Cos = Depends(get_cos),
    db_session: AsyncSession = Depends(get_db_session),

)->FileService:
    #1.初始化文件仓库和文件存储桶
    file_repository = DBFileRepository(db_session=db_session)
    file_storage = CosFileStorage(
        bucket=settings.cos_bucket,
        cos=cos,
        file_repository=file_repository
    )
    #2.构建服务并且返回
    return FileService(
        file_storage=file_storage,
        file_repository=file_repository
    )


def get_session_service(
    db_session: AsyncSession = Depends(get_db_session),
    cos: Cos = Depends(get_cos),
)->SessionService:
    return SessionService(
        db_session=db_session,
        cos=cos,
        settings=settings,
        app_config_service=get_app_config_service(),
    )
