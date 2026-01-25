from app.services.conta_azul_client import ContaAzulClient


def get_or_create_customer_uuid(client: ContaAzulClient, customer_name: str) -> str:
    """
    Tenta achar cliente pelo nome via GET /v1/pessoas.
    Se não achar, cria via POST /v1/pessoas e retorna o UUID.
    """
    name = (customer_name or "").strip()
    if not name:
        raise RuntimeError("customer_name vazio (não dá pra criar/buscar cliente)")

    data = client.list_people(nome=name, tipo_perfil="Cliente")

    # Resposta típica: { "totalItems": 340, "items": [ { "id": "...", "nome": "..." } ] }
    items = data.get("items") or []

    # tenta match exato por nome (case-insensitive)
    for p in items:
        if (p.get("nome") or "").strip().lower() == name.lower():
            return p["id"]

    # se não achou exato, usa o primeiro (quando API retorna “parecidos”)
    if items:
        return items[0]["id"]

    created = client.create_person_cliente(nome=name)
    return created["id"]