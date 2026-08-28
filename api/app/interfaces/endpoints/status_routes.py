

import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from app.application.services.status_service import StatusService
from app.interfaces.schemas import Response
from app.domain.models.health_status import HealthStatus    
from typing import List

from app.interfaces.service_dependencies import get_status_service


logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/status",
    tags=["状态模块"],
)

@router.get(
    path="",
    response_model= Response,
    summary="系统健康检查",
    description="检查系统的postgres、redis、fastapi等组件的状态"
)
async def get_status(
    status_service:StatusService = Depends(get_status_service),
)->Response:
    """系统健康检查，检查postgres/redis/fastapi等"""

    statues = await status_service.check_all()

    if any(item.status == "error" for item in statues):
        return JSONResponse(
            status_code=503,
            content=Response.fail(code=503, msg="系统存在服务异常", data=statues).model_dump(),
        )
    #todo 等待postgres/redis等服务接入后补全代码

    return Response.success(msg="系统健康检查成功", data=statues)