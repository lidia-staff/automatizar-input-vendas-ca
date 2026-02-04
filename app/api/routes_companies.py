from datetime import datetime, timedelta
import traceback

from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company
from app.services.conta_azul_client import ContaAzulClient

router = APIRouter(tags=["companies"])


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


# -------------------------------------------------------------------
# Get Company
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Set Company Tokens (manual / fallback)
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# Conta Azul - Financial Accounts (COM TRATAMENTO DE ERRO DETALHADO)
# -------------------------------------------------------------------
@router.get("/companies/{company_id}/ca/financial-accounts")
def ca_list_financial_accounts(company_id: int):
    """
    Lista contas financeiras do Conta Azul.
    VERSÃO COM LOGS E TRATAMENTO DE ERRO DETALHADO.
    """
    print(f"[ENDPOINT] ===== INICIANDO ca_list_financial_accounts =====")
    print(f"[ENDPOINT] company_id={company_id}")
    
    # Valida company existe
    db: Session = SessionLocal()
    try:
        print(f"[ENDPOINT] Buscando company no banco...")
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            print(f"[ENDPOINT] ERRO: Company {company_id} não encontrada")
            raise HTTPException(status_code=404, detail="Company não encontrada")
        
        print(f"[ENDPOINT] Company encontrada: {c.name}")
        print(f"[ENDPOINT] Has access_token: {bool(c.access_token)}")
        print(f"[ENDPOINT] Has refresh_token: {bool(c.refresh_token)}")
        
    finally:
        db.close()

    # Tenta criar client e fazer request
    try:
        print(f"[ENDPOINT] Criando ContaAzulClient...")
        client = ContaAzulClient(company_id=company_id)
        print(f"[ENDPOINT] Client criado com sucesso")
        
        print(f"[ENDPOINT] Chamando list_financial_accounts()...")
        result = client.list_financial_accounts()
        print(f"[ENDPOINT] Sucesso! Retornando resultado")
        
        return result
        
    except RuntimeError as e:
        error_msg = str(e)
        print(f"[ENDPOINT] ERRO RuntimeError: {error_msg}")
        print(f"[ENDPOINT] Traceback completo:")
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": "runtime_error",
                "message": error_msg,
                "traceback": traceback.format_exc(),
            }
        )
    
    except Exception as e:
        error_msg = str(e)
        error_type = type(e).__name__
        print(f"[ENDPOINT] ERRO {error_type}: {error_msg}")
        print(f"[ENDPOINT] Traceback completo:")
        print(traceback.format_exc())
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_type,
                "message": error_msg,
                "traceback": traceback.format_exc(),
            }
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
