from datetime import datetime
from typing import Optional
from pydantic import Field
from enum import Enum
from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class MessageBase(BaseDBModel):
    conversation_id: int
    content: str
    role: str
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)

class MessageCreate(BaseCreateModel):
    conversation_id: int
    content: str
    role: str
    timestamp: Optional[datetime] = None

class MessageUpdate(BaseUpdateModel):
    content: Optional[str] = None

class MessageInDB(MessageBase):
    class Config:
        table_name = "messages"

Message = MessageInDB
