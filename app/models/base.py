from datetime import datetime
from enum import Enum
from typing import Optional, TypeVar
from pydantic import BaseModel, Field, ConfigDict

T = TypeVar('T')

class BaseDBModel(BaseModel):
    # Modelo base para todas las entidades de la base de datos
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Configuración compatible con Pydantic v2
    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat() if dt else None
        },
        json_schema_extra={
            "example": {}
        }
    )

class BaseCreateModel(BaseModel):
    # Modelo base para la creación de entidades
    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat() if dt else None
        }
    )

class BaseUpdateModel(BaseModel):
    # Modelo base para la actualización de entidades
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={
            datetime: lambda dt: dt.isoformat() if dt else None
        }
    )

# Enums comunes
class StatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
