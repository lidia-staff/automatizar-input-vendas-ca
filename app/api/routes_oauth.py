import os
import secrets
import urllib.parse
import datetime as dt
import requests

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company

router = APIRouter(tags=["oauth"])


def _env_or_fail(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise HTTPException(status_code=500, detail=f"{name} não configurado")
    return v


@router.get("/api/contaazul/start")
def contaazul_start(company_id: int):
    """
    Abre a tela de login/autorização do Conta Azul.
    Estilo Pluga: você clica numa URL e já vai pro consent.
    """
    ca_client_id = _env_or_fail("CA_CLIENT_ID")
    redirect_uri = _env_or_fail("CA_REDIRECT_URI")

    # scope default (pode ajustar via variável)
    scope = "sales"

    nonce = secrets.token_urlsafe(16)
    state = f"{company_id}:{nonce}"

    params = {
        "response_type": "code",
        "client_id": ca_client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope,
    }

    url = "https://auth.contaazul.com/login?" + urllib.parse.urlencode(params)
    return RedirectResponse(url=url, status_code=302)


@router.get("/api/contaazul/callback")
def contaazul_callback(code: str, state: str):
    """
    Troca o code por tokens e salva na Company.
    O Conta Azul redireciona pra cá (redirect_uri).
    """
    ca_client_id = _env_or_fail("CA_CLIENT_ID")
    ca_client_secret = _env_or_fail("CA_CLIENT_SECRET")
    redirect_uri = _env_or_fail("CA_REDIRECT_URI")

    try:
        company_id = int(state.split(":")[0])
    except Exception:
        raise HTTPException(status_code=400, detail="state inválido")

    token_url = "https://auth.contaazul.com/oauth2/token"

    r = requests.post(
        token_url,
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
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))

    if not access_token or not refresh_token:
        raise HTTPException(status_code=400, detail=f"Retorno sem tokens: {data}")

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
    finally:
        db.close()

    # Página simples de sucesso (pra não ficar "json perdido")
    html = f"""
    <html>
      <body style="font-family: Arial; padding: 24px;">
        <h2>✅ Conta Azul conectado com sucesso</h2>
        <p>Company ID: <b>{company_id}</b></p>
        <p>Você já pode voltar para a plataforma e enviar as vendas.</p>
      </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)
