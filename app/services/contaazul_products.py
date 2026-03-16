import unicodedata
from sqlalchemy.orm import Session
from app.services.conta_azul_client import ContaAzulClient
from app.db.models import CompanyProduct


def _normalize_product_key(name: str) -> str:
    name = str(name).strip().upper()
    name = unicodedata.normalize("NFD", name)
    name = name.encode("ASCII", "ignore").decode("ASCII")
    name = " ".join(name.split())
    return name


def get_or_create_product_uuid(client: ContaAzulClient, product_name: str, item_type: str = "servico") -> str:
    name = (product_name or "").strip()
    if not name:
        raise RuntimeError("product_name vazio")

    name_upper = name.upper()

    if item_type == "produto":
        # Busca em produtos
        try:
            resp = client.list_products(busca=name)
            if isinstance(resp, dict):
                produtos = resp.get("itens", resp.get("content", []))
            elif isinstance(resp, list):
                produtos = resp
            else:
                produtos = []
            for p in produtos:
                if (p.get("nome") or "").upper() == name_upper:
                    ca_id = p.get("id")
                    if ca_id:
                        print(f"[PRODUCTS] Produto '{name}' encontrado no CA: {ca_id}")
                        return str(ca_id)
        except Exception as e:
            print(f"[PRODUCTS] Erro ao buscar produto '{name}': {e}")

        # Cria como produto
        try:
            resp = client.create_product(nome=name)
            ca_id = resp.get("id") if isinstance(resp, dict) else None
            if not ca_id:
                raise RuntimeError(f"CA não retornou 'id' ao criar produto: {resp}")
            print(f"[PRODUCTS] Produto '{name}' criado no CA: {ca_id}")
            return str(ca_id)
        except Exception as e:
            raise RuntimeError(f"Erro ao criar produto '{name}' no CA: {e}")

    else:
        # Busca em serviços primeiro
        try:
            resp = client.list_services(busca=name)
            itens = resp.get("itens", []) if isinstance(resp, dict) else []
            for p in itens:
                if (p.get("descricao") or "").upper() == name_upper:
                    ca_id = p.get("id")
                    if ca_id:
                        print(f"[PRODUCTS] Serviço '{name}' encontrado no CA: {ca_id}")
                        return str(ca_id)
        except Exception as e:
            print(f"[PRODUCTS] Erro ao buscar serviço '{name}': {e}")

        # Fallback: busca em produtos
        try:
            resp = client.list_products(busca=name)
            if isinstance(resp, dict):
                produtos = resp.get("itens", resp.get("content", []))
            elif isinstance(resp, list):
                produtos = resp
            else:
                produtos = []
            for p in produtos:
                if (p.get("nome") or "").upper() == name_upper:
                    ca_id = p.get("id")
                    if ca_id:
                        print(f"[PRODUCTS] Produto '{name}' encontrado no CA: {ca_id}")
                        return str(ca_id)
        except Exception as e:
            print(f"[PRODUCTS] Erro ao buscar produto '{name}': {e}")

        # Cria como serviço
        try:
            resp = client.create_service(nome=name)
            ca_id = resp.get("id") if isinstance(resp, dict) else None
            if not ca_id:
                raise RuntimeError(f"CA não retornou 'id' ao criar serviço: {resp}")
            print(f"[PRODUCTS] Serviço '{name}' criado no CA: {ca_id}")
            return str(ca_id)
        except Exception as e:
            raise RuntimeError(f"Erro ao criar serviço '{name}' no CA: {e}")


def get_or_create_product_uuid_cached(
    db: Session,
    client: ContaAzulClient,
    company_id: int,
    product_name: str,
    item_type: str = "servico",
) -> str:
    name = (product_name or "").strip()
    if not name:
        raise RuntimeError("product_name vazio")

    key = _normalize_product_key(name)

    # Verifica cache local
    cached = (
        db.query(CompanyProduct)
        .filter(CompanyProduct.company_id == company_id)
        .filter(CompanyProduct.product_key == key)
        .first()
    )
    if cached and cached.ca_product_id:
        print(f"[PRODUCTS] Cache hit para '{name}': {cached.ca_product_id}")
        return cached.ca_product_id

    # Busca ou cria no CA
    ca_uuid = get_or_create_product_uuid(client, name, item_type=item_type)

    # Salva no cache
    if cached:
        cached.ca_product_id = ca_uuid
        cached.product_name = name
        db.add(cached)
    else:
        db.add(CompanyProduct(
            company_id=company_id,
            product_key=key,
            product_name=name,
            ca_product_id=ca_uuid,
        ))
    db.commit()

    return ca_uuid
