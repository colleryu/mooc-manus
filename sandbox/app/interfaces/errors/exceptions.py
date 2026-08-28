import logging
from fastapi import status
from typing import Any
logger = logging.getLogger(__name__)


class AppException(Exception):
    """应用基础异常"""
    def __init__(
            self,
            msg:str = "应用发送错误请稍后重试",
            status_code:int = status.HTTP_500_INTERNAL_SERVER_ERROR,
            data :Any = None,
            *args
    ):
        """构造函数，完成异常初始化"""
        #1.完成数据初始化
        self.msg = msg
        self.status_code = status_code
        self.data = data

        #2.记录日志并调用父类构造函数
        logger.error(f"沙箱发生错误：{msg}(code:{status_code})")
        super().__init__(self.msg)


class NotFoundException(AppException):
    """资源未找到异常"""
    def __init__(self, msg = "资源未找到，请核实后尝试", status_code = status.HTTP_404_NOT_FOUND, data = None, *args):
        super().__init__(msg, status_code, data, *args)


class BadRequestException(AppException):
    """错误请求异常"""
    def __init__(self, msg = "客户端请求错误，请检查后重试", status_code = status.HTTP_400_BAD_REQUEST, data = None, *args):
        super().__init__(msg, status_code, data, *args)

