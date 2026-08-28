

"""
1.supervisor启动后通过以unix太湖额字文件来实现通信(rpc协议)
2.链接这个通信文件，/tmp/supervisor.sock(xml-rpc链接)
3.使用某种方式来完成转换，让xml-rpc实现链接supervisor.sock
4.链接之后我们就可以调用rpc对应的方法，getAllProcessInfo()
"""
import asyncio
from datetime import datetime, timedelta
import http
import logging

import socket
import threading
from typing import Any, List, Optional
import xmlrpc.client

from app.interfaces.errors.exceptions import AppException, BadRequestException
from app.models.supervisor import ProcessInfo, SupervisorActionResult, SupervisorTimeoutResult
from app.core.config import get_settings
    
logger = logging.getLogger(__name__)

class UnixStreamHttpConnection(http.client.HTTPSConnection):
    """基于unix流的http链接处理器"""
    def __init__(self,host:str, socket_path:str, timeout = None)->None:
        """构造函数，完成连接处理器初始化"""
        http.client.HTTPConnection.__init__(self,host,timeout)
        self.socket_path = socket_path

    def connect(self)->None:
        """重写链接方法，欺骗xml-rpc库让其觉得自己正在进行网络链接"""
        self.sock =socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


class UnixStreamTransport(xmlrpc.client.Transport):
    """基于Unix流传输层的适配器/转换器"""
    def __init__(self,socket_path:str):
        """构造函数，完成传输适配器的初始化"""
        xmlrpc.client.Transport.__init__(self)
        self.socket_path = socket_path
    def make_connection(self,host)->http.client.HTTPConnection:
        return UnixStreamHttpConnection(host,self.socket_path)

class SupervisorService:
    """Supervisor服务"""

    def __init__(self):
        """构造函数，完成supervisor服务链接"""
        #1.链接supervisor配置
        self.rpc_url = "/tmp/supervisor.sock"
        self._connect_rpc()
        #2.supervisor超时配置
        settings = get_settings()
        self.timeout_active = settings.server_timeout_minutes is not None
        self.shutdown_task = None
        self.shutdown_time = None
        self.shutdown_timer = None
        self._expand_enabled = True #是否自动保活(每调用一次接口，旧增加时间)

        #3.检测是否配置了自动销毁
        if settings.server_timeout_minutes is not None:
            #4.设置销毁时间 + 定时器
            self.shutdown_time = datetime.now() + timedelta(minutes=settings.server_timeout_minutes)
            self._setup_timer(settings.server_timeout_minutes)

    @property
    def expand_enabled(self)->bool:
        """只读属性，返回是否自动保活"""
        return self._expand_enabled

    def enable_expand(self)->None:
        """开启自动保活"""
        self._expand_enabled = True

    def disable_expand(self)->None:
        """关闭自动保活"""
        self._expand_enabled = False

    def _setup_timer(self,minutes:int)->None:
        """传递时间(分钟)并创建定时器，在时间结束之后关闭supervisord主进程"""
        #1.检测当前是否存在销毁任务 ，如果存在则先取消
        if self.shutdown_task:
            try:
                self.shutdown_task.cancel()
            except Exception as e:
                logger.error(f"取消shutdown任务失败：{str(e)}")

        #2.创建一个异步定时器任务函数
        async def shutdown_after_timeout():
            await asyncio.sleep(minutes * 60)
            await self.shutdown()
        try:
            #3.获取时间循环并添加任务
            loop = asyncio.get_event_loop()
            self.shutdown_task = loop.create_task(shutdown_after_timeout())

        except Exception as e:
            #4.如果时间循环失败则创建一个新的线程来执行定时器
            if hasattr(self, "shutdown_timer") and self.shutdown_timer:
                self.shutdown_timer.cancel()
            #5.使用线程创建关闭定时器并设置在后台运行
            self.shutdown_timer = threading.Timer(
                minutes*60,
                lambda: asyncio.run(self.shutdown())
            )
            self.shutdown_timer.daemon = True
            self.shutdown_timer.start()

    async def cancel_timeout(self)->SupervisorTimeoutResult:
        """取消超时销毁设置"""
        #1.判断是否设置了超时销毁
        if not self.timeout_active:
            return SupervisorTimeoutResult(status="no_timeout_active",activate=False)

        #2.取消销毁任务
        if self.shutdown_task:
            try:
                self.shutdown_task.cancel()
                self.shutdown_task = None
            except Exception as e:
                logger.error(f"取消shutdown任务失败：{str(e)}")

        #3.同步检查是否存在定时器
        if hasattr(self, 'shutdown_timer') and self.shutdown_timer:
            self.shutdown_timer.cancel()
            self.shutdown_timer = None

        #4.跟新超时配置
        self.timeout_active = False
        self.shutdown_time = None
        self._expand_enabled = True
        return SupervisorTimeoutResult(status="timeout_cancelled",activate=False)

    async def get_timeout_status(self)->SupervisorTimeoutResult:
        """获取当前supervisor的超时状态"""
        #1.判断是否开启了超时销毁功能
        if not self.timeout_active:
            return SupervisorTimeoutResult(activate=False)

        #2.统计剩余描秒数
        remaining_seconds = 0
        if self.shutdown_time:
            remaining = self.shutdown_time - datetime.now()
            remaining_seconds = max(0,remaining.total_seconds())
        return SupervisorTimeoutResult(
            activate=self.timeout_active,
            shutdown_time=self.shutdown_time.isoformat() if self.shutdown_time else None,
            remaining_seconds=remaining_seconds,
        )

    def _connect_rpc(self)->None:
        """使用python的xml-rpc客户端链接一个本地sock文件文件实现链接rpc服务"""
        try:
            self.server = xmlrpc.client.ServerProxy(
                "http://localhost",
                transport=UnixStreamTransport(self.rpc_url),
            )
        except Exception as e:
            logger.error(f"链接Supervisor服务失败：{str(e)}")
            raise BadRequestException(f"链接Supervisor服务失败：{str(e)}")

    async def activate_timeout(
            self,
            minutes: Optional[int] = None
    )->SupervisorTimeoutResult:
        """传递直定分钟，并激活定时销毁任务同时关闭自动保活"""
        #1.获取超时分钟数
        settings = get_settings()
        timeout_minutes = minutes or settings.server_timeout_minutes
        if timeout_minutes is None:
            raise BadRequestException(f"超时时间未配置，并且未读取到系统默认超时时间")

        #2.跟新超时配置
        self.timeout_active = True
        self.shutdown_time = datetime.now() + timedelta(minutes=timeout_minutes)

        #3.创建一个新的定时器
        self._setup_timer(timeout_minutes)
        return SupervisorTimeoutResult(
            status="timeout activated",
            activate=True,
            shutdown_time=self.shutdown_time.isoformat(),
            timeout_minutes=timeout_minutes,
            remaining_seconds=(self.shutdown_time - datetime.now()).total_seconds(),   
        )

    async def extend_timeout(
            self,
            minutes:Optional[int] = 3
    )->SupervisorTimeoutResult:
        """传递指定时长，延长超时销毁的时间，单默认延长3分钟"""
        #1.获取超时分钟数
        if minutes is None:
            raise BadRequestException(f"超时时间未配置，请设置后重试")
        remaining = self.shutdown_time - datetime.now()
        timeout_minutes = round(max(0, remaining.total_seconds())/60) + minutes

        #2.跟新超时配置
        self.timeout_active = True
        self.shutdown_time = datetime.now() + timedelta(minutes=timeout_minutes)

        #3.创建一个新的定时器
        self._setup_timer(timeout_minutes)
        return SupervisorTimeoutResult(
            status="timeout extended",
            activate=True,
            shutdown_time=self.shutdown_time.isoformat(),
            timeout_minutes=timeout_minutes,
            remaining_seconds=(self.shutdown_time - datetime.now()).total_seconds(),
        )

    @classmethod
    async def _call_rpc(cls, method,*args)->Any:
        """根据传递的方法 + 参数调用rpc方法"""
        try:
            return await asyncio.to_thread(method,*args)
        except Exception as e:
            logger.error(f"RPC方法调用失败：{str(e)}")
            raise BadRequestException(f"RPC方法调用失败：{str(e)}")

    async def get_all_processes(self)->List[ProcessInfo]:
        """获取当前supervisor管理的所有进程"""
        try:
            processes = await self._call_rpc(self.server.supervisor.getAllProcessInfo)
            return [ProcessInfo(**process) for process in processes]
        except Exception as e:
            logger.error(f"获取进程信息失败:{str(e)}")
            raise AppException(f"获取进程信息失败:{str(e)}")

    async def stop_all_processes(self)->SupervisorActionResult:
        """停止supervisor管理的所有进程"""
        try:
            result = await self._call_rpc(self.server.supervisor.stopAllProcesses)
            return SupervisorActionResult(
                status="stopped",
                result=result,
            )
        except Exception as e:
            logger.error(f"停止supervisor所有进程服务失败：{str(e)}")
            raise AppException(f"停止supervisor所有进程服务失败：{str(e)}")

    async def shutdown(self)->SupervisorActionResult:
        """关闭supervisord服务"""
        try:
            shutdown_result = await self._call_rpc(self.server.supervisor.shutdown)
            return SupervisorActionResult(
                status="shutdown",
                shutdown_result=shutdown_result,
            )
        except Exception as e:
            logger.error(f"关闭supervisord服务失败：{str(e)}")
            raise AppException(f"关闭supervisord服务失败：{str(e)}")

    async def restart(self)->SupervisorActionResult:
        """重启supervisor管理的进程"""
        try:
            stop_result = await self._call_rpc(self.server.supervisor.stopAllProcesses)
            start_result = await self._call_rpc(self.server.supervisor.startAllProcesses)
            return SupervisorActionResult(
                status="restarted",
                stop_result=stop_result,
                start_result=start_result,
            )
        except Exception as e:
            logger.error(f"重启Supervisor进程服务失败：{str(e)}")
            raise AppException(f"重启Supervisor进程服务失败：{str(e)}")