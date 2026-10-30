"""Kommandozeile des Datenbank-Lastnachweises."""

from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from app.bench.runner import AUDIT_ROWS, Metric, run_benchmark

DEFAULT_ASSETS = 50_000
DEFAULT_FIELDS = 30


def _format_metric(metric: Metric) -> str:
    target = "" if metric.target is None else f" (Ziel <= {metric.target:g} {metric.unit})"
    status = ""
    if metric.ok is True:
        status = "  OK"
    elif metric.ok is False:
        status = "  ZIEL VERFEHLT"
    if metric.unit == "s":
        value = f"{metric.value:.3f}"
    else:
        value = f"{metric.value:,.1f}"
    return f"- {metric.name}: {value} {metric.unit}{target}{status}"


def _cleanup(db_path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db_path}{suffix}").unlink(missing_ok=True)


def command_run(args: argparse.Namespace) -> int:
    db_path = (
        Path(args.db_path)
        if args.db_path
        else Path(tempfile.gettempdir()) / "bulkedit_bench.sqlite3"
    )
    report = run_benchmark(
        db_path=db_path,
        assets=args.assets,
        fields=args.fields,
        audit_rows=args.audit_rows,
    )
    if args.json:
        payload = {
            "assets": report.assets,
            "fields": report.fields,
            "db_path": report.db_path,
            "metrics": [asdict(metric) | {"ok": metric.ok} for metric in report.metrics],
            "notes": report.notes,
            "failures": [metric.name for metric in report.failures],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Lastnachweis: {report.assets} Assets x {report.fields} Felder")
        for metric in report.metrics:
            print(_format_metric(metric))
        print("Hinweise:")
        for note in report.notes:
            print(f"- {note}")
        if report.failures:
            print("Ziel verfehlt: " + ", ".join(metric.name for metric in report.failures))
    if not args.keep and not args.db_path:
        _cleanup(db_path)
    return 0 if not report.failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.bench",
        description="Datenbank-Lastnachweis (Phase 1.6.3) mit synthetischen Daten",
    )
    parser.add_argument("--assets", type=int, default=DEFAULT_ASSETS)
    parser.add_argument("--fields", type=int, default=DEFAULT_FIELDS)
    parser.add_argument("--audit-rows", type=int, default=AUDIT_ROWS)
    parser.add_argument("--db-path", default=None, help="Datenbank behalten und hier ablegen")
    parser.add_argument("--keep", action="store_true", help="temporaere Datenbank behalten")
    parser.add_argument("--json", action="store_true", help="Bericht als JSON ausgeben")
    parser.set_defaults(handler=command_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
