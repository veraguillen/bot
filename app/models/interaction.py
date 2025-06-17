from datetime import datetime
from typing import Optional
from pydantic import EmailStr, Field
from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel

class InteractionBase(BaseDBModel):
    """Modelo base para interacciones con los usuarios"""
    user_wa_id: str  # ID de WhatsApp del usuario
    platform: str  # Ej: 'whatsapp', 'web', 'telegram'
    company_id: Optional[int] = None  # ID de la compañía relacionada
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_email: Optional[EmailStr] = None
    interaction_metadata: dict = Field(default_factory=dict, alias="metadata")  # Datos adicionales

class InteractionCreate(BaseCreateModel):
    """Datos para crear una nueva interacción"""
    user_wa_id: str
    platform: str
    company_id: Optional[int] = None
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_email: Optional[str] = None
    interaction_metadata: Optional[dict] = Field(default=None, alias="metadata")

class InteractionUpdate(BaseUpdateModel):
    """Datos para actualizar una interacción existente"""
    user_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_email: Optional[str] = None
    interaction_metadata: Optional[dict] = Field(default=None, alias="metadata")

class InteractionInDB(InteractionBase):
    class Config:
        table_name = "interactions"

Interaction = InteractionInDB
