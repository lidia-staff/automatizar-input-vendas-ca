from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.routes_upload import router as upload_router
from app.api.routes_sales import router as sales_router
from app.api.routes_companies import router as companies_router
from app.api.routes_oauth import router as oauth_router

from app.db.session import Base, engine
from app.db import models  # noqa: F401  (garante que modelos carreguem)

app = FastAPI(title="Automatizar Input Vendas - Conta Azul (MVP)")


@app.get("/health")
def health():
    return JSONResponse({"ok": True})


# Rotas do MVP
app.include_router(upload_router, prefix="/v1")
app.include_router(sales_router, prefix="/v1")
app.include_router(companies_router, prefix="/v1")

# OAuth não deve ficar em /v1 (para o redirect_uri ficar curto/bonito)
app.include_router(oauth_router)


@app.on_event("startup")
def _startup():
    # cria tabelas automaticamente (MVP)
    Base.metadata.create_all(bind=engine)
