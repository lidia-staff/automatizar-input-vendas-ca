from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.session import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    review_mode = Column(Boolean, default=True)

    # OAuth tokens (por empresa)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)

    # ✅ UUID da conta financeira no Conta Azul (por empresa)
    ca_financial_account_id = Column(String, nullable=True)

    batches = relationship("UploadBatch", back_populates="company", cascade="all, delete-orphan")
    sales = relationship("Sale", back_populates="company", cascade="all, delete-orphan")


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    status = Column(String(30), default="PROCESSADO")
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="batches")
    sales = relationship("Sale", back_populates="batch", cascade="all, delete-orphan")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("upload_batches.id"), nullable=False)

    group_key = Column(String(500), nullable=False)
    hash_unique = Column(String(100), nullable=False)

    sale_date = Column(Date, nullable=False)
    customer_name = Column(String(200), nullable=False)
    payment_method = Column(String(100), nullable=False)
    payment_terms = Column(String(100), nullable=False)
    receiving_account = Column(String(120), nullable=False)
    due_date = Column(Date, nullable=False)

    total_amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(40), nullable=False)
    error_summary = Column(Text, nullable=True)
    ca_sale_id = Column(String(80), nullable=True)

    company = relationship("Company", back_populates="sales")
    batch = relationship("UploadBatch", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale", cascade="all, delete-orphan")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)

    category = Column(String(150), nullable=True)
    product_service = Column(String(200), nullable=False)
    details = Column(String(250), nullable=True)

    qty = Column(Numeric(12, 2), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    sale = relationship("Sale", back_populates="items")