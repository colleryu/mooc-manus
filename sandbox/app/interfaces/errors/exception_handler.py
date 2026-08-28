

import logging
from fastapi import FastAPI,Request,status
from .exceptions import AppException
from fastapi.responses import JSONResponse
from app.interfaces.schema.base import Response
from starlette.exceptions import HTTPException
logger = logging.getLogger(__name__)

def register_exception_handler(app:FastAPI)->None:

    @app.exception_handler(AppException)
    async def app_exception_handler(req:Request, e:AppException)->JSONResponse:
        """处理moocManus沙箱自定义业务异常，将所有状态统一响应结构"""
        logger.error(f"Appexception:{e.msg}")
        return JSONResponse(
            status_code=e.status_code,
            content=Response(
                code=e.status_code,
                msg=e.msg,
                data={}
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(req:Request, e:HTTPException):
        """处理FastAPI抛出的http异常，将所有状态统一响应结构"""
        logger.error(f"HTTPException：{e.detail}")

        return JSONResponse(
            status_code=e.status_code,
            content=Response(
                code=e.status_code,
                msg=e.detail,
                data={},
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def exception_handler(req: Request, e:Exception):
        """处理MoocManus沙箱服务总抛出的任意未定义异常，将所有状态码统一响应格式"""
        logger.error(f"Exception:{e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=Response(
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                msg="服务器出现异常请稍后重试",
                data={}
            ).model_dump(),
        )