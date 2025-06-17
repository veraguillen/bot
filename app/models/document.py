from datetime import datetime
from typing import Optional, Any, List
from pydantic import Field
from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel

class DocumentBase(BaseDBModel):
    content: str
    source: Optional[str] = None
    document_metadata: Optional[dict] = Field(default=None, alias="metadata")
    # embedding se manejará de manera especial

class DocumentCreate(BaseCreateModel):
    content: str
    source: Optional[str] = None
    document_metadata: Optional[dict] = Field(default=None, alias="metadata")
    embedding: Optional[List[float]] = None

class DocumentUpdate(BaseUpdateModel):
    content: Optional[str] = None
    source: Optional[str] = None
    document_metadata: Optional[dict] = Field(default=None, alias="metadata")
    embedding: Optional[List[float]] = None

class DocumentInDB(DocumentBase):
    class Config:
        table_name = "documents"

Document = DocumentInDB
