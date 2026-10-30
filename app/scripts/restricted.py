"""Ausfuehrung von Abfrage-Scripts unter RestrictedPython.

``compile_restricted`` allein blockiert keine Imports; deshalb prueft
:func:`check_source` den Syntaxbaum vorab und die Namensaufloesung bekommt nur
eine feste Whitelist an Builtins. Das Script sieht weder Client noch Session.
"""

from __future__ import annotations

import ast
import datetime
import json
import re
import warnings
from dataclasses import dataclass
from types import CodeType
from typing import Any, Protocol

from RestrictedPython.compile import compile_restricted
from RestrictedPython.Guards import (
    full_write_guard,
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safer_getattr,
)

from app.scripts.contract import (
    ParamSpec,
    ScriptResult,
    normalize_result,
    parse_columns,
    parse_params,
)
from app.scripts.errors import ScriptContractError, ScriptExecutionError, ScriptSecurityError

FILENAME = "<script>"
MAX_LOG_LINES = 500

FORBIDDEN_CALLS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "delattr",
        "dir",
        "eval",
        "exec",
        "exit",
        "getattr",
        "globals",
        "help",
        "input",
        "locals",
        "memoryview",
        "object",
        "open",
        "quit",
        "setattr",
        "super",
        "type",
        "vars",
    }
)

FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
)

ALLOWED_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "ord": ord,
    "pow": pow,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "ArithmeticError": ArithmeticError,
    "AssertionError": AssertionError,
    "AttributeError": AttributeError,
    "Exception": Exception,
    "IndexError": IndexError,
    "KeyError": KeyError,
    "LookupError": LookupError,
    "NameError": NameError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "TypeError": TypeError,
    "ValueError": ValueError,
    "ZeroDivisionError": ZeroDivisionError,
    "True": True,
    "False": False,
    "None": None,
}

PREPARED_MODULES: dict[str, Any] = {
    "re": re,
    "json": json,
    "datetime": datetime,
}


class FacadeLike(Protocol):
    """Was ein Script von ``px`` sieht; ``max_rows`` begrenzt Ergebnismengen."""

    max_rows: int


@dataclass
class LogCollector:
    """Sammelt ``print``- und ``px.log``-Ausgaben mit Zeilenlimit."""

    limit: int = MAX_LOG_LINES
    lines: list[str] | None = None
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.lines is None:
            self.lines = []

    def add(self, text: str) -> None:
        assert self.lines is not None
        if len(self.lines) >= self.limit:
            self.truncated = True
            return
        self.lines.append(str(text))

    def text(self) -> str:
        assert self.lines is not None
        lines = list(self.lines)
        if self.truncated:
            lines.append(f"... Ausgabe nach {self.limit} Zeilen abgeschnitten.")
        return "\n".join(lines)


@dataclass(frozen=True)
class ScriptRun:
    """Ergebnis einer Script-Ausfuehrung."""

    result: ScriptResult
    params: dict[str, ParamSpec]
    columns: list[str] | None
    log: str


def check_source(source: str) -> None:
    """Prueft den Syntaxbaum auf verbotene Imports, Aufrufe und Namen."""
    try:
        tree = ast.parse(source, filename=FILENAME)
    except SyntaxError as exc:
        raise ScriptSecurityError(f"Syntaxfehler in Zeile {exc.lineno}: {exc.msg}") from exc
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            name = type(node).__name__
            raise ScriptSecurityError(
                f"Zeile {getattr(node, 'lineno', '?')}: {name} ist in Scripts nicht erlaubt "
                "(keine Imports, keine async-Syntax, keine global-Deklarationen)."
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                raise ScriptSecurityError(
                    f"Zeile {node.lineno}: der Aufruf {node.func.id!r} ist nicht erlaubt."
                )
        if isinstance(node, ast.Name) and node.id.startswith("__") and node.id.endswith("__"):
            raise ScriptSecurityError(f"Zeile {node.lineno}: der Name {node.id!r} ist gesperrt.")
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise ScriptSecurityError(
                f"Zeile {node.lineno}: Attribute mit Unterstrich ({node.attr!r}) sind gesperrt."
            )


def compile_source(source: str) -> CodeType:
    """Prueft und uebersetzt ein Script; Fehler werden als ``ScriptSecurityError`` gemeldet."""
    if not isinstance(source, str) or not source.strip():
        raise ScriptSecurityError("Das Script ist leer.")
    check_source(source)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            return compile_restricted(source, FILENAME, "exec")
        except SyntaxError as exc:
            raise ScriptSecurityError(f"RestrictedPython lehnt das Script ab: {exc}") from exc


def _guarded_getitem(obj: Any, index: Any) -> Any:
    return obj[index]


def build_namespace(log: LogCollector, facade: FacadeLike) -> dict[str, Any]:
    """Namensraum fuer ``exec``: Whitelist-Builtins, Fassade und Ausgabesammler."""

    class _Printer:
        def _call_print(self, *objects: Any, **_kwargs: Any) -> None:
            log.add(" ".join(str(item) for item in objects))

    printer = _Printer()

    def print_factory(*_args: Any, **_kwargs: Any) -> _Printer:
        return printer

    builtins = dict(ALLOWED_BUILTINS)
    builtins["print"] = printer._call_print
    namespace: dict[str, Any] = {
        "__builtins__": builtins,
        "__name__": "pixxio_script",
        "_getattr_": safer_getattr,
        "_getitem_": _guarded_getitem,
        "_getiter_": iter,
        "_write_": full_write_guard,
        "_print_": print_factory,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_unpack_sequence_": guarded_unpack_sequence,
        "px": facade,
    }
    namespace.update(PREPARED_MODULES)
    return namespace


def load_module(source: str, *, log: LogCollector, facade: FacadeLike) -> dict[str, Any]:
    """Uebersetzt und fuehrt den Modulrumpf aus (PARAMS, COLUMNS, ``query``)."""
    code = compile_source(source)
    namespace = build_namespace(log, facade)
    try:
        exec(code, namespace)  # noqa: S102 - bewusst eingeschraenkt (RestrictedPython)
    except ScriptSecurityError:
        raise
    except Exception as exc:  # noqa: BLE001 - Laufzeitfehler des Scripts
        raise ScriptExecutionError(f"Fehler beim Laden des Scripts: {_describe(exc)}") from exc
    return namespace


def read_contract(namespace: dict[str, Any]) -> tuple[dict[str, ParamSpec], list[str] | None, Any]:
    """Liest und prueft ``PARAMS``, ``COLUMNS`` und ``query``."""
    params = parse_params(namespace.get("PARAMS"))
    columns = parse_columns(namespace.get("COLUMNS"))
    query = namespace.get("query")
    if not callable(query):
        raise ScriptContractError("Das Script muss eine Funktion 'query(px, params)' definieren.")
    return params, columns, query


def execute(
    source: str,
    params: dict[str, Any],
    facade: FacadeLike,
    *,
    log: LogCollector | None = None,
) -> ScriptRun:
    """Fuehrt ein Script aus und liefert die validierte Rueckgabe."""
    collector = log if log is not None else LogCollector()
    namespace = load_module(source, log=collector, facade=facade)
    specs, columns, query = read_contract(namespace)
    try:
        raw = query(facade, params)
    except ScriptContractError:
        raise
    except Exception as exc:  # noqa: BLE001 - Laufzeitfehler des Scripts
        raise ScriptExecutionError(f"Fehler in query(): {_describe(exc)}") from exc
    result = normalize_result(raw, max_rows=int(getattr(facade, "max_rows", 0) or 1))
    return ScriptRun(
        result=result,
        params=specs,
        columns=result.columns or columns,
        log=collector.text(),
    )


def _describe(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def read_literals(source: str) -> tuple[object, object]:
    """Liest ``PARAMS`` und ``COLUMNS`` als Literale, ohne das Script auszufuehren.

    So kann die UI das Parameterformular bauen, bevor irgendein Code laeuft.
    """
    check_source(source)
    try:
        tree = ast.parse(source, filename=FILENAME)
    except SyntaxError as exc:
        raise ScriptSecurityError(f"Syntaxfehler in Zeile {exc.lineno}: {exc.msg}") from exc
    found: dict[str, object] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in {"PARAMS", "COLUMNS"}:
            continue
        try:
            found[target.id] = ast.literal_eval(node.value)
        except ValueError as exc:
            raise ScriptContractError(
                f"{target.id} muss ein Literal sein (kein Funktionsaufruf, keine Variable)."
            ) from exc
    return found.get("PARAMS"), found.get("COLUMNS")


__all__ = [
    "ALLOWED_BUILTINS",
    "LogCollector",
    "PREPARED_MODULES",
    "ScriptRun",
    "build_namespace",
    "check_source",
    "compile_source",
    "execute",
    "load_module",
    "read_contract",
    "read_literals",
]
