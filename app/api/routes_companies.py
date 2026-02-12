from datetime import datetime, timedelta
import traceback
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company, CompanyPaymentAccount
from app.services.conta_azul_client import ContaAzulClient

router = APIRouter(tags=["companies"])

VALID_PAYMENT_KEYS = ["PIX", "CARTAO_CREDITO", "CARTAO_DEBITO", "BOLETO", "TRANSFERENCIA", "DINHEIRO", "OUTRO"]


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


@router.get("/companies")
def list_companies():
    db: Session = SessionLocal()
    try:
        rows = db.query(Company).order_by(Company.id.asc()).all()
        return [{"id": c.id, "name": c.name, "has_token": bool(c.refresh_token),
                 "token_expires_at": c.token_expires_at,
                 "ca_financial_account_id": c.ca_financial_account_id,
                 "default_item_id": getattr(c, "default_item_id", None),
                 "review_mode": c.review_mode} for c in rows]
    finally:
        db.close()


@router.get("/companies/{company_id}")
def get_company(company_id: int):
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        return {"id": c.id, "name": c.name, "has_token": bool(c.refresh_token),
                "token_expires_at": c.token_expires_at,
                "ca_financial_account_id": c.ca_financial_account_id,
                "default_item_id": getattr(c, "default_item_id", None),
                "review_mode": c.review_mode}
    finally:
        db.close()


@router.post("/companies/{company_id}/tokens")
def set_company_tokens(company_id: int, access_token: str = Body(..., embed=True),
                       refresh_token: str = Body(..., embed=True), expires_in: int = Body(3600, embed=True)):
    db: Session = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        company.access_token = access_token
        company.refresh_token = refresh_token
        company.token_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        db.add(company)
        db.commit()
        return {"ok": True, "company_id": company_id, "token_expires_at": company.token_expires_at}
    finally:
        db.close()


@router.get("/companies/{company_id}/ca/financial-accounts")
def ca_list_financial_accounts(company_id: int):
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
    finally:
        db.close()
    try:
        client = ContaAzulClient(company_id=company_id)
        return client.list_financial_accounts()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {str(e)}")


@router.post("/companies/{company_id}/ca/financial-account")
def ca_set_financial_account(company_id: int, ca_financial_account_id: str = Body(..., embed=True)):
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        c.ca_financial_account_id = ca_financial_account_id
        db.add(c)
        db.commit()
        return {"ok": True, "company_id": company_id, "ca_financial_account_id": ca_financial_account_id}
    finally:
        db.close()


@router.get("/companies/{company_id}/payment-accounts")
def list_payment_accounts(company_id: int):
    """Lista mapeamento forma de pagamento → conta financeira."""
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        mappings = db.query(CompanyPaymentAccount).filter(
            CompanyPaymentAccount.company_id == company_id).all()
        return {
            "company_id": company_id,
            "company_name": c.name,
            "default_account": c.ca_financial_account_id,
            "mappings": [{"id": m.id, "payment_method_key": m.payment_method_key,
                          "ca_financial_account_id": m.ca_financial_account_id,
                          "label": m.label} for m in mappings],
            "valid_keys": VALID_PAYMENT_KEYS,
        }
    finally:
        db.close()


@router.post("/companies/{company_id}/payment-accounts")
def set_payment_account(company_id: int,
                        payment_method_key: str = Body(..., embed=True),
                        ca_financial_account_id: str = Body(..., embed=True),
                        label: Optional[str] = Body(None, embed=True)):
    """Cria ou atualiza mapeamento forma de pagamento → conta financeira."""
    key = payment_method_key.strip().upper()
    if key not in VALID_PAYMENT_KEYS:
        raise HTTPException(status_code=400,
                            detail=f"Chave inválida: '{key}'. Válidas: {VALID_PAYMENT_KEYS}")
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        existing = db.query(CompanyPaymentAccount).filter(
            CompanyPaymentAccount.company_id == company_id,
            CompanyPaymentAccount.payment_method_key == key).first()
        if existing:
            existing.ca_financial_account_id = ca_financial_account_id
            existing.label = label
            db.add(existing)
        else:
            db.add(CompanyPaymentAccount(company_id=company_id, payment_method_key=key,
                                         ca_financial_account_id=ca_financial_account_id, label=label))
        db.commit()
        return {"ok": True, "company_id": company_id, "payment_method_key": key,
                "ca_financial_account_id": ca_financial_account_id, "label": label}
    finally:
        db.close()


@router.delete("/companies/{company_id}/payment-accounts/{payment_method_key}")
def delete_payment_account(company_id: int, payment_method_key: str):
    """Remove mapeamento de uma forma de pagamento."""
    key = payment_method_key.strip().upper()
    db: Session = SessionLocal()
    try:
        mapping = db.query(CompanyPaymentAccount).filter(
            CompanyPaymentAccount.company_id == company_id,
            CompanyPaymentAccount.payment_method_key == key).first()
        if not mapping:
            raise HTTPException(status_code=404, detail="Mapeamento não encontrado")
        db.delete(mapping)
        db.commit()
        return {"ok": True, "deleted": key}
    finally:
        db.close()
