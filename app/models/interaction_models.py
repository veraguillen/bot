"""Modelos SQLAlchemy para la gestión de interacciones."""
from datetime import datetime
from typing import Dict, Optional, TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Para type hints circulares
if TYPE_CHECKING:
    from .company_models import Company
    from .appointment_models import Appointment

# Importar la base de datos desde el core
try:
    from app.core.database import Base
except ImportError:
    from sqlalchemy.orm import DeclarativeBase
    Base = DeclarativeBase()

class Interaction(Base):
    """Modelo SQLAlchemy para la tabla de interacciones."""
    __tablename__ = "interactions"
    __allow_unmapped__ = True  # Para compatibilidad con código heredado

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_wa_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="whatsapp")
    user_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    interaction_metadata: Mapped[Dict] = mapped_column('metadata', JSON, default=dict, nullable=False)
    
    # Claves foráneas
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('companies.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # Relaciones
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="interactions")
    appointment: Mapped[Optional["Appointment"]] = relationship(
        "Appointment", 
        back_populates="interaction", 
        uselist=False
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Interaction(id={self.id}, user_wa_id='{self.user_wa_id}', company_id={self.company_id})>"
