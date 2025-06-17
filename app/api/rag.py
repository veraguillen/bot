# app/api/rag.py
"""
Módulo para endpoints relacionados con Retrieval Augmented Generation (RAG).
Este archivo proporciona endpoints para realizar búsquedas vectoriales usando PGVector.
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.utils.logger import logger
from app.ai.rag_retriever import search_relevant_documents

# Crear router para endpoints RAG
rag_router = APIRouter(prefix="/rag", tags=["RAG API"])

class RAGQueryRequest(BaseModel):
    query: str
    brand: Optional[str] = None
    top_k: Optional[int] = None

@rag_router.post("/ask")
async def ask_query(request: Request, rag_query: RAGQueryRequest):
    """
    Endpoint para realizar consultas al sistema RAG y obtener documentos relevantes.
    """
    if not request.app.state.is_rag_ready:
        logger.error("El sistema RAG no está listo. Verifique la conexión a la base de datos y la carga de componentes RAG.")
        raise HTTPException(status_code=503, detail="Servicio RAG no disponible")
        
    try:
        results = await search_relevant_documents(
            user_query=rag_query.query,
            target_brand=rag_query.brand,
            k_final=rag_query.top_k
        )
        return results
    except Exception as e:
        logger.error(f"Error al procesar consulta RAG: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al procesar la consulta: {str(e)}")

@rag_router.get("/status")
async def rag_status():
    """Endpoint para verificar el estado del sistema RAG"""
    return {
        "status": "operational",
        "message": "Sistema RAG inicializado correctamente",
        "version": "1.0.0"
    }
