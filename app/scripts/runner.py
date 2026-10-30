"""Ausfuehrung eines Scripts in einem Kindprozess mit Zeit- und Ausgabelimit."""

from __future__ import annotations

import multiprocessing
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.scripts.contract import (
    ParamSpec,
    ScriptResult,
    coerce_params,
    normalize_result,
    parse_columns,
    parse_params,
)
from app.scripts.errors import ScriptContractError, ScriptExecutionError, ScriptTimeoutError
from app.scripts.restricted import compile_source, read_literals
from app.scripts.worker import RESULT_KEY, child_main


@dataclass(frozen=True)
class ScriptInterface:
    """Was die UI ohne Ausfuehrung aus einem Script lesen kann."""

    params: dict[str, ParamSpec]
    columns: list[str] | None


@dataclass(frozen=True)
class ScriptOutcome:
    """Ergebnis eines Laufs, immer fuer die UI darstellbar."""

    ok: bool
    result: ScriptResult | None = None
    log: str = ""
    error: str | None = None
    duration_ms: int = 0
    timed_out: bool = False

    @property
    def ids(self) -> list[int]:
        return list(self.result.ids) if self.result and self.result.ids else []

    @property
    def filter(self) -> dict[str, Any] | None:
        return self.result.filter if self.result else None

    @property
    def columns(self) -> list[str] | None:
        return self.result.columns if self.result else None


class ScriptRunner:
    """Uebersetzt, prueft und startet Scripts; der API-Key lebt nur im Kindprozess."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        max_output_chars: int = 20_000,
        max_log_lines: int = 500,
        max_calls: int = 1_000,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.max_output_chars = int(max_output_chars)
        self.max_log_lines = int(max_log_lines)
        self.max_calls = int(max_calls)

    # -- Pruefen ohne Ausfuehrung --------------------------------------
    def inspect(self, source: str) -> ScriptInterface:
        """Prueft Syntax und Vertrag und liest ``PARAMS``/``COLUMNS``."""
        compile_source(source)
        raw_params, raw_columns = read_literals(source)
        return ScriptInterface(params=parse_params(raw_params), columns=parse_columns(raw_columns))

    # -- Ausfuehren -----------------------------------------------------
    def run(
        self,
        source: str,
        params: Mapping[str, Any] | None,
        *,
        host: str,
        api_key: str,
        max_rows: int,
        max_retries: int = 0,
        timeout_seconds: float | None = None,
    ) -> ScriptOutcome:
        """Fuehrt das Script aus und liefert ein pruefbares Ergebnis."""
        interface = self.inspect(source)
        typed = self.bind_params(interface, params)
        payload = {
            "source": source,
            "params": typed,
            "host": host,
            "api_key": api_key,
            "max_rows": int(max_rows),
            "max_retries": int(max_retries),
            "max_calls": self.max_calls,
            "max_log_lines": self.max_log_lines,
        }
        timeout = float(timeout_seconds if timeout_seconds is not None else self.timeout_seconds)
        started = time.perf_counter()
        raw = self._run_in_child(payload, timeout)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if raw.get("timed_out"):
            return ScriptOutcome(
                ok=False,
                error=f"Zeitlimit von {timeout:.0f} Sekunden ueberschritten.",
                duration_ms=duration_ms,
                timed_out=True,
            )
        log = str(raw.get("log") or "")[: self.max_output_chars]
        if not raw.get("ok"):
            return ScriptOutcome(
                ok=False,
                error=str(raw.get("error") or "Unbekannter Fehler."),
                log=log,
                duration_ms=duration_ms,
            )
        try:
            payload_result = raw.get("result") or {}
            result = normalize_result(
                ScriptResult(
                    filter=payload_result.get("filter"),
                    ids=payload_result.get("ids"),
                    columns=payload_result.get("columns"),
                    note=payload_result.get("note"),
                ),
                max_rows=int(max_rows),
            )
        except ScriptContractError as exc:
            return ScriptOutcome(ok=False, error=str(exc), log=log, duration_ms=duration_ms)
        return ScriptOutcome(ok=True, result=result, log=log, duration_ms=duration_ms)

    def bind_params(
        self, interface: ScriptInterface, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        return coerce_params(interface.params, dict(params or {}))

    # -- Kindprozess ----------------------------------------------------
    def _run_in_child(self, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        context = multiprocessing.get_context("spawn")
        queue: Any = context.Queue()
        process = context.Process(target=child_main, args=(payload, queue), daemon=True)
        process.start()
        try:
            process.join(timeout)
            if process.is_alive():
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
                return {"timed_out": True}
            try:
                message = queue.get_nowait()
            except Exception:  # noqa: BLE001 - kein Ergebnis (Absturz im Kind)
                return {
                    "ok": False,
                    "error": (
                        "Der Kindprozess hat kein Ergebnis geliefert "
                        f"(Exitcode {process.exitcode})."
                    ),
                }
            if not isinstance(message, dict) or RESULT_KEY not in message:
                return {"ok": False, "error": "Unerwartete Antwort des Kindprozesses."}
            outcome = message[RESULT_KEY]
            if not isinstance(outcome, dict):
                return {"ok": False, "error": "Unerwartete Antwort des Kindprozesses."}
            return outcome
        finally:
            queue.close()
            if process.is_alive():  # pragma: no cover - Sicherheitsnetz
                process.kill()


__all__ = [
    "ScriptExecutionError",
    "ScriptInterface",
    "ScriptOutcome",
    "ScriptRunner",
    "ScriptTimeoutError",
]
