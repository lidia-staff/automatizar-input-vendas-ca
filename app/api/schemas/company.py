from pydantic import BaseModel, Field
from typing import Optional

class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    ca_company_id: Optional[str] = None  # opcional

class CompanyUpdate(BaseModel):
    """Schema para atualização parcial de Company"""
    name: Optional[str] = None
    slug: Optional[str] = None
    review_mode: Optional[bool] = None
    default_item_id: Optional[str] = None
    ca_financial_account_id: Optional[str] = None

class CompanyOut(BaseModel):
    id: int
    name: str
    ca_company_id: Optional[str] = None

    class Config:
        from_attributes = True
