import os
import shutil
import tempfile

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Company, UploadBatch
from app.services.import_xlsx import read_base_sheet
from app.services.sales_builder import create_sales_from_records

router = APIRouter()


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

        suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            temp_path = tmp.name

        records = read_base_sheet(temp_path, sheet_name="Base")
        if not records:
            raise HTTPException(status_code=400, detail="empty_sheet")

        batch = UploadBatch(
            company_id=company_id,
            filename=file.filename or "upload.xlsx",
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        created, ready, awaiting, with_error, items_with_error = (
            create_sales_from_records(
                db=db,
                company_id=company_id,
                batch_id=batch.id,
                records=records,
            )
        )

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