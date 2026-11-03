from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str
    quantity: Decimal = Field(default=Decimal("1"), ge=0)
    unit_price: Decimal = Field(..., ge=0)
    amount: Decimal = Field(..., ge=0)


class Invoice(BaseModel):
    vendor: str
    invoice_number: str
    invoice_date: date | None = None
    due_date: date | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    subtotal: Decimal | None = None
    tax: Decimal | None = Field(default=None, ge=0)
    total: Decimal = Field(..., ge=0)
    line_items: list[LineItem] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    field: str
    message: str


class ExtractionResult(BaseModel):
    source_file: str
    invoice: Invoice | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    error: str | None = None
    provider: str = "mock"

    @property
    def status(self) -> str:
        if self.error:
            return "failed"
        return "needs_review" if self.issues else "ok"
