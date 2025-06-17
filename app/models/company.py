from datetime import datetime
from typing import Optional
from pydantic import HttpUrl, Field
from .base import BaseDBModel, BaseCreateModel, BaseUpdateModel

class CompanyBase(BaseDBModel):
    """Modelo base para las compañías"""
    name: str
    description: Optional[str] = None
    scheduling_url: Optional[str] = None

class CompanyCreate(BaseCreateModel):
    """Datos para crear una nueva compañía"""
    name: str
    description: Optional[str] = None
    scheduling_url: Optional[str] = None

class CompanyUpdate(BaseUpdateModel):
    """Datos para actualizar una compañía existente"""
    name: Optional[str] = None
    description: Optional[str] = None
    scheduling_url: Optional[str] = None

class CompanyInDB(CompanyBase):
    class Config:
        table_name = "companies"

Company = CompanyInDB
