from app.services.contaazul_people import get_or_create_customer_id
from app.services.ca_payload_builder import build_ca_payload


def build_sale_payload_with_customer(sale, ca_access_token: str) -> dict:
    """
    1) resolve o id_cliente no Conta Azul (busca ou cria)
    2) monta o payload da venda SEMPRE EM_ANDAMENTO
    3) injeta id_cliente no payload
    """

    # no MVP você pode começar só com o nome
    customer_id = get_or_create_customer_id(
        ca_access_token,
        nome=sale.customer_name,
        email=getattr(sale, "customer_email", None),
        documento=getattr(sale, "customer_document", None),
        telefone=getattr(sale, "customer_phone", None),
        observacao="Criado automaticamente pelo integrador (venda em revisão).",
    )

    payload = build_ca_payload(sale)  # já vem com situacao="EM_ANDAMENTO"
    payload["id_cliente"] = customer_id
    return payload