"""Generate the demo invoices in samples/ (already included; re-run to regenerate)."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)


def pdf(name: str, header: list[str], items: list[tuple], footer: list[str], sym: str) -> None:
    c = canvas.Canvas(str(OUT / name), pagesize=A4)
    y = 800
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, header[0])
    c.setFont("Helvetica", 10)
    for line in header[1:]:
        y -= 16
        c.drawString(50, y, line)
    y -= 36
    c.setFont("Helvetica-Bold", 10)
    for x, t in ((50, "Description"), (330, "Qty"), (400, "Unit price"), (490, "Amount")):
        c.drawString(x, y, t)
    c.setFont("Helvetica", 10)
    for desc, qty, unit, amount in items:
        y -= 18
        c.drawString(50, y, desc)
        c.drawString(330, y, str(qty))
        c.drawString(400, y, f"{sym}{unit}")
        c.drawString(490, y, f"{sym}{amount}")
    y -= 30
    for line in footer:
        c.drawString(330, y, line)
        y -= 16
    c.save()


pdf("acme_cloud_2026-10.pdf",
    ["Acme Cloud Services Inc.", "Invoice Number: INV-2026-1042", "Invoice Date: 2026-10-01", "Due Date: 2026-10-31", "Currency: USD"],
    [("Cloud hosting - Pro plan", 1, "249.00", "249.00"), ("Extra storage 100 GB", 3, "15.00", "45.00"), ("Priority support", 1, "99.00", "99.00")],
    ["Subtotal: $393.00", "Tax (10%): $39.30", "Total: $432.30"], "$")

pdf("berlin_design_studio.pdf",
    ["Berlin Design Studio GmbH", "Invoice No: BDS-0877", "Invoice Date: 15.09.2026", "Due Date: 15.10.2026", "Currency: EUR"],
    [("Landing page design", 1, "1,200.00", "1,200.00"), ("Illustrations", 4, "150.00", "600.00")],
    ["Subtotal: €1,800.00", "VAT 19%: €342.00", "Total: €2,142.00"], "€")

# contains a calculation error on purpose -> shows up as "needs review"
pdf("office_supplies_error.pdf",
    ["OfficeHub Ltd", "Invoice #: OH-55120", "Date: 2026-10-20", "Due Date: 2026-11-20", "Currency: GBP"],
    [("A4 paper, box", 10, "4.50", "45.00"), ("Ergonomic chair", 2, "180.00", "380.00")],
    ["Subtotal: £425.00", "VAT 20%: £85.00", "Total: £510.00"], "£")

# same vendor + number as the first one -> duplicate detection
(OUT / "acme_cloud_resent.txt").write_text(
    """Acme Cloud Services Inc.
Invoice Number: INV-2026-1042
Invoice Date: 2026-10-01
Due Date: 2026-10-31

Description                Qty    Unit price    Amount
Cloud hosting - Pro plan   1      $249.00       $249.00
Extra storage 100 GB       3      $15.00        $45.00
Priority support           1      $99.00        $99.00

Subtotal: $393.00
Tax (10%): $39.30
Total: $432.30
""", encoding="utf-8")

(OUT / "coffee_receipt.txt").write_text(
    """Kava Lab Kyiv
Receipt No: 004417
Date: 2026-10-28

Flat white                 2      85.00         170.00
Croissant                  1      70.00         70.00

Total: 240.00 UAH
""", encoding="utf-8")
print("samples written to", OUT)
