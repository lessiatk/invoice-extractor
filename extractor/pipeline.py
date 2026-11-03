from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .models import ExtractionResult, ValidationIssue
from .providers import Provider
from .readers import iter_inputs
from .validation import find_duplicates, validate

log = logging.getLogger(__name__)


def process_file(path: Path, provider: Provider) -> ExtractionResult:
    try:
        invoice = provider.extract(path)
        return ExtractionResult(source_file=path.name, invoice=invoice, issues=validate(invoice), provider=provider.name)
    except Exception as exc:
        log.error("%s: %s", path.name, exc)
        return ExtractionResult(source_file=path.name, error=str(exc), provider=provider.name)


def process(target: Path, provider: Provider, workers: int = 4) -> list[ExtractionResult]:
    files = iter_inputs(target)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: process_file(p, provider), files))

    dupes = find_duplicates([(r.source_file, r.invoice) for r in results if r.invoice])
    for r in results:
        if r.source_file in dupes:
            r.issues.append(ValidationIssue(field="invoice_number", message=f"duplicate of {dupes[r.source_file]}"))
    return results
