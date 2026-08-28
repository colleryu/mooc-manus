from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str = ""


class SendMessageRequest(BaseModel):
    message: str = ""
    attachments: list[str] = Field(default_factory=list)

