from app.services.ca_payload_builder import build_ca_payload


def build_ca_sale_payload(
    id_cliente: str,
    numero: str | int,
    sale,
    items: list,
    id_conta_financeira: str | None = None,
    product_uuid_map: dict | None = None,
) -> dict:
    """
    Monta payload final para criar venda no Conta Azul.

    - build_ca_payload(sale) monta o corpo base (itens, datas, condição, desconto, centro de custo)
    - Se sale.sale_number estiver preenchido, usa esse número — senão usa o automático do CA
    - product_uuid_map: {nome_produto → uuid_ca} para injetar id nos itens
    - Injeta id_cliente e id_conta_financeira
    """
    try:
        sale.items = items
    except Exception:
        pass

    payload = build_ca_payload(sale, product_uuid_map=product_uuid_map)

    payload["id_cliente"] = id_cliente

    # Número da venda: usa o da planilha se informado, senão usa o automático do CA
    sale_number = getattr(sale, "sale_number", None)
    payload["numero"] = str(sale_number) if sale_number else str(numero)

    if id_conta_financeira:
        payload.setdefault("condicao_pagamento", {})
        if not isinstance(payload["condicao_pagamento"], dict):
            payload["condicao_pagamento"] = {}
        payload["condicao_pagamento"]["id_conta_financeira"] = id_conta_financeira

    return payload
