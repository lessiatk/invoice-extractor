from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from extractor import exporters
from extractor.models import Invoice, LineItem
from extractor.pipeline import process
from extractor.providers import MockProvider, parse_date, parse_money
from extractor.validation import validate

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,234.56", "1234.56"), ("1.234,56 €", "1234.56"), ("€342,00", "342.00"), ("240.00 UAH", "240.00"), ("1,200", "1200.00")],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["2026-10-01", "01.10.2026", "October 1, 2026", "1 Oct 2026"])
def test_parse_date(raw):
    assert parse_date(raw) == date(2026, 10, 1)


def test_mock_extracts_pdf():
    inv = MockProvider().extract(SAMPLES / "acme_cloud_2026-10.pdf")
    assert inv.vendor == "Acme Cloud Services Inc."
    assert inv.invoice_number == "INV-2026-1042"
    assert inv.invoice_date == date(2026, 10, 1)
    assert inv.currency == "USD"
    assert inv.total == Decimal("432.30")
    assert len(inv.line_items) == 3
    assert validate(inv, today=date(2026, 11, 1)) == []


def test_eu_number_format():
    inv = MockProvider().extract(SAMPLES / "berlin_design_studio.pdf")
    assert inv.currency == "EUR"
    assert inv.subtotal == Decimal("1800.00")
    assert inv.invoice_date == date(2026, 9, 15)


def test_validation_catches_math_error():
    inv = Invoice(
        vendor="X", invoice_number="1", invoice_date=date(2026, 1, 1), total=Decimal("380"),
        line_items=[LineItem(description="chair", quantity=Decimal(2), unit_price=Decimal(180), amount=Decimal(380))],
    )
    fields = {i.field for i in validate(inv, today=date(2026, 2, 1))}
    assert "line_items[1]" in fields


def test_validation_future_date_and_due_before_issue():
    inv = Invoice(vendor="X", invoice_number="1", invoice_date=date(2030, 1, 1), due_date=date(2029, 1, 1), total=Decimal(10))
    fields = {i.field for i in validate(inv, today=date(2026, 1, 1))}
    assert {"invoice_date", "due_date"} <= fields


def test_pipeline_end_to_end(tmp_path):
    results = {r.source_file: r for r in process(SAMPLES, MockProvider())}
    assert results["acme_cloud_2026-10.pdf"].status == "ok"
    assert results["office_supplies_error.pdf"].status == "needs_review"
    assert any("duplicate" in i.message for i in results["acme_cloud_resent.txt"].issues)

    paths = exporters.to_csv(list(results.values()), tmp_path)
    paths.append(exporters.to_json(list(results.values()), tmp_path))
    paths.append(exporters.to_sqlite(list(results.values()), tmp_path))
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)


def test_unreadable_file_is_reported_not_raised(tmp_path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    [result] = process(tmp_path, MockProvider())
    assert result.status == "failed" and result.error
