from pydantic import TypeAdapter

from app.domain.models.event import DoneEvent, ErrorEvent, Event


def test_base_event_has_task_id_field():
    event = DoneEvent(task_id="task-1")
    assert event.task_id == "task-1"
    assert event.model_dump(mode="json")["task_id"] == "task-1"


def test_event_discriminator_accepts_missing_task_id():
    # 历史数据没有 task_id 时允许解析，保持向后兼容
    raw = '{"id": "e1", "type": "done", "create_at": "2026-08-28T23:00:00"}'
    event = TypeAdapter(Event).validate_json(raw)
    assert isinstance(event, DoneEvent)
    assert event.task_id is None


def test_error_event_serializes_task_id():
    event = ErrorEvent(error="boom", task_id="task-9")
    payload = event.model_dump(mode="json")
    assert payload["type"] == "error"
    assert payload["task_id"] == "task-9"
