import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company, UploadBatch
from app.services.import_xlsx import read_base_sheet
from app.services.sales_builder import create_sales_from_records

router = APIRouter(tags=["uploads"])


@router.post("/uploads")
def upload_sales(
    company_id: int = Form(...),
    file: UploadFile = File(...),
):
    db: Session = SessionLocal()
    temp_path = None

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="company_not_found")
        
        # ✅ VALIDAÇÃO: Bloqueia upload se configuração incompleta
        if not company.default_item_id:
            raise HTTPException(
                status_code=400,
                detail="config_incomplete: Configure o produto padrão em Configurações antes de enviar vendas"
            )
        
        # Verifica se tem pelo menos 1 conta mapeada
        payment_accounts = db.query(CompanyPaymentAccount).filter(
            CompanyPaymentAccount.company_id == company_id
        ).count()
        
        if payment_accounts == 0:
            raise HTTPException(
                status_code=400,
                detail="config_incomplete: Configure pelo menos uma conta de pagamento em Configurações antes de enviar vendas"
            )

        suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = tmp.name

        # ✅ aqui é onde geralmente quebra quando a planilha mudou
        try:
            records = read_base_sheet(temp_path, sheet_name="Base")
        except Exception as e:
            # devolve erro LEGÍVEL pro cliente (nada de 500 genérico)
            raise HTTPException(
                status_code=400,
                detail=f"invalid_spreadsheet: {str(e)}"
            )

        if not records:
            raise HTTPException(status_code=400, detail="empty_sheet")

        batch = UploadBatch(
            company_id=company_id,
            filename=file.filename or "upload.xlsx",
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        try:
            created, ready, awaiting, with_error, items_with_error = create_sales_from_records(
                db=db,
                company_id=company_id,
                batch_id=batch.id,
                records=records,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"build_sales_failed: {str(e)}")

        return {
            "batch_id": batch.id,
            "company_id": company_id,
            "sales_created": created,
            "ready": ready,
            "awaiting_approval": awaiting,
            "with_error": with_error,
            "items_with_error": items_with_error,
        }

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        try:
            file.file.close()
        except Exception:
            pass
        db.close()
