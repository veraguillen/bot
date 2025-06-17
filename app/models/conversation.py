from datetime import datetime
from typing import Optional
from pydantic import Field
from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel, StatusEnum

class ConversationBase(BaseDBModel):
    user_id: str
    company_id: Optional[int] = None
    started_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    status: Optional[str] = None

class ConversationCreate(BaseCreateModel):
    user_id: str
    company_id: Optional[int] = None
    status: Optional[str] = "active"

class ConversationUpdate(BaseUpdateModel):
    status: Optional[str] = None
    last_message_at: Optional[datetime] = None

class ConversationInDB(ConversationBase):
    class Config:
        table_name = "conversations"

Conversation = ConversationInDB
