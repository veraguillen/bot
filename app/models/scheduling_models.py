from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, func,
    Boolean, Index
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import expression
import datetime
from typing import List, Optional, TYPE_CHECKING

# Intenta importar Base de la ubicación centralizada
try:
    from app.core.database import Base
except ImportError:
    from sqlalchemy.ext.declarative import declarative_base
    Base = declarative_base()

# Type Hinting para evitar importación circular
if TYPE_CHECKING:
    from .user_state import UserState

class Company(Base):
    """Modelo para las Empresas/Marcas que el chatbot puede representar."""
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # Relaciones
    user_states: Mapped[List["UserState"]] = relationship(back_populates="company")
    interactions: Mapped[List["Interaction"]] = relationship(
        "Interaction", 
        back_populates="company", 
        cascade="all, delete-orphan"
    )
    appointments: Mapped[List["Appointment"]] = relationship("Appointment", back_populates="company")

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, name='{self.name}')>"

class Interaction(Base):
    """Modelo para registrar interacciones significativas del usuario."""
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_wa_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(50), default='whatsapp', nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('companies.id', ondelete='SET NULL'),
        index=True,
        nullable=True
    )
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )

    # Relaciones
    company: Mapped[Optional["Company"]] = relationship(back_populates="interactions")
    appointment: Mapped[Optional["Appointment"]] = relationship(
        back_populates="interaction", 
        uselist=False,
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Interaction(id={self.id}, user_wa_id='{self.user_wa_id}', company_id={self.company_id}, created_at='{self.created_at}')>"

class Appointment(Base):
    """Modelo para las citas agendadas con Calendly."""
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    
    interaction_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('interactions.id', ondelete='CASCADE'),
        unique=True,
        index=True,
        nullable=True
    )
    
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('companies.id', ondelete='SET NULL'),
        index=True,
        nullable=True
    )
    
    # URIs de Calendly
    calendly_event_uri: Mapped[str] = mapped_column(Text, nullable=False)
    calendly_invitee_uri: Mapped[str] = mapped_column(Text, unique=True, nullable=False, index=True)

    # Detalles de la cita
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    end_time: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default='scheduled', index=True, nullable=False)
    
    # Para seguimiento de recordatorios
    reminder_sent: Mapped[bool] = mapped_column(
        Boolean, 
        server_default=expression.false(),
        nullable=False,
        index=True
    )

    # Relaciones
    interaction: Mapped[Optional["Interaction"]] = relationship(back_populates="appointment")
    company: Mapped[Optional["Company"]] = relationship(back_populates="appointments")

    def __repr__(self) -> str:
        return (f"<Appointment(id={self.id}, invitee_uri='{self.calendly_invitee_uri}', " +
                f"start='{self.start_time}', status='{self.status}')>")
