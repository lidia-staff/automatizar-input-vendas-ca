from app.services.ca_payload_builder import build_ca_payload


def build_ca_sale_payload(
    id_cliente: str,
    numero: str | int,
    sale,
    items: list,
    id_conta_financeira: str | None = None,
) -> dict:
    """
    Monta payload final para criar venda no Conta Azul.
    - build_ca_payload(sale) monta o corpo base (itens, datas, condição etc.)
    - injeta id_cliente e numero
    - injeta id_conta_financeira (UUID 36 chars) dentro de condicao_pagamento
    """

    # garante que o builder base enxergue os itens
    try:
        sale.items = items
    except Exception:
        pass

    payload = build_ca_payload(sale)

    # campos obrigatórios do endpoint de venda
    payload["id_cliente"] = id_cliente
    payload["numero"] = str(numero)

    # injeta conta financeira APENAS se veio preenchida
    if id_conta_financeira:
        payload.setdefault("condicao_pagamento", {})
        # se por acaso condicao_pagamento veio como string por erro em outro lugar
        if not isinstance(payload["condicao_pagamento"], dict):
            payload["condicao_pagamento"] = {}
        payload["condicao_pagamento"]["id_conta_financeira"] = id_conta_financeira

    return payload
