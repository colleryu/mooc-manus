import asyncio
import json
import os
import urllib.parse
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.application.errors.exceptions import NotFoundError
from app.application.services.session_service import SessionService
from app.domain.models.event import DoneEvent
from app.domain.models.session import Session
from app.infrastructure.external.task.redis_stream_task import RedisStreamTask
from app.interfaces.schemas.base import Response
from app.interfaces.schemas.session import CreateSessionRequest, SendMessageRequest
from app.interfaces.service_dependencies import get_session_service


router = APIRouter(prefix="/sessions", tags=["会话模块"])


@router.get("", response_model=Response[list[Session]])
async def list_sessions(service: SessionService = Depends(get_session_service)):
    return Response.success(data=await service.list_sessions())


@router.post("", response_model=Response[Session])
async def create_session(
    body: CreateSessionRequest,
    service: SessionService = Depends(get_session_service),
):
    return Response.success(data=await service.create_session(body.title), msg="创建会话成功")


@router.get("/{session_id}", response_model=Response[Session])
async def get_session(session_id: str, service: SessionService = Depends(get_session_service)):
    return Response.success(data=await service.get_session(session_id))


@router.get("/{session_id}/files", response_model=Response[list[dict[str, str]]])
async def list_generated_files(
    session_id: str,
    service: SessionService = Depends(get_session_service),
):
    files = await service.list_generated_files(session_id)
    return Response.success(data=files, msg="获取任务生成文件成功")


@router.get("/{session_id}/files/download")
async def download_generated_file(
    session_id: str,
    filepath: str = Query(...),
    service: SessionService = Depends(get_session_service),
):
    file_data = await service.download_generated_file(session_id, filepath)
    filename = os.path.basename(filepath)
    encoded_filename = urllib.parse.quote(filename)
    return StreamingResponse(
        file_data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"},
    )


@router.delete("/{session_id}", response_model=Response)
async def delete_session(session_id: str, service: SessionService = Depends(get_session_service)):
    await service.delete_session(session_id)
    return Response.success(msg="删除会话成功")


@router.post("/{session_id}/messages", response_model=Response[Session])
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    service: SessionService = Depends(get_session_service),
):
    session = await service.send_message(session_id, body.message, body.attachments)
    return Response.success(data=session, msg="消息发送成功")


@router.post("/{session_id}/cancel", response_model=Response)
async def cancel_session(session_id: str, service: SessionService = Depends(get_session_service)):
    await service.cancel(session_id)
    return Response.success(msg="任务已停止")


@router.post("/{session_id}/read", response_model=Response)
async def mark_session_read(session_id: str, service: SessionService = Depends(get_session_service)):
    await service.mark_read(session_id)
    return Response.success(msg="会话已标记为已读")


@router.get("/{session_id}/events")
async def stream_events(
    session_id: str,
    request: Request,
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
    after: str | None = Query(None),
    service: SessionService = Depends(get_session_service),
):
    session = await service.get_session(session_id)
    task = RedisStreamTask.get(session.task_id) if session.task_id else None
    if not isinstance(task, RedisStreamTask):
        async def completed_stream():
            # EventSource 会在服务端关闭连接后自动重连。这里必须发送完整的
            # Agent 终态事件，让前端更新会话状态并主动关闭连接。
            done_event = DoneEvent().model_dump_json()
            yield f"event: done\ndata: {done_event}\n\n"
        return StreamingResponse(completed_stream(), media_type="text/event-stream")

    start_id = last_event_id_header or after or "0-0"

    async def generate()->AsyncGenerator[str, None]:
        nonlocal start_id
        while True:
            if await request.is_disconnected():
                break
            event_id, raw_event = await task.output_stream.get(start_id=start_id, block_ms=15000)
            if raw_event is None:
                if task.done:
                    break
                yield ": ping\n\n"
                continue
            start_id = event_id
            try:
                event_type = json.loads(raw_event).get("type", "message")
            except (TypeError, json.JSONDecodeError):
                event_type = "message"
            yield f"id: {event_id}\nevent: {event_type}\ndata: {raw_event}\n\n"
            if event_type == "done":
                break
            await asyncio.sleep(0)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
