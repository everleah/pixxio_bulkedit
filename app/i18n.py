"""Zweisprachige Oberflächentexte (Deutsch als Quelle, Englisch als Übersetzung).

Deutsch steht direkt im Code, damit die Oberfläche ohne Übersetzung vollständig ist.
`sichtbaren Texte` laufen über :func:`t`; fehlt eine englische Übersetzung, erscheint
der deutsche Text. Die Sprache liegt in der Session und wird über die Kopfzeile gesetzt.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

DEFAULT_LOCALE = "de"
LOCALES: dict[str, str] = {"de": "Deutsch", "en": "English"}
LOCALE_LABELS: dict[str, str] = {"de": "DE", "en": "EN"}

_current_locale: ContextVar[str] = ContextVar("bulkedit_locale", default=DEFAULT_LOCALE)

# Schlüssel der Sprache in der NiceGUI-Session.
LOCALE_STORAGE_KEY = "locale"

# Englische Übersetzungen; Schlüssel ist der deutsche Quelltext.
EN_TRANSLATIONS: dict[str, str] = {
    # Allgemein und Navigation
    "Start": "Home",
    "Arbeitsbestände": "Workspaces",
    "Scripts": "Scripts",
    "Profile": "Profiles",
    "Benutzer": "Users",
    "Abmelden": "Sign out",
    "Anmelden": "Sign in",
    "Sprache wechseln": "Change language",
    "Angemeldet als {user} ({role})": "Signed in as {user} ({role})",
    "Sitzung läuft nach {minutes} Minuten ab.": "Session expires after {minutes} minutes.",
    "Review und Schreiben folgen in den nächsten Meilensteinen.": (
        "Review and writing follow in the next milestones."
    ),
    "Änderungen prüfen und schreiben: Arbeitsbestand öffnen, Review und Dry Run.": (
        "Check and write changes: open a workspace, then review and dry run."
    ),
    "Dry Run {run}: geprüft ({steps} Anfrage(n), {conflicts} Konflikt(e)).": (
        "Dry run {run}: checked ({steps} request(s), {conflicts} conflict(s))."
    ),
    "Zu viele Fehlversuche. Bitte später erneut versuchen.": (
        "Too many failed attempts. Please try again later."
    ),
    "Anmeldung fehlgeschlagen.": "Sign-in failed.",
    "Benutzername": "Username",
    "Passwort": "Password",
    "unbekannt": "unknown",
    "abgebrochen": "cancelled",
    "keine": "none",
    "aktiv": "active",
    "inaktiv": "inactive",
    "Fehler: {message}": "Error: {message}",
    "Status: {status}": "Status: {status}",
    # Profile
    "Profil anlegen oder bearbeiten": "Create or edit profile",
    "Name": "Name",
    "Host": "Host",
    "API-Key": "API key",
    "Leer lassen, um den gespeicherten Key zu behalten.": ("Leave empty to keep the stored key."),
    "max. Wiederholungen": "max. retries",
    "max. Zeilen": "max. rows",
    "Schreiben erlaubt": "Writing allowed",
    "Speichern": "Save",
    "Neues Profil": "New profile",
    "Neues Profil anlegen": "Create new profile",
    "Vorhandene Profile": "Existing profiles",
    "Noch keine Profile angelegt.": "No profiles yet.",
    "Bearbeiten": "Edit",
    "Verbindung testen": "Test connection",
    "max. {rows}": "max. {rows}",
    "Schreiben": "write",
    "nur lesen": "read only",
    "noch nicht geprüft": "not checked yet",
    "OK: {user} ({stamp})": "OK: {user} ({stamp})",
    "Fehler ({stamp})": "Error ({stamp})",
    "Profil geladen – der Key bleibt unverändert, solange das Feld leer ist.": (
        "Profile loaded – the key stays unchanged while the field is empty."
    ),
    "Profil '{name}' gespeichert.": "Profile '{name}' saved.",
    "Das Profil wurde nicht gefunden.": "The profile was not found.",
    "Profil nicht gefunden.": "Profile not found.",
    "Verbindung OK als {user}.": "Connection OK as {user}.",
    "Verbindung fehlgeschlagen: {message}": "Connection failed: {message}",
    "Kein Zugriff: Diese Seite verwaltet nur ein Superuser.": (
        "No access: only a superuser manages this page."
    ),
    # Benutzer
    "Benutzer anlegen oder bearbeiten": "Create or edit user",
    "Beim Bearbeiten leer lassen, um das Passwort zu behalten.": (
        "Leave empty while editing to keep the password."
    ),
    "Rolle": "Role",
    "darf Scripts bearbeiten": "may edit scripts",
    "Vorhandene Benutzer": "Existing users",
    "Benutzer geladen": "User loaded",
    "Neuer Benutzer": "New user",
    "Neuen Benutzer anlegen": "Create new user",
    "Benutzer nicht gefunden.": "User not found.",
    "Benutzer '{name}' gespeichert.": "User '{name}' saved.",
    "Benutzer '{name}' aktiviert.": "User '{name}' activated.",
    "Benutzer '{name}' deaktiviert.": "User '{name}' deactivated.",
    "Aktivieren": "Activate",
    "Deaktivieren": "Deactivate",
    "Script-Recht": "script right",
    # Scripts
    "Neues Script": "New script",
    "Verfügbare Scripts": "Available scripts",
    "Noch keine Scripts vorhanden.": "No scripts yet.",
    "Öffnen": "Open",
    "Vorlage": "Template",
    "Vorlage kopieren": "Copy template",
    "nicht veröffentlicht": "not published",
    "v{version}": "v{version}",
    "{count} Versionen": "{count} versions",
    "Kopie '{name}' angelegt.": "Copy '{name}' created.",
    "Die Vorlage hat keine Version.": "The template has no version.",
    "Vorlagen sind unveränderlich – bitte eine Kopie anlegen.": (
        "Templates are immutable – please create a copy."
    ),
    "Veröffentlichte Fassung (nur lesbar)": "Published version (read only)",
    "Angezeigt: v{version}": "Showing: v{version}",
    "Profil": "Profile",
    "Keinem Profil zugeordnet – ein Superuser muss ein Profil zuweisen.": (
        "No profile assigned – a superuser must assign one."
    ),
    "Parameter": "Parameters",
    "Dieses Script hat keine Parameter.": "This script has no parameters.",
    "Prüfen": "Validate",
    "Dry Run": "Dry run",
    "Dry Run: ": "Dry run: ",
    "Speichern (neue Version)": "Save (new version)",
    "Speichern und veröffentlichen": "Save and publish",
    "Aktuelle Version veröffentlichen": "Publish current version",
    "Version laden": "Load version",
    "(veröffentlicht)": "(published)",
    "(keine Ausgabe)": "(no output)",
    "Lauf gestartet …": "Run started …",
    "Script läuft …": "Script is running …",
    "Der Lauf wurde abgebrochen.": "The run was cancelled.",
    "Kein Profil zugewiesen.": "No profile assigned.",
    "Bitte ein Profil auswählen.": "Please select a profile.",
    "Script ist gültig: {params} Parameter, Spalten: {columns}.": (
        "Script is valid: {params} parameters, columns: {columns}."
    ),
    "IDs: {preview}{suffix}": "IDs: {preview}{suffix}",
    "Filter:": "Filter:",
    "{ms} ms": "{ms} ms",
    "{count} IDs": "{count} IDs",
    "{count} Spalten": "{count} columns",
    "Limit {rows} Zeilen": "limit {rows} rows",
    "Script '{name}' angelegt.": "Script '{name}' created.",
    "Version v{version} gespeichert.": "Version v{version} saved.",
    "Version v{version} ist jetzt veröffentlicht.": "Version v{version} is now published.",
    "Das Script wurde nicht gefunden.": "The script was not found.",
    "Das Script ist nicht veröffentlicht.": "The script is not published.",
    "Es gibt noch keine Version.": "There is no version yet.",
    # Arbeitsbestände
    "Offene Arbeitsbestände": "Open workspaces",
    "Keine offenen Arbeitsbestände.": "No open workspaces.",
    "Arbeitsbestand laden": "Load workspace",
    "Arbeitsbestand {id}": "Workspace {id}",
    "Name (optional)": "Name (optional)",
    "Script": "Script",
    "Liste aktualisieren": "Refresh list",
    "Arbeitsbestand löschen": "Delete workspace",
    "Arbeitsbestand löschen.": "Delete workspace.",
    "Arbeitsbestand gelöscht.": "Workspace deleted.",
    "Arbeitsbestand schließen": "Close workspace",
    "{count} Zeilen": "{count} rows",
    "{rows} Zeilen | {changes} Änderungen | Revision {revision}": (
        "{rows} rows | {changes} changes | revision {revision}"
    ),
    "Der Arbeitsbestand wurde nicht gefunden.": "The workspace was not found.",
    "Das Profil fehlt.": "The profile is missing.",
    "Benutzer oder Profil fehlt.": "User or profile is missing.",
    "Bitte Script und Profil auswählen.": "Please select a script and a profile.",
    "{count} Assets geladen.": "{count} assets loaded.",
    "Assets werden geladen …": "Loading assets …",
    "Der Entwurf läuft in {days} Tagen ab (Warnung ab {threshold} Tagen).": (
        "The draft expires in {days} days (warning from {threshold} days)."
    ),
    "Der Entwurf wurde in einem anderen Tab geändert. Bitte die Seite neu laden.": (
        "The draft was changed in another tab. Please reload the page."
    ),
    "Spalte": "Column",
    "Filter (enthält)": "Filter (contains)",
    "nur geänderte Zeilen": "only changed rows",
    "Zielspalte": "Target column",
    "Wert": "Value",
    "Ziel": "Target",
    "markierte Zeilen": "selected rows",
    "gefilterte": "filtered",
    "alle": "all",
    "Filter zurücksetzen": "Reset filter",
    "Aufsteigend sortieren": "Sort ascending",
    "Absteigend sortieren": "Sort descending",
    "Spalten an Inhalt anpassen": "Size columns to content",
    "Spalten an Anzeige anpassen": "Size columns to display",
    "Wert auf Ziel setzen": "Set value on target",
    "Änderungen verwerfen": "Discard changes",
    "Format JJJJ-MM-TT HH:MM:SS": "Format YYYY-MM-DD HH:MM:SS",
    "Mehrere Werte mit Komma trennen": "Separate multiple values with commas",
    "Bitte eine Zielspalte wählen.": "Please select a target column.",
    "Keine Zeile markiert.": "No row selected.",
    "{changed} von {total} Zeilen geändert.": "{changed} of {total} rows changed.",
    "{count} Änderungen verworfen.": "{count} changes discarded.",
    "Spalten sind nur {width} px breit; Inhalte werden abgeschnitten.": (
        "Columns are only {width} px wide; content will be cut off."
    ),
    "{field} gespeichert.": "{field} saved.",
    "{count} Änderungen": "{count} changes",
    "expiry": "expiry",
    "laeuft": "runs",
    # Review und Schreibpipeline
    "Review und schreiben": "Review and write",
    "Review aktualisieren": "Refresh review",
    "Review aktualisiert.": "Review refreshed.",
    "Dry Run prüfen": "Check dry run",
    "Jetzt schreiben": "Write now",
    "Zum Grid": "Back to grid",
    "Nur geänderte Felder werden geschrieben; jedes Ergebnis wird zurückgelesen.": (
        "Only changed fields are written; every result is read back."
    ),
    "Externe Änderungen überschreiben": "Overwrite external changes",
    "Feldänderungen: {changes} | Dateien: {files} | Anfragen: {steps}": (
        "Field changes: {changes} | files: {files} | requests: {steps}"
    ),
    "Hinweis: {message}": "Note: {message}",
    "Der Plan enthält Fehler und ist nicht ausführbar.": (
        "The plan contains errors and cannot be executed."
    ),
    "Der Plan enthält Fehler und kann nicht gespeichert werden.": (
        "The plan contains errors and cannot be saved."
    ),
    "Der Entwurf hat sich geändert. Bitte Review und Dry Run erneuern.": (
        "The draft has changed. Please refresh review and dry run."
    ),
    "Dieser Auftrag wurde bereits ausgeführt.": "This job has already been executed.",
    "Externe Änderungen erkannt. Bitte das Überschreiben ausdrücklich bestätigen.": (
        "External changes detected. Please confirm overwriting explicitly."
    ),
    "Externe Änderungen erkannt: {files}": "External changes detected: {files}",
    "Ein weiterer Schreibauftrag läuft auf diesem Host bereits (Läufe: {runs}).": (
        "Another write job is already running on this host (runs: {runs})."
    ),
    "Datei {file_id} ist nicht mehr vorhanden.": "File {file_id} no longer exists.",
    "Der Arbeitsbestand zum Plan fehlt.": "The workspace for this plan is missing.",
    "Die API hat den Schreibvorgang abgelehnt.": "The API rejected the write request.",
    "Der Hintergrundauftrag ist fehlgeschlagen.": "The background job failed.",
    "Ausgang unklar: {message}": "Outcome unclear: {message}",
    "Ausgang nach Neustart unklar. Bitte Werte prüfen.": (
        "Outcome unclear after restart. Please check the values."
    ),
    "Über Rücklesung bestätigt: {message}": "Confirmed by reading back: {message}",
    "Rücklesung weicht bei {count} Feld(ern) ab.": ("Read-back differs for {count} field(s)."),
    "Schreiblauf {run}: {status} ({ok} erfolgreich, {unknown} unklar, {failed} fehlgeschlagen, "
    "{skipped} übersprungen).": (
        "Write run {run}: {status} ({ok} succeeded, {unknown} unclear, {failed} failed, "
        "{skipped} skipped)."
    ),
    "Aus dem Entwurf entfernte Änderungen: {count}": ("Changes removed from the draft: {count}"),
    "Es gibt keine Änderungen.": "There are no changes.",
    "Unbekannte Spalte: {key}": "Unknown column: {key}",
    "Die Spalte {key} gehört nicht zum Arbeitsbestand.": (
        "Column {key} is not part of the workspace."
    ),
    "Die Spalte {label!r} ist nicht schreibbar.": "Column {label!r} is not writable.",
    "Die Änderungen ergeben keinen Schreibvorgang.": "The changes produce no write request.",
    "Das Attribut {attribute!r} ist nicht schreibbar.": "Attribute {attribute!r} is not writable.",
    "Der Wert für {label!r} konnte nicht umgewandelt werden.": (
        "The value for {label!r} could not be converted."
    ),
    "Unbekannte Auswahl für {label}: {values}": "Unknown option for {label}: {values}",
    "{label}: widersprüchliche Werte im selben Schreibvorgang.": (
        "{label}: conflicting values in the same write request."
    ),
    "{label}: {message}": "{label}: {message}",
}


def normalize_locale(value: object) -> str:
    """Unbekannte oder fehlende Werte fallen auf die Standardsprache zurück."""
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in LOCALES:
            return lowered
    return DEFAULT_LOCALE


def get_locale() -> str:
    """Aktuelle Sprache: Session bevorzugt, sonst Kontext (Seitenaufbau)."""
    try:
        from nicegui import app  # lokal, damit app.i18n ohne UI nutzbar bleibt

        stored = app.storage.user.get(LOCALE_STORAGE_KEY)
    except Exception:  # noqa: BLE001 - kein Session-Kontext (CLI, Tests)
        stored = None
    if isinstance(stored, str) and stored in LOCALES:
        return stored
    return _current_locale.get()


def set_locale(locale: object) -> str:
    resolved = normalize_locale(locale)
    _current_locale.set(resolved)
    return resolved


def t(message: str, /, **params: Any) -> str:
    """Übersetzt einen deutschen Quelltext und füllt Platzhalter."""
    text = message
    if get_locale() == "en":
        text = EN_TRANSLATIONS.get(message, message)
    if params:
        try:
            return text.format(**params)
        except KeyError, IndexError:  # pragma: no cover - defekte Übersetzung
            return text
    return text


def describe_error(exc: BaseException) -> str:
    """Fehlertext für die Oberfläche; bekannte Fehler werden übersetzt."""
    key = getattr(exc, "translation_key", None)
    if isinstance(key, str) and key in EN_TRANSLATIONS and get_locale() == "en":
        return EN_TRANSLATIONS[key]
    return str(exc)


def missing_translations(messages: set[str]) -> list[str]:
    """Quelltexte ohne englische Übersetzung (für Tests)."""
    return sorted(message for message in messages if message not in EN_TRANSLATIONS)


__all__ = [
    "DEFAULT_LOCALE",
    "EN_TRANSLATIONS",
    "LOCALES",
    "LOCALE_LABELS",
    "LOCALE_STORAGE_KEY",
    "describe_error",
    "get_locale",
    "missing_translations",
    "normalize_locale",
    "set_locale",
    "t",
]
