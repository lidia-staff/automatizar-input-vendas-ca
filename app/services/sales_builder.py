import uuid


def map_payment_method_to_tipo_pagamento(pm: str | None) -> str:
    """
    Mapeia seu texto interno para enum tipo_pagamento da Conta Azul.
    Se não souber, cai em OUTRO.
    """
    s = (pm or "").strip().lower()

    if "pix" in s:
        return "PIX_PAGAMENTO_INSTANTANEO"
    if "dinheiro" in s or "cash" in s:
        return "DINHEIRO"
    if "debito" in s:
        return "CARTAO_DEBITO"
    if "credito" in s:
        return "CARTAO_CREDITO"
    if "transfer" in s or "ted" in s or "doc" in s:
        return "TRANSFERENCIA_BANCARIA"
    if "boleto" in s:
        return "BOLETO_BANCARIO"

    return "OUTRO"


def build_ca_sale_payload(
    *,
    id_cliente: str,
    numero: int,
    sale,
    items,
    id_conta_financeira: str,
) -> dict:
    """
    Monta payload no formato exigido por POST /v1/venda.
    Campos obrigatórios: id_cliente, numero, situacao, data_venda, itens[], condicao_pagamento.
    """
    # total e datas vêm do seu Sale
    data_venda = str(sale.sale_date)
    data_venc = str(sale.due_date)

    # itens exigem: id(UUID), quantidade, valor
    ca_items = []
    for it in items:
        ca_items.append(
            {
                "id": str(uuid.uuid4()),  # UUID válido com 36 chars
                "descricao": (it.product_service or it.details or "-"),
                "quantidade": float(it.qty),
                "valor": float(it.unit_price),
            }
        )

    # condição de pagamento (obrigatória)
    # regra simples: 1 parcela à vista no vencimento, valor total.
    payload = {
        "id_cliente": id_cliente,
        "numero": int(numero),
        "situacao": "EM_ANDAMENTO",
        "data_venda": data_venda,
        "observacoes": "Venda importada automaticamente (MVP).",
        "itens": ca_items,
        "condicao_pagamento": {
            "tipo_pagamento": map_payment_method_to_tipo_pagamento(sale.payment_method),
            "id_conta_financeira": id_conta_financeira,
            "opcao_condicao_pagamento": "À vista",
            "parcelas": [
                {
                    "data_vencimento": data_venc,
                    "valor": float(sale.total_amount),
                    "descricao": "Parcela 1",
                }
            ],
        },
    }

    return payload