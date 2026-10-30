"""Kindprozess einer Script-Ausfuehrung.

Der Client mit dem API-Key entsteht ausschliesslich hier; das Script sieht ihn nie,
sondern nur die Fassade. Ergebnisse gehen als einfache Werte zurueck an den Elternprozess.
"""

from __future__ import annotations

from typing import Any

from pixxio_client import Client

from app.scripts.errors import ScriptError
from app.scripts.facade import Facade
from app.scripts.restricted import LogCollector, execute

RESULT_KEY = "outcome"


def child_main(payload: dict[str, Any], queue: Any) -> None:
    """Einstiegspunkt im Kindprozess; schreibt genau ein Ergebnis in die Queue."""
    outcome: dict[str, Any] = {"ok": False, "error": None, "result": None, "log": ""}
    log = LogCollector(limit=int(payload.get("max_log_lines", 500)))
    try:
        client = Client.create_client(
            str(payload["api_key"]),
            str(payload["host"]),
            max_retries=int(payload.get("max_retries", 0)),
        )

        def provide() -> Client:
            return client

        facade = Facade(
            provide,
            max_rows=int(payload.get("max_rows", 0)) or 1,
            log=log.add,
            max_calls=int(payload.get("max_calls", 1_000)),
        )
        run = execute(
            str(payload["source"]),
            dict(payload.get("params") or {}),
            facade,
            log=log,
        )
        outcome.update(
            ok=True,
            result={
                "filter": run.result.filter,
                "ids": run.result.ids,
                "columns": run.result.columns,
                "note": run.result.note,
            },
        )
    except ScriptError as exc:
        outcome["error"] = str(exc)
    except BaseException as exc:  # noqa: BLE001 - Kindprozess darf nie haengen bleiben
        outcome["error"] = f"{type(exc).__name__}: {exc}"
    outcome["log"] = log.text()
    queue.put({RESULT_KEY: outcome})


__all__ = ["RESULT_KEY", "child_main"]
