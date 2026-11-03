"""Extraction providers: regex-based mock (no keys) and LLM (OpenAI / Anthropic, incl. vision for images)."""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from .models import Invoice, LineItem
from .readers import is_image, read_text

log = logging.getLogger(__name__)

SCHEMA_HINT = json.dumps(Invoice.model_json_schema(), indent=1)
SYSTEM_PROMPT = f"""You extract structured data from invoices and receipts.
Return ONLY one JSON object matching this JSON schema (dates as YYYY-MM-DD, numbers without currency symbols,
currency as ISO 4217 code). Use null for fields that are not present. Do not invent values.

{SCHEMA_HINT}"""

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₴": "UAH", "zł": "PLN"}
DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")


def parse_money(text: str) -> Decimal | None:
    cleaned = re.sub(r"[^\d,.\-]", "", text)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:  # 1,234.56 or 1.234,56
        cleaned = cleaned.replace(",", "") if cleaned.rfind(".") > cleaned.rfind(",") else cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        head, _, tail = cleaned.rpartition(",")
        cleaned = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else cleaned.replace(",", "")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def parse_date(text: str) -> date | None:
    text = text.strip().rstrip(".")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


class Provider(Protocol):
    name: str

    def extract(self, path: Path) -> Invoice: ...


class MockProvider:
    """Label-based regex parser. Good enough for clean digital invoices and for running the demo offline."""

    name = "mock"

    _LABELS = {
        "invoice_number": r"(?:(?:invoice|receipt)\s*(?:no\.?|number|#)|rechnung\s*nr\.?|№)\s*[:#]?\s*([A-Z0-9][\w\-/]*)",
        "invoice_date": r"(?:invoice\s*date|date\s*of\s*issue|issued|datum|date)\s*[:]?\s*([A-Za-z0-9 ,./\-]{6,20})",
        "due_date": r"(?:due\s*date|payment\s*due|due)\s*[:]?\s*([A-Za-z0-9 ,./\-]{6,20})",
        "subtotal": r"(?:subtotal|sub-total|net\s*amount|netto)\s*[:]?\s*([^\n]+)",
        "tax": r"(?:tax|vat|mwst)[^\n:]*[:]?\s*([^\n]+)",
        "total": r"(?:total\s*due|amount\s*due|grand\s*total|total|gesamt)\s*[:]?\s*([^\n]+)",
    }
    _LINE = re.compile(
        r"^\s*(?P<desc>[A-Za-z][^\n]*?)\s{2,}(?P<qty>\d+(?:[.,]\d+)?)\s{2,}(?P<unit>[$€£]?\s?[\d.,]+)\s{2,}(?P<amount>[$€£]?\s?[\d.,]+)\s*$",
        re.MULTILINE,
    )

    def _find(self, key: str, text: str) -> str | None:
        # last match for totals (the "Total" line is at the bottom), first match otherwise
        matches = re.findall(self._LABELS[key], text, re.IGNORECASE)
        if not matches:
            return None
        return (matches[-1] if key == "total" else matches[0]).strip()

    def extract(self, path: Path) -> Invoice:
        if is_image(path):
            raise ValueError("Mock mode cannot read images. Set LLM_PROVIDER=openai or anthropic for photos/scans.")
        text = read_text(path)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            raise ValueError("Document is empty (scanned PDF without a text layer?)")

        currency = next((code for sym, code in CURRENCY_SYMBOLS.items() if sym in text), None)
        if m := re.search(r"\b(USD|EUR|GBP|UAH|PLN|CHF)\b", text):
            currency = m.group(1)

        items = [
            LineItem(
                description=m["desc"].strip(),
                quantity=Decimal(m["qty"].replace(",", ".")),
                unit_price=parse_money(m["unit"]) or Decimal(0),
                amount=parse_money(m["amount"]) or Decimal(0),
            )
            for m in self._LINE.finditer(text)
            if not re.match(r"(?i)(description|item|qty|sub-?total|total|tax|vat)", m["desc"])
        ]

        total_raw = self._find("total", text)
        total = parse_money(total_raw) if total_raw else None
        if total is None:
            raise ValueError("Could not find the invoice total")

        def money(key: str) -> Decimal | None:
            raw = self._find(key, text)
            return parse_money(raw) if raw else None

        def when(key: str) -> date | None:
            raw = self._find(key, text)
            return parse_date(raw) if raw else None

        tax_raw = self._find("tax", text)
        tax = parse_money(tax_raw.split()[-1]) if tax_raw else None

        return Invoice(
            vendor=lines[0],
            invoice_number=self._find("invoice_number", text) or "UNKNOWN",
            invoice_date=when("invoice_date"),
            due_date=when("due_date"),
            currency=currency or "USD",
            subtotal=money("subtotal"),
            tax=tax,
            total=total,
            line_items=items,
        )


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Model did not return JSON")
    return json.loads(match.group(0))


class _LLMProvider:
    name = "llm"
    max_attempts = 3

    def _call(self, text: str | None, image: tuple[str, str] | None, feedback: str | None) -> str:  # pragma: no cover
        raise NotImplementedError

    def extract(self, path: Path) -> Invoice:
        text = image = None
        if is_image(path):
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            image = (mime, base64.b64encode(path.read_bytes()).decode())
        else:
            text = read_text(path)
        feedback = None
        for attempt in range(1, self.max_attempts + 1):
            raw = self._call(text, image, feedback)
            try:
                return Invoice.model_validate(_extract_json(raw))
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                log.warning("%s: invalid output (attempt %s): %s", path.name, attempt, exc)
                feedback = f"Your previous answer failed validation: {exc}. Return corrected JSON only."
        raise ValueError(f"Model output invalid after {self.max_attempts} attempts")


class OpenAIProvider(_LLMProvider):  # pragma: no cover - network
    name = "openai"

    def __init__(self, api_key: str, model: str):
        from openai import OpenAI

        self.client, self.model = OpenAI(api_key=api_key), model

    def _call(self, text, image, feedback):
        content: list[dict] = []
        if text:
            content.append({"type": "text", "text": f"Invoice text:\n\n{text}"})
        if image:
            content.append({"type": "image_url", "image_url": {"url": f"data:{image[0]};base64,{image[1]}"}})
        if feedback:
            content.append({"type": "text", "text": feedback})
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
        )
        return resp.choices[0].message.content or ""


class AnthropicProvider(_LLMProvider):  # pragma: no cover - network
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic

        self.client, self.model = Anthropic(api_key=api_key), model

    def _call(self, text, image, feedback):
        content: list[dict] = []
        if image:
            content.append({"type": "image", "source": {"type": "base64", "media_type": image[0], "data": image[1]}})
        if text:
            content.append({"type": "text", "text": f"Invoice text:\n\n{text}"})
        if feedback:
            content.append({"type": "text", "text": feedback})
        resp = self.client.messages.create(
            model=self.model, max_tokens=2000, temperature=0, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


def build_provider(name: str, openai_key: str = "", anthropic_key: str = "",
                   openai_model: str = "gpt-4o-mini", anthropic_model: str = "claude-sonnet-4-5") -> Provider:
    name = name.lower()
    if name == "openai" and openai_key:
        return OpenAIProvider(openai_key, openai_model)
    if name == "anthropic" and anthropic_key:
        return AnthropicProvider(anthropic_key, anthropic_model)
    if name != "mock":
        log.warning("No API key for %s — using mock provider", name)
    return MockProvider()
