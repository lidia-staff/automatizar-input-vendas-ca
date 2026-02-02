from fastapi import FastAPI
from sqlalchemy import text

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
app.include_router(oauth_router)

@app.get("/")
def root():
    return {"ok": True, "service": "ca-sales-api"}

@app.get("/health")
def health():
    return {"ok": True}


def run_schema_migrations():
    """
    Migração leve (sem Alembic) para evitar 500 quando o model muda e o Postgres
    já existe no Railway.
    Seguro: só adiciona colunas se não existirem.
    """
    stmts = [
        # companies
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS default_item_id VARCHAR;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS ca_financial_account_id VARCHAR;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS access_token TEXT;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS refresh_token TEXT;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS review_mode BOOLEAN DEFAULT TRUE;",
    ]

    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))


# 1) garante tabelas
Base.metadata.create_all(bind=engine)

# 2) garante colunas novas (Railway Postgres já existente)
run_schema_migrations()
