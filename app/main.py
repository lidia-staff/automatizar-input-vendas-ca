from fastapi import FastAPI

from app.api.routes_upload import router as upload_router
from app.api.routes_sales import router as sales_router
from app.api.routes_companies import router as companies_router
from app.api.routes_oauth import router as oauth_router

from app.db.session import Base, engine
from app.db import models  # noqa: F401 (garante modelos carreguem)

app = FastAPI(title="Automatizar Input Vendas - Conta Azul (MVP)")

# Rotas do MVP
app.include_router(upload_router, prefix="/v1")
app.include_router(sales_router, prefix="/v1")
app.include_router(companies_router, prefix="/v1")

# OAuth (precisa bater exatamente com o redirect_uri configurado)
# Vai expor:
#   GET /api/contaazul/start?company_id=1
#   GET /api/contaazul/callback
app.include_router(oauth_router)

@app.get("/")
def root():
    return {"ok": True, "service": "ca-sales-api"}

@app.get("/health")
def health():
    return {"ok": True}

# MVP: cria tabelas automaticamente
Base.metadata.create_all(bind=engine)
