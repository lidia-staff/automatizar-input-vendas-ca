from datetime import date
from decimal import Decimal, InvalidOperation

def _to_decimal(v):
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v).replace(",", "."))
    except InvalidOperation:
        return None

def validate_item(row: dict) -> list[str]:
    errors = []

    if not row.get("DATA ATENDIMENTO"):
        errors.append("DATA ATENDIMENTO obrigatório.")
    if not row.get("CLIENTE / PACIENTE"):
        errors.append("CLIENTE / PACIENTE obrigatório.")

    qty = _to_decimal(row.get("QUANTIDADE"))
    if qty is None or qty <= 0:
        errors.append("QUANTIDADE deve ser numérica e > 0.")

    unit = _to_decimal(row.get("VALOR UNITARIO"))
    if unit is None or unit < 0:
        errors.append("VALOR UNITARIO deve ser numérico e >= 0.")

    if not row.get("FORMA DE PAGAMENTO"):
        errors.append("FORMA DE PAGAMENTO obrigatório.")

    if not row.get("CONDICAO DE PAGAMENTO"):
        errors.append("CONDICAO DE PAGAMENTO obrigatório.")

    if not row.get("CONTA DE RECEBIMENTO"):
        errors.append("CONTA DE RECEBIMENTO obrigatório.")

    if not row.get("VENCIMENTO"):
        errors.append("VENCIMENTO obrigatório.")

    # consistência de datas (se vierem como datetime/date, ok)
    dt = row.get("DATA ATENDIMENTO")
    venc = row.get("VENCIMENTO")
    if dt and venc:
        try:
            # pandas costuma vir Timestamp; comparável
            if venc.date() < dt.date():
                errors.append("VENCIMENTO não pode ser anterior à DATA ATENDIMENTO.")
        except Exception:
            # se não der pra comparar, deixa a validação simples
            pass

    return errors