import unicodedata
from sqlalchemy.orm import Session

from app.services.conta_azul_client import ContaAzulClient
from app.db.models import CompanyCustomer


def _normalize_customer_key(name: str) -> str:
    """
    Normaliza nome do cliente para usar como chave de cache.
    - Remove acentos
    - Uppercase
    - Remove espaços extras
    - Remove caracteres especiais
    
    Exemplo: "João da Silva" -> "JOAO DA SILVA"
    """
    name = str(name).strip().upper()
    # Remove acentos (NFD = decompose, depois remove marcas diacríticas)
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ASCII", "ignore").decode("ASCII")
    # Remove espaços múltiplos
    name = " ".join(name.split())
    return name


def get_or_create_customer_uuid(client: ContaAzulClient, customer_name: str) -> str:
    """
    Busca cliente no Conta Azul por nome exato.
    Se não existir, cria um novo cliente.
    
    Returns:
        UUID do cliente no Conta Azul (id)
    """
    name = (customer_name or "").strip()
    if not name:
        raise RuntimeError("customer_name vazio - não dá pra criar/buscar cliente no CA")
    
    # 1) Busca cliente existente no CA
    try:
        resp = client.list_people(nome=name, tipo_perfil="Cliente")
        pessoas = resp if isinstance(resp, list) else []
        
        # Busca match exato (case-insensitive)
        name_normalized = name.upper()
        for p in pessoas:
            if p.get("nome", "").upper() == name_normalized:
                ca_id = p.get("id")
                if ca_id:
                    return str(ca_id)
    except Exception as e:
        # Se falhar a busca, continua pra criar
        print(f"[WARN] Erro ao buscar cliente '{name}' no CA: {e}")
    
    # 2) Cliente não existe -> cria novo
    try:
        resp = client.create_person_cliente(nome=name)
        ca_id = resp.get("id")
        if not ca_id:
            raise RuntimeError(f"CA não retornou 'id' ao criar cliente: {resp}")
        return str(ca_id)
    except Exception as e:
        raise RuntimeError(f"Erro ao criar cliente '{name}' no Conta Azul: {e}")


def get_or_create_customer_uuid_cached(
    db: Session,
    client: ContaAzulClient,
    company_id: int,
    customer_name: str,
) -> str:
    """
    Versão com cache em banco.
    
    Fluxo:
    1. Normaliza nome -> chave
    2. Busca no cache local (CompanyCustomer)
    3. Se não existir, chama get_or_create_customer_uuid()
    4. Salva no cache
    5. Retorna UUID
    """
    name = (customer_name or "").strip()
    if not name:
        raise RuntimeError("customer_name vazio (não dá pra criar/buscar cliente)")

    key = _normalize_customer_key(name)

    # Busca no cache local
    cached = (
        db.query(CompanyCustomer)
        .filter(CompanyCustomer.company_id == company_id)
        .filter(CompanyCustomer.customer_key == key)
        .first()
    )
    if cached and cached.ca_customer_id:
        return cached.ca_customer_id

    # Não está em cache -> busca/cria no CA
    ca_uuid = get_or_create_customer_uuid(client, name)

    # Atualiza cache
    if cached:
        cached.ca_customer_id = ca_uuid
        cached.customer_name = name
        db.add(cached)
    else:
        db.add(
            CompanyCustomer(
                company_id=company_id,
                customer_key=key,
                customer_name=name,
                ca_customer_id=ca_uuid,
            )
        )
    db.commit()

    return ca_uuid
