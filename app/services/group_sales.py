import hashlib
from decimal import Decimal

def build_group_key(row: dict) -> str:
    d = row["DATA ATENDIMENTO"].date().isoformat()
    venc = row["VENCIMENTO"].date().isoformat()
    cliente = str(row["CLIENTE / PACIENTE"]).strip()
    forma = str(row["FORMA DE PAGAMENTO"]).strip()
    cond = str(row["CONDICAO DE PAGAMENTO"]).strip()
    conta = str(row["CONTA DE RECEBIMENTO"]).strip()
    return f"{d}|{cliente}|{forma}|{cond}|{conta}|{venc}"

def calc_line_total(qty: Decimal, unit: Decimal) -> Decimal:
    return (qty * unit).quantize(Decimal("0.01"))

def make_hash_unique(group_key: str, items_signature: str) -> str:
    raw = f"{group_key}::{items_signature}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()