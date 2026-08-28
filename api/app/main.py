from core.config import get_settings
from fastapi import FastAPI
from app.infrastructure.logging import setup_logging
import logging
from contextlib import asynccontextmanager
from app.interfaces.endpoints.routes import router
from fastapi.middleware.cors import CORSMiddleware
from app.interfaces.errors.exception_handlers import register_exception_handler
from app.infrastructure.storage.redis import get_redis
from app.infrastructure.storage.postgres import get_postgres
from app.infrastructure.storage.cos import get_cos
#1.加载配置信息

settings = get_settings()
#print(settings)

#2.初始化日志信息
setup_logging()
logger = logging.getLogger()
logger.info("测试")


#3.定义FastAPI路由tags标签
openapi_tags = [
    {
        "name":"状态模块",
        "description":"包含 **状态检测** 等api接口，用于检测系统运行状态",
    }
]


@asynccontextmanager
async def lifespan(app:FastAPI):
    """创建FastAPI应用程序生命周期上下文管理"""
    #1.打印日志表示程序开始了
    logger.info("MoocManus正在初始化")


    #2.初始化Redis、Postgres/Cos客户端
    await get_redis().init()
    await get_postgres().init()
    await get_cos().init()

    #todo 内容

    try:
        #3.lifespan节点/分解
        yield
    finally:
        #4.应用关闭时执行
        await get_redis().shutdown() 
        await get_postgres().shutdown()
        await get_cos().shutdown()
        logger.info("MoocManus正在关闭")

#4.创建MoocManus应用实例
app = FastAPI(
    title="MoocManus通用智能体",
    description="MoocManus是一个通用的AI Agent系统，可以完全私有部署，使用A2A+MCP链接Agent/Tools,同时支持在沙箱中运行各种内置工具和操作",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
    version="1.0.0"
) 

#5.配置CORS中间件 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # 与 allow_origins=["*"] 同时为 True 会被浏览器拒绝
    allow_methods=["*"],
    allow_headers=["*"]
)

#6.注册错误处理器
register_exception_handler(app)

#7.集成路由 
app.include_router(router,prefix="/api")