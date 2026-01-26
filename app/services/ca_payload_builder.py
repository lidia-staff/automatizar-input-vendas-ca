from datetime import date
from typing import Dict


def _normalize_payment_method(raw: str) -> str:
    s = (raw or "").strip().upper()

    if "PIX" in s:
        return "PIX_PAGAMENTO_INSTANTANEO"
    if "BOLETO" in s:
        return "BOLETO_BANCARIO"
    if "CRÉDITO" in s or "CREDITO" in s:
        return "CARTAO_CREDITO"
    if "DÉBITO" in s or "DEBITO" in s:
        return "CARTAO_DEBITO"
    if "TRANSFER" in s:
        return "TRANSFERENCIA_BANCARIA"
    if "DINHEIRO" in s:
        return "DINHEIRO"

    return "OUTRO"


def _parcelas_qtd(payment_terms: str) -> int:
    t = (payment_terms or "").strip().upper()
    if "À VISTA" in t or "A VISTA" in t:
        return 1
    digits = "".join([c for c in t if c.isdigit()])
    if digits:
        try:
            n = int(digits)
            return max(1, n)
        except Exception:
            return 1
    return 1


def _build_parcelas(total: float, due_date: date, parcelas: int = 1):
    valor_parcela = round(total / parcelas, 2)
    return [{"data_vencimento": str(due_date), "valor": valor_parcela} for _ in range(parcelas)]


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


def build_ca_payload(sale) -> Dict:
    tipo_pagamento = _normalize_payment_method(sale.payment_method)
    n_parcelas = _parcelas_qtd(sale.payment_terms or "")

    payload = {
        "situacao": "EM_ANDAMENTO",
        "data_venda": str(sale.sale_date),
        "observacoes": "Venda importada automaticamente.",
        "itens": _build_itens(sale),
        "condicao_pagamento": {
            "tipo_pagamento": tipo_pagamento,
            "opcao_condicao_pagamento": "À vista" if n_parcelas == 1 else f"{n_parcelas}x",
            "parcelas": _build_parcelas(
                total=float(sale.total_amount),
                due_date=sale.due_date,
                parcelas=n_parcelas,
            ),
        },
    }

    return payload
