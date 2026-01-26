from datetime import datetime, timedelta

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company
from app.services.conta_azul_client import ContaAzulClient

router = APIRouter(tags=["companies"])


class DefaultItemIn(BaseModel):
    default_item_id: str


# -------------------------------------------------------------------
# Criar Company
# -------------------------------------------------------------------
@router.post("/companies")
def create_company(name: str = Body(..., embed=True)):
    db: Session = SessionLocal()
    try:
        existing = db.query(Company).filter(Company.name == name).first()
        if existing:
            return {"id": existing.id, "name": existing.name, "message": "Company já existente"}

        company = Company(name=name)
        db.add(company)
        db.commit()
        db.refresh(company)
        return {"id": company.id, "name": company.name}
    finally:
        db.close()


# -------------------------------------------------------------------
# Listar Companies
# -------------------------------------------------------------------
@router.get("/companies")
def list_companies():
    db: Session = SessionLocal()
    try:
        companies = db.query(Company).order_by(Company.id.asc()).all()
        return [
            {
                "id": c.id,
                "name": c.name,
                "has_token": bool(c.access_token),
                "token_expires_at": c.token_expires_at,
                "ca_financial_account_id": c.ca_financial_account_id,
                "default_item_id": c.default_item_id,
            }
            for c in companies
        ]
    finally:
        db.close()


# -------------------------------------------------------------------
# Buscar Company por ID
# -------------------------------------------------------------------
@router.get("/companies/{company_id}")
def get_company(company_id: int):
    db: Session = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        return {
            "id": company.id,
            "name": company.name,
            "has_token": bool(company.access_token),
            "token_expires_at": company.token_expires_at,
            "ca_financial_account_id": company.ca_financial_account_id,
            "default_item_id": company.default_item_id,
        }
    finally:
        db.close()


# -------------------------------------------------------------------
# Salvar / Atualizar Tokens OAuth Conta Azul (fallback manual)
# -------------------------------------------------------------------
@router.post("/companies/{company_id}/tokens")
def set_company_tokens(
    company_id: int,
    access_token: str = Body(...),
    refresh_token: str = Body(...),
    expires_in: int = Body(3600),
):
    db: Session = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        company.access_token = access_token
        company.refresh_token = refresh_token
        company.token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        db.add(company)
        db.commit()

        return {"ok": True, "company_id": company_id, "token_expires_at": company.token_expires_at}
    finally:
        db.close()


# -------------------------------------------------------------------
# Conta Azul - Contas Financeiras
# -------------------------------------------------------------------
@router.get("/companies/{company_id}/ca/financial-accounts")
def ca_list_financial_accounts(company_id: int):
    # valida company existe
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
    finally:
        db.close()

    client = ContaAzulClient(company_id=company_id)
    return client.list_financial_accounts()


@router.post("/companies/{company_id}/ca/financial-account")
def ca_set_financial_account(company_id: int, ca_financial_account_id: str = Body(..., embed=True)):
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company not found")
        c.ca_financial_account_id = ca_financial_account_id
        db.add(c)
        db.commit()
        db.refresh(c)
        return {"ok": True, "company_id": company_id, "ca_financial_account_id": c.ca_financial_account_id}
    finally:
        db.close()


# -------------------------------------------------------------------
# Conta Azul - Produtos/Serviços (Inventário) por busca
# -------------------------------------------------------------------
@router.get("/companies/{company_id}/ca/products")
def ca_list_products(company_id: int, busca: str, pagina: int = 1, tamanho_pagina: int = 50):
    client = ContaAzulClient(company_id=company_id)
    return client.list_products(busca=busca, pagina=pagina, tamanho_pagina=tamanho_pagina)


# -------------------------------------------------------------------
# Definir item/serviço padrão (fallback) para vendas
# -------------------------------------------------------------------
@router.post("/companies/{company_id}/default-item")
def set_default_item(company_id: int, body: DefaultItemIn):
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")

        c.default_item_id = body.default_item_id
        db.add(c)
        db.commit()
        db.refresh(c)

        return {"ok": True, "company_id": company_id, "default_item_id": c.default_item_id}
    finally:
        db.close()
