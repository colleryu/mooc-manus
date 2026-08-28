
import logging

from sqlalchemy.ext.asyncio import AsyncEngine,AsyncSession,async_sessionmaker,create_async_engine
from typing import Optional
from core.config import get_settings
from functools import lru_cache
from sqlalchemy import text
logger = logging.getLogger(__name__)


class Postgres:
    """Postgres数据库基础类，用于完成数据库链接配置等操作"""

    def __init__(self):
        """构造函数，完成postgres数据库初始化"""
        self._engine : Optional[AsyncEngine] = None
        self._session_factory : Optional[async_sessionmaker] = None
        self._settings = get_settings()


    async def init(self)->None:


        """初始化postgres链接"""
        #1.判断是否已经创建好引擎，如果连接上则中断程序
        if self._engine is not None:
            logger.warning(f"Postgres已经初始化，无需重复操作")
            return

        try:
            #2.创建异步引擎
            logger.info("正在初始化Postgres链接...")
            self._engine = create_async_engine(
                self._settings.sqlalchemy_database_url,
                # 默认关闭 SQL 回显，避免输出完整 SQL 和参数导致日志量膨胀
                echo=False,
            )

            #3.创建会话工厂
            self._session_factory = async_sessionmaker(
                autoflush=False,
                autocommit=False,
                bind=self._engine,
            )
            logger.info(f"Postgres会话工厂创建完毕")

            #4.链接Postgres并执行预操作
            async with self._engine.begin() as async_conn:
                #5.检查是否安装了uuid扩展，如果没有的话就安装
                await async_conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')) 
                logger.info("成功链接Postgres并安装uuid-ossp扩展")

        except Exception as e:
            logger.error(f"链接Postgress失败：{str(e)}")
            raise

    async def shutdown(self)->None:
        """关闭Postgres链接"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("成功关闭Postgres链接")

        get_postgres.cache_clear()


    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """只读属性，返回初始化的会话工厂"""  
        if self._session_factory is None:
            raise RuntimeError("Postgres未初始化，请先调用init()函数初始化")
        return self._session_factory
    

@lru_cache
def get_postgres()->Postgres:
    """使用lru_cache实现单例模式，获得Postgres实例"""
    return Postgres()

async def get_db_session()->AsyncSession:
    """FastAPI依赖项，用于在每个请求中异步获取数据库会话实例，确保会话在正确使用后关闭"""
    #1.获得引擎和会话工厂
    db = get_postgres()
    session_factory = db.session_factory


    #2.创建会话上下文，在上下文内完成数据交换
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as _:
            await session.rollback()
            raise
