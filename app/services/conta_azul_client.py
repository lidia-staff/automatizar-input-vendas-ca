import os
import datetime as dt
import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.db.models import Company


class ContaAzulClient:
    """
    Cliente Conta Azul com Token Manager automático:
    
    ✅ Lê tokens do banco por company_id
    ✅ Refresh automático quando token expira
    ✅ Retry 1x em 401 (refresh + retry)
    ✅ Lock no banco para evitar race condition
    ✅ Persistência automática de novos tokens
    
    Uso:
        client = ContaAzulClient(company_id=1)
        vendas = client.list_sales()  # já gerencia token automaticamente
    """

    def __init__(self, company_id: int):
        self.company_id = company_id

        self.api_base = os.getenv("CA_API_BASE_URL", "https://api-v2.contaazul.com").rstrip("/")
        self.auth_url = os.getenv("CA_AUTH_URL", "https://auth.contaazul.com/oauth2/token")

        self.client_id = os.getenv("CA_CLIENT_ID")
        self.client_secret = os.getenv("CA_CLIENT_SECRET")
        if not self.client_id or not self.client_secret:
            raise RuntimeError("CA_CLIENT_ID ou CA_CLIENT_SECRET não configurados")

        # Carrega tokens do banco
        self._load_company_tokens()

        # Pré-refresh se já nasceu expirado
        if self._is_token_expired():
            self._refresh_token()

    def _load_company_tokens(self):
        """Carrega access_token, refresh_token e expires_at do banco."""
        db: Session = SessionLocal()
        try:
            c = db.query(Company).filter(Company.id == self.company_id).first()
            if not c:
                raise RuntimeError(f"Company {self.company_id} não encontrada")
            if not c.refresh_token:
                raise RuntimeError(
                    f"Company {self.company_id} sem refresh_token. "
                    "Execute o fluxo OAuth em /api/contaazul/start primeiro."
                )
            if not c.access_token:
                raise RuntimeError(f"Company {self.company_id} sem access_token salvo no banco")

            self.access_token = c.access_token
            self.refresh_token = c.refresh_token
            self.token_expires_at = c.token_expires_at
        finally:
            db.close()

    def _now_utc(self) -> dt.datetime:
        """Retorna datetime atual com timezone UTC."""
        return dt.datetime.now(dt.timezone.utc)

    def _as_aware_utc(self, value: dt.datetime | None) -> dt.datetime | None:
        """Converte datetime naive para aware UTC."""
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)

    def _is_token_expired(self) -> bool:
        """
        Verifica se token está expirado (com margem de 2min de segurança).
        
        Returns:
            True se expirado ou sem expires_at
        """
        exp = self._as_aware_utc(self.token_expires_at)
        if exp is None:
            return True
        # Margem de segurança de 2 minutos
        return self._now_utc() >= (exp - dt.timedelta(minutes=2))

    def _headers(self):
        """Headers para requests ao Conta Azul."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _refresh_token(self):
        """
        Renova access_token usando refresh_token e persiste no banco.
        
        ✅ Lê refresh_token mais recente do banco (evita usar token velho)
        ✅ Usa lock (FOR UPDATE) para reduzir race condition
        ✅ Persiste novos tokens no banco
        ✅ Atualiza tokens em memória
        
        Raises:
            RuntimeError: Se refresh falhar (ex: invalid_grant)
        """
        print(f"[TOKEN] Refreshing token for company {self.company_id}...")

        # 1) Lê refresh_token mais recente do banco
        db: Session = SessionLocal()
        try:
            c = db.query(Company).filter(Company.id == self.company_id).first()
            if not c:
                raise RuntimeError(f"Company {self.company_id} não encontrada para refresh")
            if not c.refresh_token:
                raise RuntimeError(
                    f"Company {self.company_id} sem refresh_token. "
                    "Reautorize em /api/contaazul/start"
                )
            refresh_to_use = c.refresh_token
        finally:
            db.close()

        # 2) Chama endpoint de refresh do Conta Azul
        try:
            r = requests.post(
                self.auth_url,
                auth=(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "refresh_token", "refresh_token": refresh_to_use},
                timeout=30,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Erro de rede ao fazer refresh: {e}")

        if r.status_code >= 400:
            # Ex: invalid_grant = refresh_token expirado/inválido
            raise RuntimeError(
                f"Token refresh failed [{r.status_code}]: {r.text}. "
                f"Reautorize a company {self.company_id} em /api/contaazul/start"
            )

        data = r.json()
        new_access = data.get("access_token")
        if not new_access:
            raise RuntimeError(f"Refresh retornou sem access_token: {data}")

        # Refresh token pode ou não vir novo (depende do provedor)
        new_refresh = data.get("refresh_token", refresh_to_use)
        expires_in = int(data.get("expires_in", 3600))
        new_expires_at = self._now_utc() + dt.timedelta(seconds=expires_in)

        # 3) Persiste com lock (FOR UPDATE) para reduzir race condition
        db = SessionLocal()
        try:
            c = (
                db.query(Company)
                .filter(Company.id == self.company_id)
                .with_for_update()
                .first()
            )
            if not c:
                raise RuntimeError(f"Company {self.company_id} não encontrada para salvar refresh")

            c.access_token = new_access
            c.refresh_token = new_refresh
            c.token_expires_at = new_expires_at
            db.add(c)
            db.commit()
            print(f"[TOKEN] ✅ Token refreshed for company {self.company_id}")
        except SQLAlchemyError as e:
            db.rollback()
            raise RuntimeError(f"Erro ao persistir tokens no banco: {e}")
        finally:
            db.close()

        # 4) Atualiza tokens em memória
        self.access_token = new_access
        self.refresh_token = new_refresh
        self.token_expires_at = new_expires_at

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        timeout: int = 30,
        _retried: bool = False,
    ):
        """
        Request centralizada com Token Manager automático.
        
        Estratégia:
        1. Verifica se token está perto de expirar -> refresh preventivo
        2. Faz request
        3. Se 401 e não tentou retry -> refresh + retry 1x
        4. Se 401 após retry -> erro fatal (reautorizar)
        
        Args:
            method: GET, POST, etc
            path: /v1/venda, etc
            params: query params
            json: body JSON
            timeout: timeout em segundos
            _retried: controle interno de retry
        
        Returns:
            Response JSON (dict/list) ou texto
        
        Raises:
            RuntimeError: Em caso de erro
        """
        # Pré-refresh se perto de expirar
        if self._is_token_expired():
            self._refresh_token()

        url = f"{self.api_base}{path}"
        
        try:
            r = requests.request(
                method, 
                url, 
                headers=self._headers(), 
                params=params, 
                json=json, 
                timeout=timeout
            )
        except requests.RequestException as e:
            raise RuntimeError(f"Erro de rede ao chamar {method} {path}: {e}")

        # Retry automático em 401 (token pode ter expirado entre requests)
        if r.status_code == 401 and not _retried:
            print(f"[TOKEN] 401 detected, refreshing and retrying...")
            self._refresh_token()
            
            try:
                r = requests.request(
                    method, 
                    url, 
                    headers=self._headers(), 
                    params=params, 
                    json=json, 
                    timeout=timeout
                )
            except requests.RequestException as e:
                raise RuntimeError(f"Erro de rede no retry: {e}")

        # Se ainda 401 após refresh -> problema sério
        if r.status_code == 401:
            raise RuntimeError(
                f"401 Unauthorized após refresh. "
                f"Company {self.company_id} precisa reautorizar em /api/contaazul/start"
            )

        # Outros erros HTTP
        if r.status_code >= 400:
            raise RuntimeError(
                f"Conta Azul API error [{r.status_code}] {method} {path}: {r.text}"
            )

        # Parse response
        txt = (r.text or "").strip()
        if txt.startswith("{") or txt.startswith("["):
            return r.json()
        return txt

    # ========== ENDPOINTS CONTA AZUL ==========

    def get_next_sale_number(self) -> int:
        """Retorna próximo número de venda disponível."""
        resp = self._request("GET", "/v1/venda/proximo-numero", timeout=20)
        try:
            return int(str(resp).strip())
        except Exception:
            raise RuntimeError(f"Resposta inesperada do próximo número: {resp}")

    def list_financial_accounts(self):
        """Lista contas financeiras da empresa no Conta Azul."""
        return self._request("GET", "/v1/conta-financeira", timeout=30)

    def list_products(self, busca: str, pagina: int = 1, tamanho_pagina: int = 50, status: str = "ATIVO"):
        """
        Lista produtos/serviços.
        
        Args:
            busca: termo de busca
            pagina: número da página
            tamanho_pagina: itens por página
            status: ATIVO, INATIVO, etc
        """
        params = {
            "pagina": pagina, 
            "tamanho_pagina": tamanho_pagina, 
            "busca": busca, 
            "status": status
        }
        return self._request("GET", "/v1/produtos", params=params, timeout=30)

    def list_people(self, nome: str, tipo_perfil: str = "Cliente") -> dict:
        """
        Lista pessoas (clientes, fornecedores, etc).
        
        Args:
            nome: nome para buscar
            tipo_perfil: Cliente, Fornecedor, etc
        
        Returns:
            Lista de pessoas encontradas
        """
        params = {"nome": nome, "tipo_perfil": tipo_perfil}
        return self._request("GET", "/v1/pessoas", params=params, timeout=30)

    def create_person_cliente(self, nome: str) -> dict:
        """
        Cria novo cliente no Conta Azul.
        
        Args:
            nome: nome do cliente
        
        Returns:
            Dados do cliente criado (incluindo 'id')
        """
        payload = {
            "nome": nome,
            "tipo_pessoa": "Física",
            "perfis": [{"tipo_perfil": "Cliente"}],
            "ativo": True,
        }
        return self._request("POST", "/v1/pessoas", json=payload, timeout=30)

    def create_sale(self, payload: dict) -> dict:
        """
        Cria venda no Conta Azul.
        
        Args:
            payload: payload completo da venda
        
        Returns:
            Response do CA (incluindo 'id' da venda criada)
        """
        return self._request("POST", "/v1/venda", json=payload, timeout=60)
