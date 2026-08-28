

from functools import lru_cache
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.repositories.db_session_repository import DBSessionRepository
from app.infrastructure.storage.postgres import get_db_session
import logging

logger = logging.getLogger(__name__)



def get_db_session_repository(
    db_session: AsyncSession = Depends(get_db_session),
)->DBSessionRepository:
    """基于数据库的会话数据仓库"""
    logger.info("加载获取DBSessionRepository")
    return DBSessionRepository(dbsession=db_session)