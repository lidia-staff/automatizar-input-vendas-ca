from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
import os

from app.api.routes_upload import router as upload_router
from app.api.routes_sales import router as sales_router
from app.api.routes_companies import router as companies_router
from app.api.routes_oauth import router as oauth_router

from app.db.session import Base, engine
from app.db import models  # noqa: F401

app = FastAPI(title="Automatizar Input Vendas - Conta Azul (MVP)")

app.include_router(upload_router, prefix="/v1")
app.include_router(sales_router, prefix="/v1")
app.include_router(companies_router, prefix="/v1")
app.include_router(oauth_router)


@app.get("/painel", response_class=HTMLResponse)
def painel():
    path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/")
def root():
    return {"ok": True, "service": "ca-sales-api", "painel": "/painel"}


@app.get("/health")
def health():
    return {"ok": True}


def run_schema_migrations():
    stmts = [
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS default_item_id VARCHAR;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS ca_financial_account_id VARCHAR;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS access_token TEXT;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS refresh_token TEXT;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP;",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS review_mode BOOLEAN DEFAULT TRUE;",
        """CREATE TABLE IF NOT EXISTS company_payment_accounts (
            id SERIAL PRIMARY KEY,
            company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            payment_method_key VARCHAR(50) NOT NULL,
            ca_financial_account_id VARCHAR(80) NOT NULL,
            label VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uq_company_payment_method UNIQUE (company_id, payment_method_key)
        );""",
    ]
    with engine.begin() as conn:
        for s in stmts:
            conn.execute(text(s))


Base.metadata.create_all(bind=engine)
run_schema_migrations()
