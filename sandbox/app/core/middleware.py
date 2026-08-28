import logging

from fastapi import Request

from app.core.config import get_settings
from app.interfaces.service_dependencies import get_supervisor_service 


logger = logging.getLogger(__name__)

async def auto_extend_timeout_middleware(request:Request, call_next):
    """有效 API 操作后，将空闲销毁期限重置为完整 TTL。"""
    #1.获取系统配置与supervisor服务
    settings = get_settings()
    supervisor_service = get_supervisor_service()

    #2.判断逻辑，仅在符合条件时延长超时销毁时间3分钟
    ignore_paths = (
        "/api/supervisor/activate-timeout",
        "/api/supervisor/extend-timeout",
        "/api/supervisor/cancel-timeout",
        "/api/supervisor/timeout-status",
        # Docker healthcheck 和 API 启动探测不能被视为用户活动，否则永不回收。
        "/api/supervisor/status",
    )
    if (
        settings.server_timeout_minutes is not None 
        and supervisor_service.timeout_active
        and request.url.path.startswith("/api")
        and not request.url.path.startswith(ignore_paths)
        and supervisor_service.expand_enabled
    ):
        try:
            await supervisor_service.activate_timeout(settings.server_timeout_minutes)
            logger.debug(f"Sandbox 活动后重置空闲销毁时间：{request.url}")
        except Exception as e:
            logger.warning(f"自动延长超时失败：{str(e)}")

    response = await call_next(request)
    return response
