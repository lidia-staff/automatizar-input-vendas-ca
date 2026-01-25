from datetime import date
from typing import Dict

# ==============================
# MAPAS DE CONTA AZUL
# ==============================

# Tipos de pagamento aceitos pelo Conta Azul
PAYMENT_METHOD_MAP = {
    "PIX": "PIX_PAGAMENTO_INSTANTANEO",
    "DINHEIRO": "DINHEIRO",
    "CARTAO_CREDITO": "CARTAO_CREDITO",
    "CARTAO_DEBITO": "CARTAO_DEBITO",
    "TRANSFERENCIA": "TRANSFERENCIA_BANCARIA",
}

# ⚠️ Estes IDs você ajusta por empresa depois
# Por enquanto funciona como default
DEFAULT_FINANCIAL_ACCOUNTS = {
    "PIX": "UUID_CONTA_PIX",
    "DINHEIRO": "UUID_CONTA_CAIXA",
    "CARTAO_CREDITO": "UUID_CONTA_CARTAO",
    "CARTAO_DEBITO": "UUID_CONTA_CARTAO",
    "TRANSFERENCIA": "UUID_CONTA_BANCO",
}


# ==============================
# FUNÇÕES AUXILIARES
# ==============================

def _build_parcelas(
    total: float,
    due_date: date,
    parcelas: int = 1,
):
    """Gera parcelas iguais"""
    valor_parcela = round(total / parcelas, 2)
    return [
        {
            "data_vencimento": str(due_date),
            "valor": valor_parcela,
        }
        for _ in range(parcelas)
    ]


def _build_itens(sale) -> list:
    itens = []
    for i in sale.items:
        itens.append(
            {
                "descricao": i.product_service,
                "quantidade": float(i.qty),
                "valor": float(i.unit_price),
            }
        )
    return itens


# ==============================
# BUILDER PRINCIPAL
# ==============================

def build_ca_payload(sale) -> Dict:
    """
    Constrói o payload de venda para o Conta Azul.
    REGRA FIXA: SEMPRE EM_ANDAMENTO (revisão pendente).
    """

    payment_method = sale.payment_method.upper()
    payment_terms = sale.payment_terms or ""

    tipo_pagamento = PAYMENT_METHOD_MAP.get(payment_method)
    if not tipo_pagamento:
        raise ValueError(f"Forma de pagamento não suportada: {payment_method}")

    # Número de parcelas (default = 1)
    parcelas_qtd = 1
    if "PARCEL" in payment_terms.upper():
        try:
            parcelas_qtd = int("".join(filter(str.isdigit, payment_terms)))
        except Exception:
            parcelas_qtd = 1

    payload = {
        "situacao": "EM_ANDAMENTO",  # 🔒 REGRA DE OURO
        "data_venda": str(sale.sale_date),
        "observacoes": (
            "Venda importada automaticamente.\n"
            "⚠️ Revisão manual obrigatória antes da aprovação."
        ),
        "itens": _build_itens(sale),
        "condicao_pagamento": {
            "tipo_pagamento": tipo_pagamento,
            "opcao_condicao_pagamento": "À vista"
            if parcelas_qtd == 1
            else f"{parcelas_qtd}x",
            "parcelas": _build_parcelas(
                total=float(sale.total_amount),
                due_date=sale.due_date,
                parcelas=parcelas_qtd,
            ),
        },
    }

    # Conta financeira (se existir)
    account_id = DEFAULT_FINANCIAL_ACCOUNTS.get(payment_method)
    if account_id:
        payload["condicao_pagamento"]["id_conta_financeira"] = account_id

    return payload