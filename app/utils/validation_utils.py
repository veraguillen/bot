# app/utils/validation_utils.py
import re

def is_valid_email(email: str) -> bool:
    """Valida un formato de email simple."""
    if not email or not isinstance(email, str):
        return False
    # Regex simple, puedes usar una más compleja si es necesario
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))

def is_valid_phone(phone: str) -> bool:
    """Valida un formato de teléfono simple (ej. internacional con +)."""
    if not phone or not isinstance(phone, str):
        return False
    # Regex muy simple: empieza con +, seguido de números. Longitud entre 7 y 15.
    pattern = r"^\+[0-9]{7,15}$" 
    return bool(re.match(pattern, phone))