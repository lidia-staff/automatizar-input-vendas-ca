from pydantic import BaseModel, Field
from typing import Optional

class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    ca_company_id: Optional[str] = None  # opcional

class CompanyOut(BaseModel):
    id: int
    name: str
    ca_company_id: Optional[str] = None

    class Config:
        from_attributes = True
