from typing import Optional
from fastapi import APIRouter, Body, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company, AsaasCredential, AsaasExecutionLog
from app.services.asaas_client import AsaasClient

router = APIRouter(tags=["asaas"])


def _get_company_or_404(db: Session, company_id: int) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def _require_asaas_enabled(company: Company):
    if not getattr(company, "asaas_enabled", False):
        raise HTTPException(status_code=403, detail="Integração Asaas não habilitada para esta empresa")


def _get_credential_or_404(db: Session, company_id: int) -> AsaasCredential:
    cred = db.query(AsaasCredential).filter(AsaasCredential.company_id == company_id).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial Asaas não configurada para esta empresa")
    return cred


# ──────────────────────────────────────────────
# Credenciais
# ──────────────────────────────────────────────

@router.post("/companies/{company_id}/asaas/credentials")
def upsert_asaas_credentials(
    company_id: int,
    api_key: str = Body(..., embed=True),
    environment: Optional[str] = Body("production", embed=True),
):
    if environment not in ("production", "sandbox"):
        raise HTTPException(status_code=400, detail="environment deve ser 'production' ou 'sandbox'")
    db: Session = SessionLocal()
    try:
        company = _get_company_or_404(db, company_id)
        _require_asaas_enabled(company)
        cred = db.query(AsaasCredential).filter(AsaasCredential.company_id == company_id).first()
        if cred:
            cred.api_key = api_key.strip()
            cred.environment = environment
        else:
            cred = AsaasCredential(company_id=company_id, api_key=api_key.strip(), environment=environment)
            db.add(cred)
        db.commit()
        db.refresh(cred)
        return {"ok": True, "environment": cred.environment, "created_at": cred.created_at}
    finally:
        db.close()


@router.get("/companies/{company_id}/asaas/credentials")
def get_asaas_credentials(company_id: int):
    db: Session = SessionLocal()
    try:
        _get_company_or_404(db, company_id)
        cred = db.query(AsaasCredential).filter(AsaasCredential.company_id == company_id).first()
        if not cred:
            return {"has_key": False}
        return {
            "has_key": True,
            "environment": cred.environment,
            "created_at": cred.created_at,
            "updated_at": cred.updated_at,
        }
    finally:
        db.close()


@router.delete("/companies/{company_id}/asaas/credentials")
def delete_asaas_credentials(company_id: int):
    db: Session = SessionLocal()
    try:
        _get_company_or_404(db, company_id)
        cred = db.query(AsaasCredential).filter(AsaasCredential.company_id == company_id).first()
        if cred:
            db.delete(cred)
            db.commit()
        return {"ok": True}
    finally:
        db.close()


# ──────────────────────────────────────────────
# Ping / validação
# ──────────────────────────────────────────────

@router.get("/companies/{company_id}/asaas/ping")
def ping_asaas(company_id: int):
    db: Session = SessionLocal()
    try:
        _get_company_or_404(db, company_id)
        cred = _get_credential_or_404(db, company_id)
        client = AsaasClient(api_key=cred.api_key, environment=cred.environment)
    finally:
        db.close()
    try:
        info = client.get_account_info()
        return {"ok": True, "account": info}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha ao conectar no Asaas: {str(e)}")


# ──────────────────────────────────────────────
# Logs de execução
# ──────────────────────────────────────────────

@router.get("/companies/{company_id}/asaas/logs")
def list_asaas_logs(
    company_id: int,
    status: Optional[str] = None,
    limit: int = 50,
):
    db: Session = SessionLocal()
    try:
        _get_company_or_404(db, company_id)
        q = db.query(AsaasExecutionLog).filter(AsaasExecutionLog.company_id == company_id)
        if status:
            q = q.filter(AsaasExecutionLog.status == status)
        logs = q.order_by(AsaasExecutionLog.created_at.desc()).limit(limit).all()
        return [
            {
                "id": log.id,
                "asaas_payment_id": log.asaas_payment_id,
                "status": log.status,
                "ca_customer_id": log.ca_customer_id,
                "ca_receivable_id": log.ca_receivable_id,
                "error_detail": log.error_detail,
                "duration_ms": log.duration_ms,
                "created_at": log.created_at,
            }
            for log in logs
        ]
    finally:
        db.close()


@router.get("/companies/{company_id}/asaas/logs/{log_id}")
def get_asaas_log(company_id: int, log_id: int):
    db: Session = SessionLocal()
    try:
        _get_company_or_404(db, company_id)
        log = db.query(AsaasExecutionLog).filter(
            AsaasExecutionLog.id == log_id,
            AsaasExecutionLog.company_id == company_id,
        ).first()
        if not log:
            raise HTTPException(status_code=404, detail="Log não encontrado")
        return {
            "id": log.id,
            "asaas_payment_id": log.asaas_payment_id,
            "status": log.status,
            "ca_customer_id": log.ca_customer_id,
            "ca_receivable_id": log.ca_receivable_id,
            "error_detail": log.error_detail,
            "payload_summary": log.payload_summary,
            "duration_ms": log.duration_ms,
            "created_at": log.created_at,
        }
    finally:
        db.close()
