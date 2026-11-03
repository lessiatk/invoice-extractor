"""Business-rule checks. Anything that fails goes to `needs_review` instead of silently into accounting."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from .models import Invoice, ValidationIssue

TOLERANCE = Decimal("0.02")


def validate(inv: Invoice, today: date | None = None) -> list[ValidationIssue]:
    today = today or date.today()
    issues: list[ValidationIssue] = []

    for i, item in enumerate(inv.line_items, 1):
        expected = (item.quantity * item.unit_price).quantize(Decimal("0.01"))
        if abs(expected - item.amount) > TOLERANCE:
            issues.append(ValidationIssue(field=f"line_items[{i}]",
                                          message=f"{item.quantity} × {item.unit_price} = {expected}, invoice says {item.amount}"))

    if inv.line_items:
        items_sum = sum((it.amount for it in inv.line_items), Decimal(0))
        base = inv.subtotal if inv.subtotal is not None else inv.total - (inv.tax or 0)
        if abs(items_sum - base) > TOLERANCE:
            issues.append(ValidationIssue(field="subtotal", message=f"line items sum to {items_sum}, subtotal is {base}"))

    if inv.subtotal is not None:
        expected_total = inv.subtotal + (inv.tax or 0)
        if abs(expected_total - inv.total) > TOLERANCE:
            issues.append(ValidationIssue(field="total", message=f"subtotal + tax = {expected_total}, total is {inv.total}"))

    if inv.invoice_number == "UNKNOWN":
        issues.append(ValidationIssue(field="invoice_number", message="not found"))
    if inv.invoice_date is None:
        issues.append(ValidationIssue(field="invoice_date", message="not found"))
    elif inv.invoice_date > today + timedelta(days=1):
        issues.append(ValidationIssue(field="invoice_date", message=f"{inv.invoice_date} is in the future"))
    if inv.due_date and inv.invoice_date and inv.due_date < inv.invoice_date:
        issues.append(ValidationIssue(field="due_date", message="due date is before invoice date"))

    return issues


def find_duplicates(invoices: list[tuple[str, Invoice]]) -> dict[str, str]:
    """Map source_file -> source_file of the first invoice with the same vendor + number."""
    seen: dict[tuple[str, str], str] = {}
    dupes: dict[str, str] = {}
    for source, inv in invoices:
        key = (inv.vendor.lower().strip(), inv.invoice_number.lower().strip())
        if key in seen:
            dupes[source] = seen[key]
        else:
            seen[key] = source
    return dupes
