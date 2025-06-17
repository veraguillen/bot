from fastapi import APIRouter

router = APIRouter()



# Incluir solo el router de meta, que contiene los endpoints de WhatsApp
#router.include_router(meta.router, prefix="/api", tags=["api"])