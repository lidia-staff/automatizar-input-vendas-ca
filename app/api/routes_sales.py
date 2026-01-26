from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Sale, SaleItem, Company
from app.services.conta_azul_client import ContaAzulClient
from app.services.contaazul_people import get_or_create_customer_uuid
from app.services.ca_sale_builder import build_ca_sale_payload

# ✅ Export padrão que o main.py espera
router = APIRouter(tags=["sales"])

# ✅ Alias de compatibilidade (se em algum lugar estiverem usando sales_router)
sales_router = router


@router.get("/sales")
def list_sales(company_id: int | None = None, batch_id: int | None = None, status: str | None = None):
    db: Session = SessionLocal()
    try:
        q = db.query(Sale)
        if company_id is not None:
            q = q.filter(Sale.company_id == company_id)
        if batch_id is not None:
            q = q.filter(Sale.batch_id == batch_id)
        if status is not None:
            q = q.filter(Sale.status == status)
        rows = q.order_by(Sale.id.asc()).all()
        return rows
    finally:
        db.close()


@router.get("/sales/{sale_id}")
def get_sale(sale_id: int):
    db: Session = SessionLocal()
    try:
        s = db.query(Sale).filter(Sale.id == sale_id).first()
        if not s:
            raise HTTPException(status_code=404, detail="Sale não encontrada")
        items = db.query(SaleItem).filter(SaleItem.sale_id == sale_id).all()
        return {"sale": s, "items": items}
    finally:
        db.close()


@router.post("/sales/{sale_id}/send_to_ca")
def send_to_ca(sale_id: int):
    """
    Envia a venda para Conta Azul:
    - refresh token automático
    - garante cliente (pessoa) existe e pega UUID
    - pega próximo número disponível
    - monta payload no padrão /v1/venda
    """
    db: Session = SessionLocal()
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale não encontrada")

        company = db.query(Company).filter(Company.id == sale.company_id).first()
        if not company:
            raise HTTPException(status_code=400, detail="Company não encontrada")

        if not company.ca_financial_account_id:
            raise HTTPException(
                status_code=400,
                detail="Company sem ca_financial_account_id (UUID da conta financeira). Preencha antes de enviar.",
            )

        items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
        if not items:
            raise HTTPException(status_code=400, detail="Sale sem itens")

        client = ContaAzulClient(company_id=company.id)

        customer_uuid = get_or_create_customer_uuid(client, sale.customer_name)

        numero = client.get_next_sale_number()

        payload = build_ca_sale_payload(
            id_cliente=customer_uuid,
            numero=numero,
            sale=sale,
            items=items,
            id_conta_financeira=company.ca_financial_account_id,
        )

        resp = client.create_sale(payload)

        sale.ca_sale_id = resp.get("id") or sale.ca_sale_id
        sale.status = "ENVIADA_CA"
        sale.error_summary = None
        db.add(sale)
        db.commit()
        db.refresh(sale)

        return {"ok": True, "sale_id": sale.id, "ca_response": resp}

    except HTTPException:
        raise
    except Exception as e:
        # registra erro e não derruba API
        try:
            s2 = db.query(Sale).filter(Sale.id == sale_id).first()
            if s2:
                s2.status = "ERRO_ENVIO_CA"
                s2.error_summary = str(e)[:1000]
                db.add(s2)
                db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
