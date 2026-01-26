from app.services.ca_payload_builder import build_ca_payload


def build_ca_sale_payload(
    id_cliente: str,
    numero: str | int,
    sale,
    items: list,
    id_conta_financeira: str | None = None,
) -> dict:
    # Garante que o builder enxergue os itens (ele lê sale.items)
    try:
        sale.items = items
    except Exception:
        pass

    payload = build_ca_payload(sale)

    payload["id_cliente"] = id_cliente
    payload["numero"] = str(numero)

    # TESTE: forçar condicao_pagamento como UUID fake (36 chars)
    payload["condicao_pagamento"] = "00000000-0000-0000-0000-000000000000"

    return payload
