from typing import Protocol,List

from app.domain.models.health_status import HealthStatus


class HealthChecker(Protocol):
    """服务健康检查协议"""
    async def check(self)->HealthStatus:
        """"用于检查对应协议是否健康"""
        ...
