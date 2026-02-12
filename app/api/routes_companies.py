from datetime import datetime, timedelta
import traceback

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company
from app.services.conta_azul_client import ContaAzulClient

router = APIRouter(tags=["companies"])


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
        return [
            {
                "id": c.id,
                "name": c.name,
                "has_token": bool(c.refresh_token),
                "token_expires_at": c.token_expires_at,
                "ca_financial_account_id": c.ca_financial_account_id,
                "default_item_id": getattr(c, "default_item_id", None),
            }
            for c in rows
        ]
    finally:
        db.close()


@router.get("/companies/{company_id}")
def get_company(company_id: int):
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        return {
            "id": c.id,
            "name": c.name,
            "has_token": bool(c.refresh_token),
            "token_expires_at": c.token_expires_at,
            "ca_financial_account_id": c.ca_financial_account_id,
            "default_item_id": getattr(c, "default_item_id", None),
        }
    finally:
        db.close()


@router.post("/companies/{company_id}/tokens")
def set_company_tokens(
    company_id: int,
    access_token: str = Body(..., embed=True),
    refresh_token: str = Body(..., embed=True),
    expires_in: int = Body(3600, embed=True),
):
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
    """Lista contas financeiras - com tratamento de erro detalhado."""
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
        raise HTTPException(
            status_code=500,
            detail=f"{type(e).__name__}: {str(e)} | {traceback.format_exc()}"
        )


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
