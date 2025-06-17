from datetime import datetime
from typing import Optional
from pydantic import Field
from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel

class AppointmentBase(BaseDBModel):
    start_time: datetime
    end_time: datetime
    status: str
    calendly_event_uri: str
    calendly_invitee_uri: str
    interaction_id: Optional[int] = None
    company_id: Optional[int] = None
    reminder_sent: bool = False

class AppointmentCreate(BaseCreateModel):
    start_time: datetime
    end_time: datetime
    status: str
    calendly_event_uri: str
    calendly_invitee_uri: str
    interaction_id: Optional[int] = None
    company_id: Optional[int] = None

class AppointmentUpdate(BaseUpdateModel):
    status: Optional[str] = None
    reminder_sent: Optional[bool] = None
    end_time: Optional[datetime] = None

class AppointmentInDB(AppointmentBase):
    class Config:
        table_name = "appointments"

Appointment = AppointmentInDB
