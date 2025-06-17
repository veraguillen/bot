from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel, StatusEnum
from .user_state import UserState, UserStateCreate, UserStateUpdate, UserStateInDB
from .company import CompanyCreate, CompanyUpdate, CompanyInDB  # Modelos Pydantic
from .company_models import Company  # Modelo SQLAlchemy
from .conversation import Conversation, ConversationCreate, ConversationUpdate, ConversationInDB
from .message import Message, MessageCreate, MessageUpdate, MessageInDB
from .appointment import AppointmentCreate, AppointmentUpdate, AppointmentInDB  # Modelos Pydantic
from .appointment_models import Appointment  # Modelo SQLAlchemy
from .document import Document, DocumentCreate, DocumentUpdate, DocumentInDB
from .interaction import InteractionCreate, InteractionUpdate, InteractionInDB  # Modelos Pydantic
from .interaction_models import Interaction  # Modelo SQLAlchemy

__all__ = [
    # Base models
    'BaseDBModel', 'BaseCreateModel', 'BaseUpdateModel', 'StatusEnum',
    
    # User State
    'UserState', 'UserStateCreate', 'UserStateUpdate', 'UserStateInDB',
    
    # Company
    'Company', 'CompanyCreate', 'CompanyUpdate', 'CompanyInDB',  # Modelos Pydantic y SQLAlchemy
    
    # Conversation
    'Conversation', 'ConversationCreate', 'ConversationUpdate', 'ConversationInDB',
    
    # Message
    'Message', 'MessageCreate', 'MessageUpdate', 'MessageInDB',
    
    # Appointment
    'Appointment', 'AppointmentCreate', 'AppointmentUpdate', 'AppointmentInDB',  # Modelos Pydantic y SQLAlchemy
    
    # Document
    'Document', 'DocumentCreate', 'DocumentUpdate', 'DocumentInDB',
    
    # Interaction
    'Interaction', 'InteractionCreate', 'InteractionUpdate', 'InteractionInDB'  # Modelos Pydantic y SQLAlchemy
]
