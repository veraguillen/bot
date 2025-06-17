from sqlalchemy import String, DateTime, func, Integer, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# Importar Base de la base de datos central
try:
    from app.core.database import Base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base
    Base = declarative_base()

# Type hints para evitar importaciones circulares
if TYPE_CHECKING:
    from .company_models import Company

# Enumeración para el estado del usuario
class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"

# Modelo SQLAlchemy
class UserState(Base):
    __tablename__ = "user_states"

    # --- Clave Primaria Compuesta ---
    user_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    platform: Mapped[str] = mapped_column(
        String(50), 
        primary_key=True, 
        index=True, 
        default="whatsapp"
    )

    # --- Campo de Suscripción ---
    is_subscribed: Mapped[bool] = mapped_column(
        Boolean, 
        default=True, 
        nullable=False
    )

    # --- Relación con Company ---
    current_brand_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('companies.id', name='fk_user_states_company_id', ondelete='SET NULL'),
        index=True,
        nullable=True
    )
    company: Mapped[Optional["Company"]] = relationship(
        "Company",
        back_populates="user_states",
        foreign_keys=[current_brand_id]
    )
    
    # --- Estado del Flujo ---
    stage: Mapped[str] = mapped_column(
        String(100), 
        default="selecting_brand", 
        index=True, 
        nullable=False
    )
    
    # Flag para marcar si la sesión ha sido finalizada explícitamente por el usuario
    session_explicitly_ended: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False
    )

    # --- Campos de Información Recolectada ---
    collected_name: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True
    )
    collected_phone: Mapped[Optional[str]] = mapped_column(
        String(50), 
        nullable=True
    )
    collected_email: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True
    )
    purpose_of_inquiry: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True
    )
    location_info: Mapped[Optional[str]] = mapped_column(
        String(512), 
        nullable=True
    )

    # --- Timestamps ---
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<UserState(user_id='{self.user_id}', " +
            f"platform='{self.platform}', " +
            f"stage='{self.stage}', " +
            f"subscribed={self.is_subscribed})>" 
        )

# Modelos Pydantic para validación
class UserStateBase(BaseModel):
    user_id: str
    platform: str = "whatsapp"
    is_subscribed: bool = True
    current_brand_id: Optional[int] = None
    stage: str = "selecting_brand"
    session_explicitly_ended: bool = False
    collected_name: Optional[str] = None
    collected_phone: Optional[str] = None
    collected_email: Optional[str] = None
    purpose_of_inquiry: Optional[str] = None
    location_info: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class UserStateCreate(UserStateBase):
    pass

class UserStateUpdate(BaseModel):
    is_subscribed: Optional[bool] = None
    current_brand_id: Optional[int] = None
    stage: Optional[str] = None
    session_explicitly_ended: Optional[bool] = None
    collected_name: Optional[str] = None
    collected_phone: Optional[str] = None
    collected_email: Optional[str] = None
    purpose_of_inquiry: Optional[str] = None
    location_info: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class UserStateInDB(UserStateBase):
    last_interaction_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
