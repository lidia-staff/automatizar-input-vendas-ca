import os
import secrets
import urllib.parse
import requests
import datetime as dt
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company

router = APIRouter(tags=["oauth"])

AUTH_LOGIN_URL = "https://auth.contaazul.com/login"
TOKEN_URL = "https://auth.contaazul.com/oauth2/token"


@router.get("/api/contaazul/start")
def contaazul_start(company_id: int = Query(..., description="ID da empresa no seu banco")):
    """
    Gera a URL de autorização (o cliente clica e autoriza).
    Depois a Conta Azul redireciona para CA_REDIRECT_URI (callback).
    """
    ca_client_id = os.getenv("CA_CLIENT_ID")
    redirect_uri = os.getenv("CA_REDIRECT_URI")  # ex: https://api.staffconsult.com.br/api/contaazul/callback

    if not ca_client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="CA_CLIENT_ID/CA_REDIRECT_URI não configurados")

    # valida se company existe (evita autorizar company_id inválido)
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")
    finally:
        db.close()

    # state: company_id + nonce (multi-tenant + anti-CSRF simples)
    nonce = secrets.token_urlsafe(16)
    state = f"{company_id}:{nonce}"

    params = {
        "response_type": "code",
        "client_id": ca_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        # escopos conforme docs do CA
        "scope": "openid profile aws.cognito.signin.user.admin",
    }

    auth_url = AUTH_LOGIN_URL + "?" + urllib.parse.urlencode(params)
    return {"auth_url": auth_url, "state": state}


@router.get("/api/contaazul/callback")
def contaazul_callback(code: str, state: str):
    """
    Callback OAuth: troca o 'code' por tokens e salva no banco na company correta.
    """
    ca_client_id = os.getenv("CA_CLIENT_ID")
    ca_client_secret = os.getenv("CA_CLIENT_SECRET")
    redirect_uri = os.getenv("CA_REDIRECT_URI")

    if not ca_client_id or not ca_client_secret or not redirect_uri:
        raise HTTPException(status_code=500, detail="Credenciais OAuth não configuradas")

    # extrai company_id do state
    try:
        company_id = int(state.split(":")[0])
    except Exception:
        raise HTTPException(status_code=400, detail="state inválido")

    # troca code por tokens
    r = requests.post(
        TOKEN_URL,
        auth=(ca_client_id, ca_client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )

    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"token_exchange_failed: {r.status_code} {r.text}")

    data = r.json()
    access_token = data["access_token"]
    refresh_token = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))

    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token ausente no retorno")

    # salva tokens
    db: Session = SessionLocal()
    try:
        c = db.query(Company).filter(Company.id == company_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Company não encontrada")

        c.access_token = access_token
        c.refresh_token = refresh_token
        c.token_expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=expires_in)

        db.add(c)
        db.commit()

        # retorna algo visível no navegador (melhor que JSON seco)
        return {
            "ok": True,
            "company_id": company_id,
            "message": "Conta Azul conectada com sucesso. Você já pode importar a planilha e enviar vendas.",
        }
    finally:
        db.close()