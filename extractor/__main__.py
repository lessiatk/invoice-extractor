"""python -m extractor samples/ --out output/ --format csv json sqlite"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from . import exporters
from .pipeline import process
from .providers import build_provider


def _load_dotenv() -> None:
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    _load_dotenv()
    p = argparse.ArgumentParser(description="Extract structured data from invoices and receipts")
    p.add_argument("input", type=Path, help="file or folder with PDFs / images / text")
    p.add_argument("--out", type=Path, default=Path("output"))
    p.add_argument("--format", nargs="+", default=["csv", "json"], choices=["csv", "json", "sqlite"])
    p.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "mock"), choices=["mock", "openai", "anthropic"])
    p.add_argument("--workers", type=int, default=4)
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    provider = build_provider(
        args.provider,
        openai_key=os.getenv("OPENAI_API_KEY", ""),
        anthropic_key=os.getenv("ANTHROPIC_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
    )
    results = process(args.input, provider, args.workers)

    icon = {"ok": "✅", "needs_review": "⚠️ ", "failed": "❌"}
    print(f"\nProvider: {provider.name} · {len(results)} files\n")
    for r in results:
        inv = r.invoice
        line = f"{icon[r.status]} {r.source_file:<28}"
        if inv:
            line += f" {inv.vendor[:24]:<24} {inv.invoice_number:<14} {inv.total:>10} {inv.currency}"
        print(line)
        for issue in r.issues:
            print(f"     └ {issue.field}: {issue.message}")
        if r.error:
            print(f"     └ {r.error}")

    written: list[Path] = []
    if "csv" in args.format:
        written += exporters.to_csv(results, args.out)
    if "json" in args.format:
        written.append(exporters.to_json(results, args.out))
    if "sqlite" in args.format:
        written.append(exporters.to_sqlite(results, args.out))

    ok = sum(r.status == "ok" for r in results)
    print(f"\n{ok}/{len(results)} ready for accounting, {len(results) - ok} need review")
    print("Saved:", ", ".join(str(p) for p in written))


if __name__ == "__main__":
    main()
