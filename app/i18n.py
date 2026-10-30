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
    # Loeschen von Scripts und Profilen
    "Löschen": "Delete",
    "Profil '{name}' endgültig löschen? API-Key und Zuordnungen entfallen.": "Delete profile '{name}' permanently? API key and assignments will be removed.",
    "Profil '{name}' gelöscht.": "Profile '{name}' deleted.",
    "Profil löschen": "Delete profile",
    "Script '{name}' endgültig löschen? Versionen und Verweise entfallen.": "Delete script '{name}' permanently? Versions and references will be removed.",
    "Script '{name}' gelöscht.": "Script '{name}' deleted.",
    "Script löschen": "Delete script",
    "unbenutzt": "unused",
    "{workspaces} Bestände, {runs} Läufe": "{workspaces} workspaces, {runs} runs",
    # Script umbenennen
    "Script heißt jetzt '{name}'.": "Script is now called '{name}'.",
    "Speichern (Name und neue Version)": "Save (name and new version)",
    "Umbenennen erfordert das Recht zum Bearbeiten von Scripts.": "Renaming requires permission to edit scripts.",
    # Spaltenauswahl: Filter und Zähler
    "Felder filtern": "Filter fields",
    "Höchstens {limit} Spalten; {skipped} Felder wurden nicht ausgewählt.": "At most {limit} columns; {skipped} fields were not selected.",
    "{count} von {limit} Spalten ausgewählt": "{count} of {limit} columns selected",
    # Spaltenauswahl
    "Alle": "All",
    "Die Auswahl gilt nur für diesen Arbeitsbestand und wird gespeichert. Höchstens {limit} Spalten.": "The selection applies to this workspace only and is saved. At most {limit} columns.",
    "Eigene Metadatenfelder": "Custom metadata fields",
    "Keine": "None",
    "Spalten auswählen": "Select columns",
    "Standard-Metadatenfelder": "Standard metadata fields",
    "Standardattribute": "Standard attributes",
    "Zurücksetzen": "Reset",
    "{count} Spalten übernommen.": "{count} columns applied.",
    "Übernehmen": "Apply",
    # Excel-Fehlerdatei
    "Fehlerdatei erstellt: {count} markierte Zellen.": "Error file created: {count} marked cells.",
    "Fehlerdatei herunterladen": "Download error file",
    "Fehlerdatei: markierte Zellen prüfen, dann erneut importieren.": "Error file: check the marked cells, then import again.",
    "Keine Befunde zum Markieren vorhanden.": "No findings to mark.",
    "Meldung": "Message",
    "Zeile": "Row",
    # Excel-Schnittstelle
    "Abbrechen": "Cancel",
    "Anzeigename": "Display name",
    "Arbeitsmappe (.xlsx)": "Workbook (.xlsx)",
    "Arbeitsmappen mit Makros werden nicht unterstützt.": "Macro-enabled workbooks are not supported.",
    "Auswahl aus Blatt „{sheet}“": 'Selection from sheet "{sheet}"',
    "Auswahlwerte": "Allowed values",
    "Bitte Profil und Datei auswählen.": "Please select a profile and a file.",
    "Das Blatt „{sheet}“ ist leer.": 'Sheet "{sheet}" is empty.',
    "Das Format hat Version {version}; unterstützt wird Version {supported}.": "The format has version {version}; supported is version {supported}.",
    "Das Profil ist nur lesbar; ein Import ist nicht möglich.": "The profile is read-only; importing is not possible.",
    "Der Arbeitsbestand enthält keine Zeilen zum Export.": "The workspace has no rows to export.",
    "Der Spaltenschlüssel {key} kommt doppelt vor.": "Column key {key} appears twice.",
    "Die Arbeitsmappe enthält keine wirksamen Änderungen.": "The workbook contains no effective changes.",
    "Die Arbeitsmappe konnte nicht gelesen werden: {error}": "The workbook could not be read: {error}",
    "Die Arbeitsmappe stammt aus dem Excel-Export des Bulk-Editors. Übernommen werden nur Zellen, die sich gegenüber dem Export geändert haben.": "The workbook comes from the Bulk Editor Excel export. Only cells changed since the export are applied.",
    "Die Datei enthält keine Datenzeilen.": "The file contains no data rows.",
    "Die Datei enthält keine schreibbaren Spalten.": "The file contains no writable columns.",
    "Die Datei enthält mehr Zeilen als das Profillimit von {rows}.": "The file contains more rows than the profile limit of {rows}.",
    "Die Datei ist größer als {size} MB.": "The file is larger than {size} MB.",
    "Die Datei ist keine Arbeitsmappe des Bulk-Editors (Blatt „{sheet}“ fehlt).": 'The file is not a Bulk Editor workbook (sheet "{sheet}" is missing).',
    "Die Datei ist keine Excel-Arbeitsmappe (.xlsx).": "The file is not an Excel workbook (.xlsx).",
    "Die Datei ist keine gültige Excel-Arbeitsmappe (.xlsx).": "The file is not a valid Excel workbook (.xlsx).",
    "Die Datei ist leer.": "The file is empty.",
    "Die Datei ist nicht mehr vorhanden oder nicht sichtbar.": "The file no longer exists or is not visible.",
    "Die Datei wurde für den Host „{host}“ erstellt, nicht für „{profile}“.": 'The file was created for host "{host}", not for "{profile}".',
    "Die Datei-ID {id} kommt mehrfach vor.": "File ID {id} appears more than once.",
    "Die Datei-ID „{value}“ ist keine Zahl.": 'File ID "{value}" is not a number.',
    "Die entpackte Arbeitsmappe ist zu groß.": "The unpacked workbook is too large.",
    "Excel importieren": "Import Excel",
    "Excel-Export (markierte oder gefilterte Zeilen)": "Excel export (selected or filtered rows)",
    "Excel-Import": "Excel import",
    "Export erstellt: ungeschriebene Änderungen sind nicht enthalten.": "Export created: unsaved changes are not included.",
    "Export erstellt: {rows} Zeilen.": "Export created: {rows} rows.",
    "Exportiert am {moment}": "Exported on {moment}",
    "Feldtyp": "Field type",
    "Format {format} {version}": "Format {format} {version}",
    "Formeln werden nicht unterstützt.": "Formulas are not supported.",
    "Hinweis": "Note",
    "Importieren": "Import",
    "In pixx.io steht inzwischen „{current}“; die Zelle wird übersprungen.": 'pixx.io now holds "{current}"; the cell is skipped.',
    "Keine Exportbasis gefunden: externe Änderungen können nicht erkannt werden, leere Zellen bleiben unberücksichtigt.": "No export basis found: external changes cannot be detected, empty cells are ignored.",
    "Mehrfachwerte mit „{separator}“ trennen": 'Separate multiple values with "{separator}"',
    "Nur .xlsx-Dateien werden unterstützt.": "Only .xlsx files are supported.",
    "Nur Editor- und Superuser-Rollen dürfen importieren.": "Only editor and superuser roles may import.",
    "Nur lesbare Spalten werden ignoriert: {columns}": "Read-only columns are ignored: {columns}",
    "Ohne Exportbasis geprüft (Zwei-Wege-Vergleich).": "Checked without export basis (two-way comparison).",
    "Ohne Exportbasis importieren (nur Zwei-Wege-Vergleich)": "Import without export basis (two-way comparison only)",
    "Profil: {profile}": "Profile: {profile}",
    "Schlüssel": "Key",
    "Schreibbar": "Writable",
    "Spalte A muss den Schlüssel „file_id“ enthalten.": 'Column A must contain the key "file_id".',
    "Unbekannter Spaltenschlüssel: {key}": "Unknown column key: {key}",
    "Unbekanntes Format: {value}": "Unknown format: {value}",
    "Ungeschriebene Änderungen des Arbeitsbestands sind nicht enthalten.": "Unsaved workspace changes are not included.",
    "Zeile {row} · {column} · {message}": "Row {row} · {column} · {message}",
    "Zum Arbeitsbestand": "Open workspace",
    "ja": "yes",
    "nein": "no",
    "{changed} Änderungen aus {rows} Zeilen übernommen.": "{changed} changes applied from {rows} rows.",
    "{count} Befunde:": "{count} findings:",
    "{count} Datenzeilen": "{count} data rows",
    "{count} Zellen wurden wegen zwischenzeitlicher Änderungen übersprungen.": "{count} cells were skipped because of changes made in the meantime.",
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
    "Läufe": "Runs",
    "Lauf {run}": "Run {run}",
    "Lauf öffnen": "Open run",
    "Zurück zu den Läufen": "Back to runs",
    "Undo vorbereiten": "Prepare undo",
    "Nur nachweislich wirksame Änderungen lassen sich zurücknehmen.": (
        "Only provably effective changes can be undone."
    ),
    "Es gibt noch keine Läufe.": "There are no runs yet.",
    "Der Lauf wurde nicht gefunden.": "The run was not found.",
    "Das Profil des Laufs fehlt.": "The profile of the run is missing.",
    "Der Lauf hat kein Profil.": "The run has no profile.",
    "Der Lauf enthält keine Feldänderungen.": "The run contains no field changes.",
    "Unbekannte Spalten im Lauf: {keys}": "Unknown columns in the run: {keys}",
    "Dateien fehlen: {files}": "Missing files: {files}",
    "Kein Feld lässt sich zurücknehmen ({diverged} abweichend, {status} nicht wirksam).": (
        "No field can be undone ({diverged} diverged, {status} not effective)."
    ),
    "Dieser Lauf hat keine Feldänderungen.": "This run has no field changes.",
    "Nur wirksame Felder werden zurückgenommen; der Rest bleibt unberührt.": (
        "Only effective fields are undone; the rest stays untouched."
    ),
    "{count} Feldwerte entfernt.": "{count} field values removed.",
    "Alte Feldwerte entfernen": "Remove old field values",
    "{count} Felder für das Undo vorbereitet ({diverged} abweichend, {status} nicht wirksam).": (
        "{count} fields prepared for undo ({diverged} diverged, {status} not effective)."
    ),
    "ok {ok} | geplant {planned} | unklar {unknown} | fehlgeschlagen {failed} | "
    "übersprungen {skipped}": (
        "ok {ok} | planned {planned} | unclear {unknown} | failed {failed} | skipped {skipped}"
    ),
    "Undo zu Lauf {run}": "Undo of run {run}",
    "Status abgleichen": "Reconcile status",
    "Es gibt keinen Plan zum Prüfen.": "There is no plan to check.",
    "Status abgeglichen: {status} ({count} Änderungen übernommen).": (
        "Status reconciled: {status} ({count} changes committed)."
    ),
    "Kommentar zum Statuswechsel": "Comment for the state change",
    "Ein Statuswechsel verlangt einen Kommentar ({field}).": (
        "A state change requires a comment ({field})."
    ),
    "Unbekannter Dateistatus: {value}": "Unknown file state: {value}",
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
