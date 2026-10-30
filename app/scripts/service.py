"""Script-Verwaltung in der Anwendungsdatenbank: Versionen, Veroeffentlichung, Runs.

Jedes Speichern erzeugt eine unveraenderliche Version; ausgefuehrt wird die
veroeffentlichte Version. Nur wer ``can_edit_scripts`` hat, darf speichern.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AppUser, QueryScript, QueryScriptVersion, Role, Run
from app.models.base import utc_now
from app.models.enums import RunKind, RunMode, RunSource, RunStatus
from app.scripts.contract import ParamSpec
from app.scripts.errors import ScriptContractError, ScriptError
from app.scripts.restricted import compile_source
from app.scripts.runner import ScriptOutcome, ScriptRunner
from app.scripts.templates import TEMPLATES


class ScriptPermissionError(ScriptError):
    """Der Benutzer darf Scripts nicht bearbeiten."""


class ScriptNotFoundError(ScriptError):
    """Das Script oder die Version existiert nicht."""


def can_edit_scripts(user: AppUser | None) -> bool:
    """Superuser und Benutzer mit Script-Recht duerfen speichern."""
    return (
        user is not None
        and user.is_active
        and (user.role is Role.SUPERUSER or user.can_edit_scripts)
    )


def _sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def list_scripts(session: Session, *, only_templates: bool = False) -> Sequence[QueryScript]:
    statement = select(QueryScript).options(selectinload(QueryScript.versions))
    if only_templates:
        statement = statement.where(QueryScript.is_template.is_(True))
    return list(session.scalars(statement.order_by(QueryScript.name)))


def get_script(session: Session, script_id: int) -> QueryScript:
    script = session.get(QueryScript, script_id)
    if script is None:
        raise ScriptNotFoundError("Das Script wurde nicht gefunden.")
    return script


def published_version(session: Session, script: QueryScript) -> QueryScriptVersion | None:
    if script.current_version_id is None:
        return None
    return session.get(QueryScriptVersion, script.current_version_id)


def latest_version(session: Session, script: QueryScript) -> QueryScriptVersion | None:
    return session.scalars(
        select(QueryScriptVersion)
        .where(QueryScriptVersion.script_id == script.id)
        .order_by(QueryScriptVersion.version_no.desc())
        .limit(1)
    ).first()


def create_script(
    session: Session,
    *,
    name: str,
    source: str,
    actor: AppUser,
    description: str | None = None,
    is_shared: bool = True,
    is_template: bool = False,
    publish: bool = True,
    comment: str | None = None,
) -> QueryScript:
    """Legt ein Script mit erster Version an (optional sofort veroeffentlicht)."""
    if not can_edit_scripts(actor):
        raise ScriptPermissionError("Kein Recht zum Bearbeiten von Scripts.")
    cleaned = name.strip()
    if not cleaned:
        raise ScriptContractError("Der Scriptname darf nicht leer sein.")
    if session.scalar(select(QueryScript.id).where(QueryScript.name == cleaned)) is not None:
        raise ScriptContractError(f"Das Script {cleaned!r} existiert bereits.")
    compile_source(source)
    script = QueryScript(
        name=cleaned,
        description=description,
        owner_id=actor.id,
        is_shared=is_shared,
        is_template=is_template,
    )
    session.add(script)
    session.flush()
    version = _add_version(session, script, source, actor=actor, comment=comment)
    if publish:
        script.current_version_id = version.id
    session.flush()
    return script


def save_version(
    session: Session,
    script: QueryScript,
    source: str,
    *,
    actor: AppUser,
    comment: str | None = None,
    publish: bool = False,
) -> QueryScriptVersion:
    """Speichert eine neue, unveraenderliche Version."""
    if not can_edit_scripts(actor):
        raise ScriptPermissionError("Kein Recht zum Bearbeiten von Scripts.")
    if script.is_template:
        raise ScriptPermissionError("Vorlagen sind unveraenderlich.")
    compile_source(source)
    version = _add_version(session, script, source, actor=actor, comment=comment)
    if publish:
        script.current_version_id = version.id
    session.flush()
    return version


def publish_version(
    session: Session, script: QueryScript, version: QueryScriptVersion, *, actor: AppUser
) -> None:
    """Setzt die veroeffentlichte Version."""
    if not can_edit_scripts(actor):
        raise ScriptPermissionError("Kein Recht zum Veroeffentlichen von Scripts.")
    if version.script_id != script.id:
        raise ScriptNotFoundError("Die Version gehoert nicht zu diesem Script.")
    script.current_version_id = version.id
    session.flush()


def _add_version(
    session: Session,
    script: QueryScript,
    source: str,
    *,
    actor: AppUser,
    comment: str | None,
) -> QueryScriptVersion:
    highest = session.scalar(
        select(func.max(QueryScriptVersion.version_no)).where(
            QueryScriptVersion.script_id == script.id
        )
    )
    version = QueryScriptVersion(
        script_id=script.id,
        version_no=int(highest or 0) + 1,
        source=source,
        sha256=_sha256(source),
        comment=comment,
        created_by_id=actor.id,
    )
    session.add(version)
    session.flush()
    return version


def ensure_templates(session: Session, *, owner: AppUser | None = None) -> int:
    """Legt fehlende Vorlagen an; liefert die Anzahl neuer Vorlagen."""
    created = 0
    for template in TEMPLATES:
        existing = session.scalar(select(QueryScript).where(QueryScript.name == template.name))
        if existing is not None:
            continue
        script = QueryScript(
            name=template.name,
            description=template.description,
            owner_id=owner.id if owner is not None else None,
            is_shared=True,
            is_template=True,
        )
        session.add(script)
        session.flush()
        version = QueryScriptVersion(
            script_id=script.id,
            version_no=1,
            source=template.source,
            sha256=_sha256(template.source),
            comment="Mitgelieferte Vorlage",
            created_by_id=owner.id if owner is not None else None,
        )
        session.add(version)
        session.flush()
        script.current_version_id = version.id
        created += 1
    session.flush()
    return created


def interface_for(
    source: str, runner: ScriptRunner | None = None
) -> tuple[dict[str, ParamSpec], list[str] | None]:
    """``PARAMS``/``COLUMNS`` eines Quelltexts fuer das Formular."""
    interface = (runner or ScriptRunner()).inspect(source)
    return interface.params, interface.columns


def record_run(
    session: Session,
    *,
    user: AppUser | None,
    profile_id: int | None,
    script_version_id: int | None,
    source: RunSource,
    params: dict[str, Any] | None,
    outcome: ScriptOutcome,
    mode: RunMode = RunMode.DRY_RUN,
) -> Run:
    """Protokolliert einen Dry Run mit Version, Parametern und Ergebnis."""
    stats: dict[str, Any] = {
        "duration_ms": outcome.duration_ms,
        "ids": len(outcome.ids),
        "has_filter": outcome.filter is not None,
    }
    if outcome.result and outcome.result.note:
        stats["note"] = outcome.result.note
    if outcome.error:
        stats["error"] = outcome.error[:2_000]
    run = Run(
        kind=RunKind.QUERY,
        mode=mode,
        source=source,
        status=RunStatus.OK if outcome.ok else RunStatus.FAILED,
        user_id=user.id if user is not None else None,
        profile_id=profile_id,
        script_version_id=script_version_id,
        params_json=json.dumps(params, ensure_ascii=False) if params else None,
        stats_json=json.dumps(stats, ensure_ascii=False),
        started_at=utc_now() - timedelta(milliseconds=outcome.duration_ms),
        finished_at=utc_now(),
    )
    session.add(run)
    session.flush()
    return run


def recent_runs(session: Session, *, limit: int = 10) -> Sequence[Run]:
    """Die letzten Laeufe fuer die Anzeige."""
    return list(session.scalars(select(Run).order_by(Run.started_at.desc()).limit(limit)))


def run_summary(outcome: ScriptOutcome, *, max_rows: int) -> str:
    """Kurzfassung fuer die UI."""
    if not outcome.ok:
        return f"Fehler: {outcome.error}"
    parts = [f"{outcome.duration_ms} ms"]
    if outcome.result and outcome.result.ids:
        parts.append(f"{len(outcome.ids)} IDs")
    if outcome.result and outcome.result.filter:
        parts.append("Filter: " + json.dumps(outcome.result.filter, ensure_ascii=False))
    if outcome.result and outcome.result.columns:
        parts.append(f"{len(outcome.result.columns)} Spalten")
    parts.append(f"Limit {max_rows} Zeilen")
    return " | ".join(parts)


__all__ = [
    "ScriptNotFoundError",
    "ScriptPermissionError",
    "can_edit_scripts",
    "create_script",
    "ensure_templates",
    "get_script",
    "interface_for",
    "latest_version",
    "list_scripts",
    "publish_version",
    "published_version",
    "recent_runs",
    "record_run",
    "run_summary",
    "save_version",
]
