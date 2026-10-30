# Oberflaeche

## Purpose

- NiceGUI-Seiten der Anwendung: gemeinsamer Rahmen, serverseitiger Zugriffsschutz und die
  Verwaltung von Profilen und Benutzern.

## Ownership

- `guard.py`: `current_user` (Signierte Session plus Aktivpruefung), `is_superuser`,
  `logout`, `redirect_to_login`.
- `shell.py`: `apply_palette` (Quasar-Farben aus `app/colors.py`) und `page_header`
  (Navigation mit Admin-Links nur fuer Superuser).
- `admin.py`: `register_admin_pages` registriert `/admin/profiles` und `/admin/users`.
  Beide Seiten pruefen die Rolle serverseitig, zeigen eine Liste und ein gemeinsames
  Formular fuer Anlegen und Bearbeiten.
- `scripts.py`: `register_script_pages` registriert `/scripts` (Liste, Vorlagen kopieren)
  und `/scripts/{script_id}` (Editor mit `ui.codemirror`, Parameterformular aus `PARAMS`,
  Pruefen, Dry Run, Speichern, Veroeffentlichen; `script_id = 0` legt neu an).

## Local Contracts

- Jede Seite ruft `current_user` selbst auf; ohne Session wird auf `/` umgeleitet, ohne
  Superuser-Rolle erscheint "Kein Zugriff" und die Seite baut keine Daten auf.
- Der API-Key ist write-only: Das Passwortfeld startet immer leer, ein leerer Wert laesst
  den gespeicherten Key stehen, und der Key erscheint nie in Labels, Logs oder im Browser.
- Nach jeder Aenderung an einem Profil wird `ClientFactory.invalidate` aufgerufen, damit
  kein Client mit veraltetem Key im Cache bleibt.
- Der Verbindungstest laeuft ueber `asyncio` (`run.io_bound`) und schreibt das Ergebnis
  mit `record_connection_check` (Audit inklusive).
- Aktionen in Listen sind Icon-Buttons mit Tooltip und `aria-label`.
- Farben ausschliesslich aus `app/colors.py`; Schaltflaechen tragen nur Text, wenn sie
  kein Listenwerkzeug sind.
- Script-Seiten rufen Ausfuehrungen ueber `run.io_bound` und `ScriptRunner` auf; der
  API-Key wird nur fuer den Aufruf entschluesselt und nie angezeigt oder protokolliert.
- Bearbeiten koennen nur Benutzer mit `can_edit_scripts`; alle anderen sehen
  ausschliesslich Pruefen, Dry Run und die Versionsauswahl.

## Work Guidance

- Handlernamen (`save`, `load`, `toggle`) bleiben lokal je Seite, damit kein Zustand
  zwischen Seiten geteilt wird.
- Widgets, die ein Refreshable benoetigt, vor dem ersten Aufruf des Refreshables anlegen
  und Container explizit fuellen; sonst erscheinen Listen und Formulare in falscher
  Reihenfolge.
- Formularfelder nach dem Speichern zuruecksetzen, aber den geladenen Datensatz nicht
  ungefragt wechseln.

## Verification

- `python -m app serve`, danach als Superuser `/admin/profiles` und `/admin/users`
  aufrufen und "Verbindung testen" ausfuehren.
- Als Nicht-Superuser dieselben Pfade aufrufen: "Kein Zugriff" ohne Datenabruf.
- `/scripts` als Superuser und als Viewer aufrufen; der Viewer darf keinen
  Speichern-Knopf sehen, aber einen Dry Run ausfuehren.

## Child DOX Index

- Keine weiteren untergeordneten DOX-Dokumente.
