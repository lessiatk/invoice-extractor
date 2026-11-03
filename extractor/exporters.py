from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .models import ExtractionResult

INVOICE_COLS = ["source_file", "status", "vendor", "invoice_number", "invoice_date", "due_date",
                "currency", "subtotal", "tax", "total", "line_items", "issues"]


def _row(r: ExtractionResult) -> dict:
    inv = r.invoice
    return {
        "source_file": r.source_file,
        "status": r.status,
        "vendor": inv.vendor if inv else "",
        "invoice_number": inv.invoice_number if inv else "",
        "invoice_date": inv.invoice_date.isoformat() if inv and inv.invoice_date else "",
        "due_date": inv.due_date.isoformat() if inv and inv.due_date else "",
        "currency": inv.currency if inv else "",
        "subtotal": str(inv.subtotal) if inv and inv.subtotal is not None else "",
        "tax": str(inv.tax) if inv and inv.tax is not None else "",
        "total": str(inv.total) if inv else "",
        "line_items": len(inv.line_items) if inv else 0,
        "issues": "; ".join(f"{i.field}: {i.message}" for i in r.issues) or (r.error or ""),
    }


def to_csv(results: list[ExtractionResult], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    invoices_path, items_path = out_dir / "invoices.csv", out_dir / "line_items.csv"
    with invoices_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INVOICE_COLS)
        w.writeheader()
        w.writerows(_row(r) for r in results)
    with items_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_file", "invoice_number", "description", "quantity", "unit_price", "amount"])
        for r in results:
            for it in r.invoice.line_items if r.invoice else []:
                w.writerow([r.source_file, r.invoice.invoice_number, it.description, it.quantity, it.unit_price, it.amount])
    return [invoices_path, items_path]


def to_json(results: list[ExtractionResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "invoices.json"
    data = [r.model_dump(mode="json") | {"status": r.status} for r in results]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def to_sqlite(results: list[ExtractionResult], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "invoices.db"
    con = sqlite3.connect(path)
    with con:
        con.execute(f"CREATE TABLE IF NOT EXISTS invoices ({', '.join(c + ' TEXT' for c in INVOICE_COLS)}, "
                    "PRIMARY KEY (source_file))")
        con.executemany(
            f"INSERT OR REPLACE INTO invoices VALUES ({', '.join('?' * len(INVOICE_COLS))})",
            [tuple(str(_row(r)[c]) for c in INVOICE_COLS) for r in results],
        )
    con.close()
    return path
