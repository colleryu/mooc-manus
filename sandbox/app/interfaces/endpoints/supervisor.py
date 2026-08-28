from fastapi import APIRouter,Depends
from typing import List
from app.interfaces.schema.base import Response
from app.interfaces.schema.supervisor import TimeoutRequest
from app.interfaces.service_dependencies import get_supervisor_service
from app.models.supervisor import ProcessInfo, SupervisorActionResult, SupervisorTimeoutResult
from app.services.supervisor import SupervisorService

router = APIRouter(prefix="/supervisor",tags=["Supervisor模块"])

@router.get(
    path="/status",
    response_model=Response[List[ProcessInfo]]
)
async def get_status(
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[List[ProcessInfo]]:
    """获取沙箱中所有进程服务的状态"""
    processes = await supervisor_service.get_all_processes()
    return Response.success(
        msg="获取沙箱进程服务成功",
        data=processes
    )


@router.post(
    path="/stop-all-processes",
    response_model=Response[SupervisorActionResult],
)
async def stop_all_processes(
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorActionResult]:
    """停止所有supervisor进程管理"""
    result = await supervisor_service.stop_all_processes()
    return Response.success(
        msg="停止Supervisor所有进程服务成功",
        data=result,
    )

@router.post(
    path="/shutdown",
    response_model=Response[SupervisorActionResult],
)
async def shutdown(
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorActionResult]:
    """关闭supervisor服务本身"""
    result = await supervisor_service.shutdown()
    return Response.success(
        msg="Supervisor关闭成功",
        data=result,
    )

@router.post(
    path="/restart",
    response_model=Response[SupervisorActionResult],
)
async def restart(
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorActionResult]:
    """重启supervisor管理的所有子进程"""
    result = await supervisor_service.restart()
    return Response.success(
        msg="重启Supervisor重启所有进程成功",
        data=result,
    )

@router.post(
    path="/activate-timeout",
    response_model=Response[SupervisorTimeoutResult],
)
async def activate_timeout(
    request:TimeoutRequest,
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorTimeoutResult]:
    """传递分钟激活超时沙箱销毁设置，并关闭自动保活配置"""
    result = await supervisor_service.activate_timeout(request.minutes)
    supervisor_service.disable_expand()
    return Response.success(
        msg=f"超时销毁已设置，所有服务在沙箱将在{result.timeout_minutes}分钟后销毁",
        data=result
    )


@router.post(
    path="/extend-timeout",
    response_model=Response[SupervisorTimeoutResult],
)
async def extend_timeout(
    request: TimeoutRequest,
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorTimeoutResult]:
    """传递指定的分钟延长超时时间并关闭自动保活"""
    result = await supervisor_service.extend_timeout(request.minutes)
    supervisor_service.disable_expand()
    return Response.success(
        msg=f"超时销毁时间已延长{request.minutes}分钟，所有服务与沙箱将在{result.timeout_minutes}后被销毁",
        data=result
    )


@router.post(
    path="/cancel-timeout",
    response_model=Response[SupervisorTimeoutResult],
)
async def cancel_timeout(
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorTimeoutResult]:
    """取消超时销毁配置"""
    result = await supervisor_service.cancel_timeout()
    return Response.success(
        msg="超时销毁已取消" if result.status == "timeout_cancelled" else "超时销毁未取消",
        data=result,
    )


@router.get(
    path="/timeout-status",
    response_model=Response[SupervisorTimeoutResult],
)
async def get_timeout_status(
    supervisor_service:SupervisorService = Depends(get_supervisor_service),
)->Response[SupervisorTimeoutResult]:
    """获取当前supervisor的超时状态配置"""
    result = await supervisor_service.get_timeout_status()

    msg="未激活超时销毁" if not result.activate else f"剩余超时销毁分钟数：{result.remaining_seconds//60}"
    return Response.success(
        msg=msg,
        data=result,
    )
