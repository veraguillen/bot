"""Modelos SQLAlchemy para la gestión de citas."""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Para type hints circulares
if TYPE_CHECKING:
    from .interaction_models import Interaction
    from .company_models import Company

# Importar la base de datos desde el core
try:
    from app.core.database import Base
except ImportError:
    from sqlalchemy.orm import DeclarativeBase
    Base = DeclarativeBase()

class Appointment(Base):
    """Modelo SQLAlchemy para la tabla de citas."""
    __tablename__ = "appointments"
    __allow_unmapped__ = True  # Para compatibilidad con código heredado

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled")
    calendly_event_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    calendly_invitee_uri: Mapped[str] = mapped_column(
        String(500), 
        unique=True, 
        nullable=False, 
        index=True
    )
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Claves foráneas
    interaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('interactions.id', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('companies.id', ondelete='SET NULL'),
        nullable=True,
        index=True
    )
    
    # Relaciones
    interaction: Mapped[Optional["Interaction"]] = relationship("Interaction", back_populates="appointment")
    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="appointments")
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )
    
    def __repr__(self) -> str:
        return f"<Appointment(id={self.id}, start='{self.start_time}', status='{self.status}')>"
