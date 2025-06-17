"""Modelos SQLAlchemy para la gestión de compañías."""
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.orm import relationship

# Para type hints circulares
if TYPE_CHECKING:
    from .user_state import UserState
    from .appointment_models import Appointment
    from .interaction_models import Interaction

# Importar la base de datos desde el core
try:
    from app.core.database import Base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base
    Base = declarative_base()

class Company(Base):
    """Modelo SQLAlchemy para la tabla de compañías."""
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    scheduling_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relaciones
    user_states = relationship("UserState", back_populates="company")
    interactions = relationship("Interaction", back_populates="company")
    appointments = relationship("Appointment", back_populates="company")

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}')>"

# Actualizar el __all__ en __init__.py para incluir el nuevo modelo
# Asegúrate de que __init__.py tenga algo como:
# from .company_models import Company
# __all__ = [..., 'Company']
