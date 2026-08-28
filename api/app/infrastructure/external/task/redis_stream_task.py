import uuid
from typing import Optional,Dict
import asyncio
from app.domain.external.message_queue import MessageQueue
from app.domain.external.task import Task, TaskRunner
from app.infrastructure.external.message_queue.redis_stream_message_queue import RedisStreamMessageQueue
import logging
from contextlib import suppress


logger = logging.getLogger(__name__)

class RedisStreamTask(Task):
    """基于redis流的任务类"""
    #定义给全局变量用于存储所有已注册的任务
    _task_registy : Dict[str,"RedisStreamTask"] = {}

    def __init__(self, task_runner:TaskRunner)->None:
        """构造函数，传递任务运行器完成Task初始化"""
        super().__init__()
        self._task_runner = task_runner
        self._id = str(uuid.uuid4())
        self._execution_task : Optional[asyncio.Task] =None #定义后台执行的任务

        input_stream_name = f"task:input:{self._id}"
        output_stream_name = f"task:output:{self._id}"

        self._input_stream = RedisStreamMessageQueue(input_stream_name)
        self._output_stream = RedisStreamMessageQueue(output_stream_name)

        #将当前类实例注册到全局变量中
        RedisStreamTask._task_registy[self._id] = self



    async def _cleanup_registry(self)->None:
        """清除类全局变量中当前注册的任务"""
        if self._id in RedisStreamTask._task_registy:
            del RedisStreamTask._task_registy[self._id]
            logger.info(f"任务[{self._id}]从注册中心移除")
            



    async def _on_task_done(self)->None:
        """任务结束时的回调函数"""
        #1.检测task_runner是否存在
        if self._task_runner:
            await self._task_runner.on_done(self)

        #2.清除当前任务对应的资源
        await self._cleanup_registry()


    async def _execute_task(self):
        """使用taskrunner来运行任务"""
        try:
            await self._task_runner.invoke(self)
        except asyncio.CancelledError:
            logger.info(f"任务{self._id}执行被取消")

        except Exception as e:
            logger.error(f"任务{self._id}执行出现异常：{str(e)}")
        finally:
            await self._on_task_done()


    async def invoke(self)->None:
        """使用提供的task_runner来运行任务"""

        #1.判断任务是否已结束，未结束则启动后台执行任务
        if self._execution_task is None or self._execution_task.done():
            self._execution_task = asyncio.create_task(self._execute_task())
            logger.info(f"任务[{self._id}]开始执行")


    def cancel(self) -> None:
        """取消当前执行的任务"""
        if self._execution_task is not None and not self._execution_task.done():
            #1.取消任务
            self._execution_task.cancel()
            logger.info(f"任务：[{self._id}]已经取消")

        #2.清除注册的当前任务
        RedisStreamTask._task_registy.pop(self._id, None)
        logger.info(f"任务[{self._id}]从注册中心移除")

    async def stop(self, destroy_runner: bool = True)->None:
        """取消任务并等待后台协程结束。

        ``destroy_runner`` 为真时同时销毁运行器拥有的会话级资源。用户仅停止
        当前任务时应传入假值，以便后续消息继续复用同一个 Sandbox。
        """
        execution_task = self._execution_task
        self.cancel()
        if execution_task is not None:
            with suppress(asyncio.CancelledError):
                await execution_task
        if destroy_runner and self._task_runner:
            await self._task_runner.destroy()

    @property
    def input_stream(self)->MessageQueue:
        return self._input_stream

    @property
    def output_stream(self)->MessageQueue:
        return self._output_stream

    @property
    def id(self)->str:
        return self._id

    @property
    def done(self) -> bool:
        if self._execution_task is None:
            return True
        return self._execution_task.done()


    @classmethod
    def get(cls, task_id:str)->Optional["Task"]:
        return RedisStreamTask._task_registy.get(task_id)

    @classmethod
    def create(cls, task_runner:TaskRunner)->"Task":
        return cls(task_runner)


    @classmethod
    async def destory(cls):
        for task_id in list(RedisStreamTask._task_registy):
            #1.获取对应的任务
            task = RedisStreamTask._task_registy[task_id]
            task.cancel()


            #2.检测任务是否有任务运行器
            if task._task_runner:
                await task._task_runner.destroy()


        #3.清除全局变量
        cls._task_registy.clear()
