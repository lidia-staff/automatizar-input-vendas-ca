import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company, UploadBatch, CompanyPaymentAccount
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

        # Validar configuração obrigatória
        if not company.default_item_id:
            raise HTTPException(
                status_code=400,
                detail="config_incompleta: produto padrão não configurado. Acesse Configurações > Produto Padrão."
            )

        payment_accounts = db.query(CompanyPaymentAccount).filter(
            CompanyPaymentAccount.company_id == company_id
        ).all()
        if not payment_accounts:
            raise HTTPException(
                status_code=400,
                detail="config_incompleta: nenhuma forma de pagamento mapeada. Acesse Configurações > Formas de Pagamento."
            )

        suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = tmp.name

        try:
            records = read_base_sheet(temp_path, sheet_name="Base")
        except Exception as e:
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
