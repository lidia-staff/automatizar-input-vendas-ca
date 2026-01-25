import os
import datetime as dt
import requests
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company


class ContaAzulClient:
    """
    Cliente Conta Azul com:
    - tokens por company_id (banco)
    - refresh token automático
    - ✅ refresh-on-401 + retry 1 vez (estilo Pluga)
    """

    def __init__(self, company_id: int):
        self.company_id = company_id

        self.api_base = os.getenv("CA_API_BASE_URL", "https://api-v2.contaazul.com").rstrip("/")
        self.auth_url = os.getenv("CA_AUTH_URL", "https://auth.contaazul.com/oauth2/token")

        self.client_id = os.getenv("CA_CLIENT_ID")
        self.client_secret = os.getenv("CA_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise RuntimeError("CA_CLIENT_ID ou CA_CLIENT_SECRET não configurados")

        self._load_company_tokens()

        # renova se expirou (com folga)
        if self._is_token_expired():
            self._refresh_token()

    def _load_company_tokens(self):
        db: Session = SessionLocal()
        try:
            c = db.query(Company).filter(Company.id == self.company_id).first()
            if not c:
                raise RuntimeError("Company não encontrada")
            if not c.refresh_token:
                raise RuntimeError("Company sem refresh_token salvo no banco")
            if not c.access_token:
                raise RuntimeError("Company sem access_token salvo no banco")

            self.access_token = c.access_token
            self.refresh_token = c.refresh_token
            self.token_expires_at = c.token_expires_at
        finally:
            db.close()

    def _now_utc(self) -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    def _as_aware_utc(self, value: dt.datetime | None) -> dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)

    def _is_token_expired(self) -> bool:
        exp = self._as_aware_utc(self.token_expires_at)
        if exp is None:
            return True
        return self._now_utc() >= (exp - dt.timedelta(minutes=2))

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _save_tokens(self, new_access: str, new_refresh: str, expires_in: int):
        new_expires_at = self._now_utc() + dt.timedelta(seconds=int(expires_in))

        db: Session = SessionLocal()
        try:
            c = db.query(Company).filter(Company.id == self.company_id).first()
            if not c:
                raise RuntimeError("Company não encontrada para salvar refresh")
            c.access_token = new_access
            c.refresh_token = new_refresh
            c.token_expires_at = new_expires_at
            db.add(c)
            db.commit()
        finally:
            db.close()

        self.access_token = new_access
        self.refresh_token = new_refresh
        self.token_expires_at = new_expires_at

    def _refresh_token(self):
        r = requests.post(
            self.auth_url,
            auth=(self.client_id, self.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            timeout=30,
        )

        if r.status_code >= 400:
            # (caso refresh_token revogado, não tem milagre: precisa reconectar)
            raise RuntimeError(f"Falha ao refresh token: {r.status_code} - {r.text}")

        data = r.json()
        new_access = data["access_token"]
        new_refresh = data.get("refresh_token", self.refresh_token)
        expires_in = int(data.get("expires_in", 3600))

        self._save_tokens(new_access, new_refresh, expires_in)

    def _request(self, method: str, url: str, *, params=None, json=None, data=None, headers=None, timeout=60):
        """
        Request centralizado:
        - se 401: refresh + retry (1 vez)
        """
        hdr = headers or self._headers()

        r = requests.request(method, url, headers=hdr, params=params, json=json, data=data, timeout=timeout)

        if r.status_code == 401:
            # ✅ comportamento Pluga: renova e tenta de novo 1 vez
            self._refresh_token()
            hdr = headers or self._headers()
            r = requests.request(method, url, headers=hdr, params=params, json=json, data=data, timeout=timeout)

        if r.status_code >= 400:
            raise RuntimeError(f"ContaAzul error {r.status_code}: {r.text}")

        # algumas rotas retornam texto puro
        ct = (r.headers.get("Content-Type") or "").lower()
        if "application/json" in ct:
            return r.json()
        return r.text

    # ---------- ENDPOINTS CA ----------
    def get_next_sale_number(self) -> int:
        url = f"{self.api_base}/v1/venda/proximo-numero"
        txt = self._request("GET", url, timeout=20)
        try:
            return int(str(txt).strip())
        except Exception:
            raise RuntimeError(f"Resposta inesperada do próximo número: {txt}")

    def list_people(self, nome: str, tipo_perfil: str = "Cliente") -> dict:
        url = f"{self.api_base}/v1/pessoas"
        params = {"nome": nome, "tipo_perfil": tipo_perfil}
        return self._request("GET", url, params=params, timeout=20)

    def create_person_cliente(self, nome: str) -> dict:
        url = f"{self.api_base}/v1/pessoas"
        payload = {
            "nome": nome,
            "tipo_pessoa": "Física",
            "perfis": [{"tipo_perfil": "Cliente"}],
            "ativo": True,
        }
        return self._request("POST", url, json=payload, timeout=30)

    def create_sale(self, payload: dict) -> dict:
        url = f"{self.api_base}/v1/venda"
        return self._request("POST", url, json=payload, timeout=60)

    def list_financial_accounts(self) -> dict:
        # endpoint usado no teu teste anterior
        url = f"{self.api_base}/v1/conta-financeira"
        return self._request("GET", url, timeout=30)