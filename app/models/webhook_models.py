from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Dict, Any

# --- Modelos para Mensajes de WhatsApp Entrantes ---

class WhatsAppTextMessage(BaseModel):
    body: str

class WhatsAppButtonReply(BaseModel):
    id: str
    title: str

class WhatsAppInteractiveListReply(BaseModel):
    id: str
    title: str
    description: Optional[str] = None

class WhatsAppInteractive(BaseModel):
    type: str
    button_reply: Optional[WhatsAppButtonReply] = None
    list_reply: Optional[WhatsAppInteractiveListReply] = None

class WhatsAppContext(BaseModel):
    from_number: Optional[str] = Field(None, alias='from')
    id: Optional[str] = None

class WhatsAppMessage(BaseModel):
    from_number: str = Field(..., alias='from') # 'from' es palabra reservada, usa alias
    id: str
    timestamp: str
    type: str
    text: Optional[WhatsAppTextMessage] = None
    interactive: Optional[WhatsAppInteractive] = None
    context: Optional[WhatsAppContext] = None

# --- NUEVOS MODELOS PARA CONTACTS ---
class WhatsAppProfile(BaseModel):
    name: str

class WhatsAppContact(BaseModel):
    profile: WhatsAppProfile
    wa_id: str # El ID de WhatsApp del usuario

# --- Modelos para Notificaciones de Estado de WhatsApp ---
class WhatsAppConversationOrigin(BaseModel):
    type: str

class WhatsAppConversation(BaseModel):
    id: str
    origin: WhatsAppConversationOrigin
    expiration_timestamp: Optional[str] = None

class WhatsAppPricing(BaseModel):
    billable: bool
    pricing_model: str
    category: str

class WhatsAppStatusErrorData(BaseModel):
    details: str

class WhatsAppStatusError(BaseModel):
    code: int
    title: str
    message: Optional[str] = None
    error_data: Optional[WhatsAppStatusErrorData] = None

class WhatsAppStatus(BaseModel):
    id: str
    recipient_id: str
    status: str
    timestamp: str
    conversation: Optional[WhatsAppConversation] = None
    pricing: Optional[WhatsAppPricing] = None
    errors: Optional[List[WhatsAppStatusError]] = None

# --- Modelos para la Estructura General del Payload de Webhook de WhatsApp ---
class WhatsAppMetadata(BaseModel):
    display_phone_number: str
    phone_number_id: str

class WhatsAppValue(BaseModel):
    messaging_product: str
    metadata: WhatsAppMetadata
    contacts: Optional[List[WhatsAppContact]] = None
    messages: Optional[List[WhatsAppMessage]] = None
    statuses: Optional[List[WhatsAppStatus]] = None
    errors: Optional[List[WhatsAppStatusError]] = None

class WhatsAppChange(BaseModel):
    value: WhatsAppValue
    field: str

class WhatsAppEntry(BaseModel):
    id: str
    changes: List[WhatsAppChange]

class WhatsAppPayload(BaseModel):
    object: str
    entry: List[WhatsAppEntry]

    @model_validator(mode='before')
    @classmethod
    def ensure_object_is_whatsapp(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("object") != "whatsapp_business_account":
            pass
        return data

# --- Modelos para Messenger ---
class MessengerTextMessage(BaseModel):
    mid: str
    text: str

class MessengerSender(BaseModel):
    id: str # Page-Scoped User ID (PSID)

class MessengerRecipient(BaseModel):
    id: str # Page ID

class MessengerPostback(BaseModel):
    payload: str
    title: Optional[str] = None

class MessagingEvent(BaseModel):
    sender: MessengerSender
    recipient: MessengerRecipient
    timestamp: int
    message: Optional[MessengerTextMessage] = None
    postback: Optional[MessengerPostback] = None

class MessengerEntry(BaseModel):
    id: str
    time: int
    messaging: List[MessagingEvent]

class MessengerPayload(BaseModel):
    object: str
    entry: List[MessengerEntry]
