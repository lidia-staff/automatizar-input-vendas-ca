from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.db.models import Company

router = APIRouter(tags=["debug"])


@router.get("/debug/company/{company_id}/status")
def debug_company_status(company_id: int):
    """
    Endpoint de diagnóstico para verificar status completo da company.
    """
    db: Session = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        
        if not company:
            raise HTTPException(status_code=404, detail=f"Company {company_id} não encontrada")
        
        # Verifica expiração do token
        now = datetime.now(timezone.utc)
        token_expired = None
        token_valid = False
        
        if company.token_expires_at:
            expires_at = company.token_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            
            token_expired = expires_at < now
            token_valid = not token_expired
        
        return {
            "company_id": company.id,
            "name": company.name,
            "oauth_status": {
                "has_access_token": bool(company.access_token),
                "has_refresh_token": bool(company.refresh_token),
                "token_expires_at": company.token_expires_at.isoformat() if company.token_expires_at else None,
                "token_expired": token_expired,
                "token_valid": token_valid,
                "needs_reauth": not company.refresh_token or not company.access_token,
            },
            "configuration": {
                "ca_financial_account_id": company.ca_financial_account_id,
                "has_financial_account": bool(company.ca_financial_account_id),
                "default_item_id": getattr(company, "default_item_id", None),
                "has_default_item": bool(getattr(company, "default_item_id", None)),
                "review_mode": getattr(company, "review_mode", True),
            },
            "recommendations": _get_recommendations(company, token_valid),
        }
    finally:
        db.close()


def _get_recommendations(company: Company, token_valid: bool) -> list[str]:
    """Gera recomendações baseadas no estado atual."""
    recs = []
    
    if not company.refresh_token or not company.access_token:
        recs.append(
            f"❌ CRÍTICO: Tokens OAuth ausentes. Reautorize em /api/contaazul/start?company_id={company.id}"
        )
    elif not token_valid:
        recs.append(f"⚠️ Token expirado. Sistema tentará refresh automático.")
    else:
        recs.append("✅ OAuth OK - Tokens válidos")
    
    if not company.ca_financial_account_id:
        recs.append(f"⚠️ Conta financeira não configurada. Configure antes de enviar vendas.")
    else:
        recs.append("✅ Conta financeira configurada")
    
    return recs


@router.get("/debug/company/{company_id}/test-ca-connection")
def test_ca_connection(company_id: int):
    """
    Testa conexão com Conta Azul.
    """
    from app.services.conta_azul_client import ContaAzulClient
    
    try:
        client = ContaAzulClient(company_id=company_id)
        result = client.get_next_sale_number()
        
        return {
            "ok": True,
            "company_id": company_id,
            "ca_connection": "success",
            "next_sale_number": result,
            "message": "✅ Conexão OK! Token Manager funcionando."
        }
    
    except RuntimeError as e:
        error_msg = str(e)
        
        if "refresh_token" in error_msg.lower() or "401" in error_msg:
            suggestion = f"Reautorize em: /api/contaazul/start?company_id={company_id}"
        else:
            suggestion = "Verifique logs do servidor"
        
        raise HTTPException(
            status_code=500,
            detail={
                "error": error_msg,
                "suggestion": suggestion,
                "company_id": company_id,
            }
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "error": str(e),
                "suggestion": "Erro inesperado. Verifique logs.",
                "company_id": company_id,
            }
        )
