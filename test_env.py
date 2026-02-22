from fastapi import APIRouter
import os

router = APIRouter(tags=["debug"])

@router.get("/debug/env")
def debug_env():
    """Endpoint temporário para verificar variáveis de ambiente"""
    return {
        "CA_CLIENT_ID": "OK" if os.getenv("CA_CLIENT_ID") else "MISSING",
        "CA_CLIENT_SECRET": "OK" if os.getenv("CA_CLIENT_SECRET") else "MISSING",
        "CA_REDIRECT_URI": os.getenv("CA_REDIRECT_URI"),
        "CA_API_BASE_URL": os.getenv("CA_API_BASE_URL"),
        "DATABASE_URL": "OK" if os.getenv("DATABASE_URL") else "MISSING",
    }
