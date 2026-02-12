import unicodedata
from sqlalchemy.orm import Session
from app.services.conta_azul_client import ContaAzulClient
from app.db.models import CompanyCustomer


def _normalize_customer_key(name: str) -> str:
    name = str(name).strip().upper()
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ASCII", "ignore").decode("ASCII")
    name = " ".join(name.split())
    return name


def get_or_create_customer_uuid(client: ContaAzulClient, customer_name: str) -> str:
    name = (customer_name or "").strip()
    if not name:
        raise RuntimeError("customer_name vazio")

    # 1) Busca no CA
    try:
        resp = client.list_people(nome=name, tipo_perfil="Cliente")
        # resp pode ser dict com "itens" ou lista direta
        if isinstance(resp, dict):
            pessoas = resp.get("itens", resp.get("content", []))
        elif isinstance(resp, list):
            pessoas = resp
        else:
            pessoas = []

        name_upper = name.upper()
        for p in pessoas:
            if p.get("nome", "").upper() == name_upper:
                ca_id = p.get("id")
                if ca_id:
                    return str(ca_id)
    except Exception as e:
        print(f"[PEOPLE] Erro ao buscar cliente '{name}': {e}")

    # 2) Cria novo cliente
    try:
        resp = client.create_person_cliente(nome=name)
        # resp pode ser dict direto ou com "id"
        ca_id = resp.get("id") if isinstance(resp, dict) else None
        if not ca_id:
            raise RuntimeError(f"CA não retornou 'id': {resp}")
        return str(ca_id)
    except Exception as e:
        raise RuntimeError(f"Erro ao criar cliente '{name}': {e}")


def get_or_create_customer_uuid_cached(
    db: Session,
    client: ContaAzulClient,
    company_id: int,
    customer_name: str,
) -> str:
    name = (customer_name or "").strip()
    if not name:
        raise RuntimeError("customer_name vazio")

    key = _normalize_customer_key(name)

    cached = (
        db.query(CompanyCustomer)
        .filter(CompanyCustomer.company_id == company_id)
        .filter(CompanyCustomer.customer_key == key)
        .first()
    )
    if cached and cached.ca_customer_id:
        return cached.ca_customer_id

    ca_uuid = get_or_create_customer_uuid(client, name)

    if cached:
        cached.ca_customer_id = ca_uuid
        cached.customer_name = name
        db.add(cached)
    else:
        db.add(CompanyCustomer(
            company_id=company_id,
            customer_key=key,
            customer_name=name,
            ca_customer_id=ca_uuid,
        ))
    db.commit()

    return ca_uuid
