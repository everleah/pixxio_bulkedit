"""Fachliche Aufzaehlungen der Anwendung."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    SUPERUSER = "superuser"
    EDITOR = "editor"
    VIEWER = "viewer"


class WorkspaceStatus(StrEnum):
    """Ladezustand eines Arbeitsbestands."""

    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"
    CLOSED = "closed"


class RunKind(StrEnum):
    QUERY = "query"
    WRITE = "write"


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    LIVE = "live"


class RunSource(StrEnum):
    GRID = "grid"
    XLSX = "xlsx"
    UNDO = "undo"


class RunStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class ChangeStatus(StrEnum):
    """Ergebnis einer geplanten Felduebernahme."""

    PLANNED = "planned"
    OK = "ok"
    FAILED = "failed"
    SKIPPED_CONFLICT = "skipped_conflict"
    UNKNOWN = "unknown"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    ABORTED = "aborted"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"
