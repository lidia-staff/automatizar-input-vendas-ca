import hashlib
from decimal import Decimal
from typing import List, Dict, Tuple

from app.db.models import Sale, SaleItem, Company
from app.services.validate import validate_item


def _to_decimal(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0")
    return Decimal(str(v).replace(",", "."))


def _build_group_key(row: dict) -> str:
    # records já vêm com datas como date (import_xlsx converte)
    d = row["DATA ATENDIMENTO"].isoformat()
    venc = row["VENCIMENTO"].isoformat()
    cliente = str(row["CLIENTE / PACIENTE"]).strip()
    forma = str(row["FORMA DE PAGAMENTO"]).strip()
    cond = str(row["CONDICAO DE PAGAMENTO"]).strip()
    conta = str(row["CONTA DE RECEBIMENTO"]).strip()
    return f"{d}|{cliente}|{forma}|{cond}|{conta}|{venc}"


def _hash_unique(group_key: str, items_signature: str) -> str:
    raw = f"{group_key}::{items_signature}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def create_sales_from_records(
    *,
    db,
    company_id: int,
    batch_id: int,
    records: List[Dict],
) -> Tuple[int, int, int, int, int]:
    """
    Cria Sales + SaleItems a partir dos records importados da planilha.

    Retorna:
      (created, ready, awaiting, with_error, items_with_error)
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise ValueError("company_not_found")

    # Agrupa itens por chave de venda
    grouped: dict[str, list[dict]] = {}
    item_errors_count = 0

    for row in records:
        errs = validate_item(row)
        if errs:
            item_errors_count += 1
            # ainda assim agrupa, mas essa venda provavelmente ficará ERRO
        gk = _build_group_key(row)
        grouped.setdefault(gk, []).append(row)

    created = ready = awaiting = with_error = 0

    for group_key, rows in grouped.items():
        # monta assinatura dos itens (pra deduplicar)
        sig_parts = []
        total = Decimal("0")

        has_error = False
        error_msgs = []

        for r in rows:
            errs = validate_item(r)
            if errs:
                has_error = True
                error_msgs.extend(errs)

            qty = _to_decimal(r.get("QUANTIDADE"))
            unit = _to_decimal(r.get("VALOR UNITARIO"))
            line_total = (qty * unit).quantize(Decimal("0.01"))
            total += line_total

            sig_parts.append(f"{r.get('PRODUTOS/SERVIÇOS')}|{qty}|{unit}")

        items_signature = "||".join(sig_parts)
        hash_unique = _hash_unique(group_key, items_signature)

        # evita duplicar se já existe igual no batch
        exists = (
            db.query(Sale)
            .filter(Sale.company_id == company_id, Sale.batch_id == batch_id, Sale.hash_unique == hash_unique)
            .first()
        )
        if exists:
            continue

        sale_date = rows[0]["DATA ATENDIMENTO"]
        due_date = rows[0]["VENCIMENTO"]
        customer_name = rows[0]["CLIENTE / PACIENTE"]
        payment_method = rows[0]["FORMA DE PAGAMENTO"]
        payment_terms = rows[0]["CONDICAO DE PAGAMENTO"]
        receiving_account = rows[0]["CONTA DE RECEBIMENTO"]

        if has_error:
            status = "ERRO"
            error_summary = "; ".join(sorted(set(error_msgs)))[:1000]
            with_error += 1
        else:
            if company.review_mode:
                status = "AGUARDANDO_APROVACAO"
                awaiting += 1
            else:
                status = "PRONTA"
                ready += 1
            error_summary = None

        sale = Sale(
            company_id=company_id,
            batch_id=batch_id,
            group_key=group_key,
            hash_unique=hash_unique,
            sale_date=sale_date,
            customer_name=customer_name,
            payment_method=payment_method,
            payment_terms=payment_terms,
            receiving_account=receiving_account,
            due_date=due_date,
            total_amount=total,
            status=status,
            error_summary=error_summary,
        )
        db.add(sale)
        db.commit()
        db.refresh(sale)

        # cria itens
        for r in rows:
            qty = _to_decimal(r.get("QUANTIDADE"))
            unit = _to_decimal(r.get("VALOR UNITARIO"))
            line_total = (qty * unit).quantize(Decimal("0.01"))

            item = SaleItem(
                sale_id=sale.id,
                category=(r.get("CATEGORIA") or None),
                product_service=str(r.get("PRODUTOS/SERVIÇOS") or "-"),
                details=(r.get("DETALHES DO ITEM") or None),
                qty=qty,
                unit_price=unit,
                line_total=line_total,
            )
            db.add(item)

        db.commit()

        created += 1

    return created, ready, awaiting, with_error, item_errors_count
