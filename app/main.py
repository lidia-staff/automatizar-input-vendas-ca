from fastapi import FastAPI

from app.api.routes_upload import router as upload_router
from app.api.routes_sales import router as sales_router
from app.api.routes_companies import router as companies_router
from app.api.routes_oauth import router as oauth_router

from app.db.session import Base, engine
from app.db import models  # noqa

app = FastAPI(title="Automatizar Input Vendas - Conta Azul")

# rotas com prefix /v1
app.include_router(upload_router, prefix="/v1")
app.include_router(sales_router, prefix="/v1")
app.include_router(companies_router, prefix="/v1")

# 🔥 OAuth SEM prefix
app.include_router(oauth_router)

Base.metadata.create_all(bind=engine)