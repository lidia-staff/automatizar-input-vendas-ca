from app.services.ca_payload_builder import build_ca_payload


def build_ca_sale_payload(
    id_cliente: str,
    numero: str | int,
    sale,
    items: list,
    id_conta_financeira: str | None = None,
) -> dict:
    """
    Monta o payload final da venda para o Conta Azul:
    - usa o builder padrão (build_ca_payload)
    - injeta id_cliente e numero
    - força id_conta_financeira se vier informado
    """

    # Garante que o builder enxergue os itens (ele lê sale.items)
    try:
        sale.items = items
    except Exception:
        pass

    payload = build_ca_payload(sale)

    # Campos essenciais
    payload["id_cliente"] = id_cliente
    payload["numero"] = str(numero)

    # Força conta financeira se informada pela Company
    if id_conta_financeira:
        payload.setdefault("condicao_pagamento", {})
        payload["condicao_pagamento"]["id_conta_financeira"] = id_conta_financeira

    return payload
