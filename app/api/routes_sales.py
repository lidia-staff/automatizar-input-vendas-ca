from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Sale, SaleItem, Company
from app.services.conta_azul_client import ContaAzulClient
from app.services.contaazul_people import get_or_create_customer_uuid_cached
from app.services.ca_sale_builder import build_ca_sale_payload

router = APIRouter(tags=["sales"])


@router.get("/sales")
def list_sales(company_id: int | None = None, batch_id: int | None = None, status: str | None = None):
    """
    Lista vendas com filtros opcionais.
    
    Query params:
        company_id: filtra por empresa
        batch_id: filtra por lote
        status: filtra por status (PRONTA, ENVIADA_CA, etc)
    """
    db: Session = SessionLocal()
    try:
        q = db.query(Sale)
        if company_id is not None:
            q = q.filter(Sale.company_id == company_id)
        if batch_id is not None:
            q = q.filter(Sale.batch_id == batch_id)
        if status is not None:
            q = q.filter(Sale.status == status)
        return q.order_by(Sale.id.asc()).all()
    finally:
        db.close()


@router.get("/sales/{sale_id}")
def get_sale(sale_id: int):
    """Retorna detalhes de uma venda específica com seus itens."""
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
    Envia uma venda individual para o Conta Azul.
    
    Fluxo:
    1. Valida company tem configuração necessária
    2. Busca/cria cliente no CA (com cache)
    3. Obtém próximo número de venda
    4. Monta payload
    5. Envia para CA
    6. Atualiza status da venda
    
    Status:
        PRONTA -> ENVIADA_CA (sucesso)
        PRONTA -> ERRO_ENVIO_CA (erro)
    """
    db: Session = SessionLocal()
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale não encontrada")

        company = db.query(Company).filter(Company.id == sale.company_id).first()
        if not company:
            raise HTTPException(status_code=400, detail="Company não encontrada")

        # Validações de configuração
        if not company.ca_financial_account_id:
            raise HTTPException(
                status_code=400,
                detail="Company sem ca_financial_account_id (UUID da conta financeira). "
                "Configure em GET /v1/companies/{id}/ca/financial-accounts e "
                "POST /v1/companies/{id}/ca/financial-account",
            )

        items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
        if not items:
            raise HTTPException(status_code=400, detail="Sale sem itens")

        # Client com Token Manager automático
        client = ContaAzulClient(company_id=company.id)

        # Busca/cria cliente no CA (com cache em CompanyCustomer)
        customer_uuid = get_or_create_customer_uuid_cached(
            db=db,
            client=client,
            company_id=company.id,
            customer_name=sale.customer_name,
        )

        # Próximo número de venda
        numero = client.get_next_sale_number()

        # Monta payload
        payload = build_ca_sale_payload(
            id_cliente=customer_uuid,
            numero=numero,
            sale=sale,
            items=items,
            id_conta_financeira=company.ca_financial_account_id,
        )

        # Fallback: se item sem id, usa default_item_id da company
        if company.default_item_id:
            for it in payload.get("itens", []):
                if not it.get("id"):
                    it["id"] = company.default_item_id

        # Validação final antes de enviar
        for it in payload.get("itens", []):
            if not it.get("id"):
                raise HTTPException(
                    status_code=400,
                    detail="Item sem 'id' e Company sem default_item_id. "
                    "Configure em POST /v1/companies/{id}/default-item",
                )

        # Envia para Conta Azul
        resp = client.create_sale(payload)

        # Atualiza status
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
        # Marca erro na venda
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


@router.post("/batches/{batch_id}/send_to_ca")
def send_batch_to_ca(batch_id: int):
    """
    Envia TODAS as vendas de um batch para o Conta Azul.
    
    ✅ Idempotente: não reenvia vendas já com status ENVIADA_CA
    ✅ Resiliente: continua enviando mesmo se 1 venda falhar
    ✅ Resumo detalhado: retorna sucessos, erros e skips
    
    Fluxo:
    1. Busca vendas PRONTAS do batch
    2. Para cada venda:
       - Tenta enviar
       - Marca sucesso (ENVIADA_CA) ou erro (ERRO_ENVIO_CA)
       - Continua para próxima venda
    3. Retorna resumo completo
    
    Returns:
        {
            "batch_id": int,
            "total_sales": int,
            "sent": int,
            "errors": int,
            "skipped": int,
            "results": [...]
        }
    """
    db: Session = SessionLocal()
    
    try:
        # Busca vendas PRONTAS do batch (ignora já enviadas)
        sales = (
            db.query(Sale)
            .filter(Sale.batch_id == batch_id)
            .filter(Sale.status.in_(["PRONTA", "PRONTA_PARA_ENVIO"]))
            .all()
        )
        
        if not sales:
            return {
                "batch_id": batch_id,
                "total_sales": 0,
                "sent": 0,
                "errors": 0,
                "skipped": 0,
                "message": "Nenhuma venda PRONTA encontrada neste batch",
                "results": []
            }
        
        # Validação: todas as vendas devem ser da mesma company
        company_ids = list(set([s.company_id for s in sales]))
        if len(company_ids) > 1:
            raise HTTPException(
                status_code=400,
                detail=f"Batch contém vendas de múltiplas companies: {company_ids}"
            )
        
        company_id = company_ids[0]
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company não encontrada")
        
        # Validação de configuração
        if not company.ca_financial_account_id:
            raise HTTPException(
                status_code=400,
                detail=f"Company {company_id} sem ca_financial_account_id configurado. "
                "Configure antes de enviar em lote."
            )
        
        # Client com Token Manager
        client = ContaAzulClient(company_id=company_id)
        
        # Contadores
        sent = 0
        errors = 0
        results = []
        
        # Processa cada venda
        for sale in sales:
            result = {
                "sale_id": sale.id,
                "customer_name": sale.customer_name,
                "total_amount": float(sale.total_amount),
                "status": None,
                "error": None,
                "ca_sale_id": None,
            }
            
            try:
                # Carrega itens
                items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
                if not items:
                    raise RuntimeError("Venda sem itens")
                
                # Busca/cria cliente
                customer_uuid = get_or_create_customer_uuid_cached(
                    db=db,
                    client=client,
                    company_id=company_id,
                    customer_name=sale.customer_name,
                )
                
                # Próximo número
                numero = client.get_next_sale_number()
                
                # Monta payload
                payload = build_ca_sale_payload(
                    id_cliente=customer_uuid,
                    numero=numero,
                    sale=sale,
                    items=items,
                    id_conta_financeira=company.ca_financial_account_id,
                )
                
                # Fallback de item
                if company.default_item_id:
                    for it in payload.get("itens", []):
                        if not it.get("id"):
                            it["id"] = company.default_item_id
                
                # Validação
                for it in payload.get("itens", []):
                    if not it.get("id"):
                        raise RuntimeError("Item sem 'id' e Company sem default_item_id")
                
                # Envia
                resp = client.create_sale(payload)
                
                # Sucesso
                sale.ca_sale_id = resp.get("id") or sale.ca_sale_id
                sale.status = "ENVIADA_CA"
                sale.error_summary = None
                db.add(sale)
                db.commit()
                
                result["status"] = "success"
                result["ca_sale_id"] = sale.ca_sale_id
                sent += 1
                
            except Exception as e:
                # Erro: marca na venda e continua
                error_msg = str(e)[:1000]
                sale.status = "ERRO_ENVIO_CA"
                sale.error_summary = error_msg
                db.add(sale)
                db.commit()
                
                result["status"] = "error"
                result["error"] = error_msg
                errors += 1
            
            results.append(result)
        
        return {
            "batch_id": batch_id,
            "company_id": company_id,
            "total_sales": len(sales),
            "sent": sent,
            "errors": errors,
            "skipped": 0,
            "results": results,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no envio em lote: {str(e)}")
    finally:
        db.close()


@router.post("/sales/{sale_id}/approve")
def approve_sale(sale_id: int):
    """
    Aprova uma venda individual.
    
    Status:
        AGUARDANDO_APROVACAO -> PRONTA
    """
    db: Session = SessionLocal()
    try:
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        if not sale:
            raise HTTPException(status_code=404, detail="Sale não encontrada")
        
        if sale.status != "AGUARDANDO_APROVACAO":
            raise HTTPException(
                status_code=400,
                detail=f"Sale não está aguardando aprovação (status atual: {sale.status})"
            )
        
        sale.status = "PRONTA"
        db.add(sale)
        db.commit()
        db.refresh(sale)
        
        return {"ok": True, "sale_id": sale.id, "new_status": sale.status}
    finally:
        db.close()


@router.post("/batches/{batch_id}/approve")
def approve_batch(batch_id: int):
    """
    Aprova TODAS as vendas de um batch.
    
    Status:
        AGUARDANDO_APROVACAO -> PRONTA (para todas)
    
    Returns:
        Número de vendas aprovadas
    """
    db: Session = SessionLocal()
    try:
        sales = (
            db.query(Sale)
            .filter(Sale.batch_id == batch_id)
            .filter(Sale.status == "AGUARDANDO_APROVACAO")
            .all()
        )
        
        for sale in sales:
            sale.status = "PRONTA"
            db.add(sale)
        
        db.commit()
        
        return {
            "ok": True,
            "batch_id": batch_id,
            "approved": len(sales),
        }
    finally:
        db.close()
