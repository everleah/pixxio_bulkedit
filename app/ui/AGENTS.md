# Oberflaeche

## Purpose

- NiceGUI-Seiten der Anwendung: gemeinsamer Rahmen, serverseitiger Zugriffsschutz und die
  Verwaltung von Profilen und Benutzern.

## Ownership

- `guard.py`: `current_user` (Signierte Session plus Aktivpruefung), `is_superuser`,
  `logout`, `redirect_to_login`.
- `widgets.py`: `action_button` (Icon, Tooltip, `aria-label`) und `nav_link`; alle
  Werkzeugleisten nutzen diese Helfer statt Textbuttons.
- `shell.py`: `apply_palette`, `apply_locale` (Sprache aus der Session), `page_header`
  mit Navigation, Sprachumschalter (DE/EN) und Abmelde-Icon.
- `i18n.py`: Katalog der Oberflächentexte (Deutsch als Quelle, Englisch als Übersetzung);
  `t()` formatiert Platzhalter, `describe_error` übersetzt bekannte Fehler über
  `translation_key`.
- `admin.py`: `register_admin_pages` registriert `/admin/profiles` und `/admin/users`.
  Beide Seiten pruefen die Rolle serverseitig, zeigen eine Liste und ein gemeinsames
  Formular fuer Anlegen und Bearbeiten.
- `scripts.py`: `register_script_pages` registriert `/scripts` (Liste, Vorlagen kopieren)
  und `/scripts/{script_id}` (Editor mit `ui.codemirror`, Parameterformular aus `PARAMS`,
  Pruefen, Dry Run, Speichern, Veroeffentlichen; `script_id = 0` legt neu an).
- `workspaces.py`: `register_workspace_pages` registriert `/workspaces` (Laden aus einem
  veroeffentlichten Script, Excel-Import, Liste offener Entwuerfe) und `/workspaces/{id}`
  (AG Grid mit Infinite Row Model). Daten liefern `GET /workspace/rows` (effektiver Stand,
  Filter, Sortierung, `onlyChanged`) und `GET /workspace/changes` (geaenderte Zellen je
  Asset). Die Werkzeugleiste enthaelt den Excel-Export der markierten oder gefilterten
  Zeilen.
- `review.py`: `register_review_pages` registriert `/workspaces/{id}/review`: Liste aller
  Feldänderungen, Fehler/Hinweise (inklusive externer Aenderungen), `Dry Run prüfen`,
  `Jetzt schreiben` und Rueckweg ins Grid.
- `runs.py`: `register_run_pages` registriert `/runs` (Laufuebersicht mit Zaehlern je
  Status, `Alte Feldwerte entfernen`) und `/runs/{id}` (Feldhistorie je Datei mit
  Alt-/Neu-Wert, `Undo vorbereiten`).

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
- Jeder sichtbare Text läuft über `t(...)`; deutsche Quelltexte mit Umlauten, englische
  Übersetzung in `app/i18n.py`. Keine Textbutton-Beschriftungen für Aktionen.
- Die Sprache wird pro Session gespeichert (`locale` in `app.storage.user`) und über
  DE/EN in der Kopfzeile gewechselt; `apply_locale()` steht am Anfang jeder Seite.
- Farben ausschliesslich aus `app/colors.py`; Schaltflaechen tragen nur Text, wenn sie
  kein Listenwerkzeug sind.
- Script-Seiten rufen Ausfuehrungen ueber `run.io_bound` und `ScriptRunner` auf; der
  API-Key wird nur fuer den Aufruf entschluesselt und nie angezeigt oder protokolliert.
- Bearbeiten koennen nur Benutzer mit `can_edit_scripts`; alle anderen sehen
  ausschliesslich Pruefen, Dry Run und die Versionsauswahl.
- Das Grid liest ausschliesslich ueber den Endpunkt im effektiven Stand; Aenderungen
  schreibt die Seite direkt ueber `set_change` und sendet dazu die zuletzt gesehene
  `edit_revision`. Eine veraltete Revision meldet der Service als Konflikt; die Seite
  zeigt dann den Hinweis "in einem anderen Tab geaendert" und verlangt ein Neuladen.
- Zellhervorhebung und Zeilenmarkierung laufen ueber AG-Grid-Ausdruecke
  (`cellClassRules`, `rowClassRules`) mit `!!data && ...`, weil AG Grid die Regeln auch
  fuer noch nicht geladene Zeilen auswertet.
- Nach jeder Aenderung: `/workspace/changes` neu laden, `purgeInfiniteCache` ausfuehren und
  den Statustext (Zeilen, Aenderungen, Revision) neu setzen.
- Die Review-Seite arbeitet ausschliesslich ueber `app/writer.py` und `app/writeplan.py`;
  sie baut das Preview bei jedem Schritt neu (Digest-Pruefung) und zeigt Fehler, Hinweise
  und Konflikte an. Geschrieben wird nur ueber `client_factory.writer_client_for`.
- Blockierende Arbeit (Preview, Dry Run, Schreiben) laeuft in `run.io_bound` und oeffnet
  dort eine eigene Session; danach aktualisiert die Seite die Anzeige mit dem neuen Preview.
- Ein Feld "Kommentar zum Statuswechsel" gehoert zum Preview-Aufbau: `build_preview` bricht
  ohne Kommentar ab, sobald `std:fileStateID` geaendert wird; das Feld wird dann rot
  markiert und der Fehler in der Hinweisliste angezeigt.
- Nach erfolgreichem Schreiben zeigt die Seite das frische Preview (0 Aenderungen) und
  meldet, wie viele Aenderungen aus dem Entwurf entfernt wurden.
- Die Ueberschreibbestaetigung ist eine Checkbox und wird nur wirksam, wenn Konflikte
  gemeldet sind; ohne Bestaetigung blockiert `execution_blockers` den Live-Lauf.
- `/runs/{id}` zeigt je Feld Alt-/Neu-Wert und Status; `Undo vorbereiten` springt nach
  Erfolg direkt in die Review-Seite des neuen Undo-Arbeitsbestands. Bei nur teilweise
  wirksamen Laeufen erscheint ein Hinweis, dass nur wirksame Felder zurueckgenommen werden.
- `Status abgleichen` erscheint bei Live-Laeufen, die nicht `ok` sind, und ruft
  `app/writer.reconcile` auf: Ruecklesung statt erneutem Senden, danach Neuladen der Seite.
  Ein Undo eines Statuswechsels verlangt in der Review-Seite ebenfalls einen Kommentar.
- Der Excel-Export laeuft ueber `app/xlsx.export_workbook` in `run.io_bound` mit eigener
  Session und startet den Download mit `ui.download(bytes, dateiname)`; ungeschriebene
  Aenderungen werden nur gemeldet, nie mitgeschrieben.
- Der Excel-Import ist ein Dialog auf `/workspaces`: Profil waehlen, Datei hochladen
  (`ui.upload`, `.xlsx`, `MAX_FILE_BYTES`), Zusammenfassung und Zellbefunde anzeigen,
  dann importieren. Ohne Export-Snapshot bleibt `Importieren` gesperrt, bis die Checkbox
  "Ohne Exportbasis importieren" bestaetigt wurde. Nach Erfolg fuehrt ein Button in den
  neuen Arbeitsbestand (Review). Nur Editor und Superuser duerfen importieren, das Profil
  muss `allow_write` haben.

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
- `/workspaces`: bestehenden Arbeitsbestand oeffnen, eine Zelle bearbeiten (Status zeigt
  eine Aenderung und eine hoehere Revision), "nur geaenderte Zeilen" sowie Wertfilter
  pruefen, Bulk-Wert setzen und Aenderungen verwerfen.
- `/workspaces/{id}/review`: Dry Run ausfuehren (Protokolleintrag mit Status `ok`), dann
  "Jetzt schreiben"; nach Erfolg steht die Aenderungszahl auf 0 und die Werte sind im Grid
  sichtbar. Mit einer extern geaenderten Datei muss der Lauf ohne Bestaetigung blockieren.
- Excel: im Grid exportieren, in der Arbeitsmappe eine Zelle aendern, ueber `/workspaces`
  importieren; der neue Arbeitsbestand zeigt genau diese Aenderung, und die Review-Seite
  schreibt sie mit `run.source = xlsx`.

## Child DOX Index

- Keine weiteren untergeordneten DOX-Dokumente.
