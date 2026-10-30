# Anwendung

## Purpose

- Python-Paket der NiceGUI-Anwendung: Konfiguration, Datenbank, Anmeldung und Rechte.
  Fachseiten: Profile, Scripts, Arbeitsbestaende mit Grid, Review und Schreiblauf.

## Ownership

- `settings.py`: Pflicht-Env `BULKEDIT_DB_PATH`, `BULKEDIT_MASTER_KEY`,
  `BULKEDIT_STORAGE_SECRET`; Limits fuer Session, Login und Scripts; `database_url`.
- `crypto.py`: Fernet-Wrapper fuer API-Keys, Anzeige-Hint, Schluesselpruefung.
- `db.py`: Engine mit SQLite-PRAGMAs (`foreign_keys`, WAL, `busy_timeout`),
  Session-Factory, `session_scope`, Alembic-Lauf.
- `models/`: `Base` mit Namenskonvention und UTC-Zeitstempeln, Enums sowie Modelle fuer
  Benutzer, Profile, Scripts, Arbeitsbestand, Snapshot, ChangeSet, WritePlan, Runs und
  Admin-Audit.
- `auth.py`: Argon2id-Hashes, Rollen und Rechte, Login-Drosselung, Session-Helfer,
  Schutz des letzten aktiven Superusers.
- `colors.py`: Meadow-Palette und WCAG-Kontrastberechnung.
- `schema.py`: Profilschema mit `ColumnDef` (Schluessel `std:*`, `custom:<id>`,
  `standard:<id>`), `resolve_columns` (IDs oder Namen), `SchemaCache` mit TTL;
  `fetch_file_states` liefert die Dateistatus-Werte als Optionen von `std:fileStateID`.
- `normalize.py`: Anzeigenormalform je Feldtyp (Texte bleiben exakt), `values_equal`
  fuer den Diff, `display_value`.
- `workspaces.py`: Arbeitsbestaende (Snapshot in `workspace_asset.values_json`,
  ChangeSet in `workspace_change`), effektive Seiten mit Filter/Sortierung,
  Massenaktionen, Ablauf und Revision; `load_assets` laedt Script-Ergebnisse,
  `file_values` liest Spaltenwerte eines Payloads, `commit_applied` uebernimmt
  geschriebene Felder in den Snapshot und leert ihre Aenderung.
- `writeplan.py`: Schreibplan aus dem ChangeSet (`build_preview`, Gruppierung gleicher
  Payloads in Schritte zu `CHUNK_SIZE`), Payload-Bildung je Feldtyp, Digest des Entwurfs
  (`current_digest`, inklusive Kommentar), Konflikterkennung ueber `modifyDate` und
  Persistenz (`save_plan`, `plan_comment`).
- `writer.py`: Review gegen die API (`review`, `read_files`), Dry Run, Ausfuehrung,
  Rueckleseverifikation und Protokoll (`dry_run`, `execute`, `reconcile`).
- `runs.py`: Laufuebersicht (`list_runs` mit Zaehlern je Status), Feldhistorie
  (`run_changes`, `undoable_changes`), Undo-Vorbereitung (`prepare_undo`) und
  Aufbewahrungsgrenze (`purge_change_values`, 90 Tage).
- `profiles.py`: Profile anlegen und aendern (API-Key verschluesselt, Hint statt Key),
  Verbindungstest protokollieren, Host normalisieren; schreibt `AdminAudit`-Eintraege.
- `clients.py`: `ClientFactory` haelt je Profil einen pixx.io-Client, ent- und
  verschluesselt den Key nur dort und liefert `current_user_name` fuer Verbindungstests;
  `writer_client_for` liefert einen Client ohne automatische PUT-Wiederholungen.
- `ui/`: `guard.py` (Session- und Rollenpruefung), `shell.py` (Palette, Kopfzeile mit
  Sprachumschalter), `widgets.py` (Icon-Button mit Tooltip, Navigationslink),
  `admin.py` (Seiten `/admin/profiles` und `/admin/users`), `scripts.py` (Liste und Editor
  unter `/scripts`), `workspaces.py` (Liste `/workspaces`, Grid `/workspaces/{id}`,
  Datenendpunkte `/workspace/rows` und `/workspace/changes`), `review.py`
  (`/workspaces/{id}/review`: Aenderungsliste, Dry Run, Schreiben); Details in `ui/AGENTS.md`.
- `i18n.py`: Oberflächentexte; deutscher Quelltext plus englische Übersetzung. Jeder
  sichtbare Text läuft über `t(...)`, die Sprache liegt in der Session.
- `scripts/`: Abfrage-Scripts mit Vertrag, RestrictedPython, read-only Fassade `px`,
  Kindprozess-Ausfuehrung, Versionierung und Vorlagen; Details in `scripts/AGENTS.md`.
- `cli.py` mit `__main__.py`: `init-db`, `generate-master-key`, `create-superuser`,
  `create-profile`, `serve`.
- `spike/`: Machbarkeitspruefungen der Phase 1 gegen ein Testsystem. `settings.py` liest
  `PXTEST_*`, `client.py` haelt die Seitenlimits, `discovery.py` liest Schema und Werte,
  `ledger.py` fuehrt selbst angelegte Test-Assets, `guard.py` setzt die Schutzgrenze,
  `fixtures.py` erzeugt lokale PNG-Testdateien, `probe.py` enthaelt Anlage, Schreibpruefungen
  und Aufraeumen.
- `bench/`: Datenbank- und Grid-Lastnachweis der Phase 1. `synthetic.py` erzeugt
  deterministische Assets, `queries.py` haelt die SQL-Abfragen auf dem effektiven Stand,
  `runner.py` misst Datenbankverhalten, `grid.py` stellt den Grid-Prototyp unter `/bench`
  bereit, `cli.py` berichtet.
- `main.py`: NiceGUI-Start, Anmeldung, Session-Ablauf; registriert die Admin-Seiten und
  gibt `SecretBox`/`ClientFactory` als Anwendungszustand weiter.
- `alembic.ini` und `migrations/`: root-owned; Schemaaenderungen laufen ausschliesslich
  ueber Alembic-Revisionen.

## Local Contracts

- Neue Spalten oder Tabellen nur als Alembic-Revision; `test_migrationen_passen_zu_modellen`
  und `alembic check` muessen ohne Diff bleiben.
- Ein Schreibplan ist unveraenderlich und ueber `change_digest` an das ChangeSet gebunden.
  Aendert sich der Entwurf, blockiert `execute` mit `WriteError`; Dry Run und Live-Lauf
  verwenden denselben Plan (`write_plan.status` wechselt `draft` -> `running` -> Endzustand).
- Nur geaenderte Felder aufnehmen, identische Payloads gruppieren (ein `filesPut` je
  Payload und `CHUNK_SIZE`-Block). Konflikte werden ueber `modifyDate` erkannt; externe
  Aenderungen verlangen `overwrite_confirmed`.
- Der Writer sendet nichts blind erneut: `writer_client_for` (max_retries=0), Job-ID vor
  dem Warten speichern, danach zuruecklesen. Erfolg entsteht aus Job-Ergebnis plus
  Ruecklesung; unklare Ausgaenge werden `StepStatus.UNKNOWN`, nie Erfolg.
- Ein systematischer Fehler (`Unauthorized`, `Forbidden`) pausiert den Rest des Auftrags:
  verbleibende Schritte werden `skipped`. `reconcile` prueft bekannte Schritte nach einem
  Neustart ohne erneutes Senden.
- Nach vollstaendig erfolgreichem Lauf uebernimmt `commit_applied` die geschriebenen Felder
  in den Snapshot und entfernt sie aus dem ChangeSet; `ChangeLog` bleibt als Protokoll.
- `ChangeStatus` umfasst `planned`, `ok`, `failed`, `skipped`, `skipped_conflict`,
  `unknown`; `StepStatus` zusaetzlich `partial`. Beide Wertebereiche sind per CHECK
  abgesichert (Revision `0002`).
- Ein Undo entsteht ausschliesslich aus Eintraegen mit `ChangeStatus.OK`. Vor dem
  Zuruecknehmen wird der aktuelle Wert gegen den damals geschriebenen Wert geprueft;
  abweichende Felder werden uebersprungen und gemeldet. `prepare_undo` legt einen neuen
  Arbeitsbestand (Snapshot = aktueller Stand) an und schreibt die alten Werte als
  ChangeSet – Undo ist eine neue Aenderung durch dieselbe Review-/Schreibpipeline, kein
  Rollback.
- `purge_change_values` entfernt `old_value`/`new_value` nach
  `HISTORY_RETENTION_DAYS` (90) Tagen; `run`, `file_id`, `field_key` und `status` bleiben
  fuer die Laufuebersicht erhalten. Aufruf ueber `python -m app purge-history` oder die
  Schaltflaeche in `/runs`.
- Werte im effektiven Stand immer als `CASE WHEN change.id IS NOT NULL THEN change.new_value
  ELSE json_extract(...) END` ausdruecken; `COALESCE` wuerde geleerte Werte falsch aufloesen.
- Spaltenkennungen sind durchgaengig `std:<attribut>`, `custom:<feld-id>` oder
  `standard:<feld-id>`; Namen aus `COLUMNS` loest `app/schema.py` vor dem Speichern auf.
- Der Snapshot (`workspace_asset.values_json`) haelt Anzeigenormalform; das ChangeSet nur
  Zellen, deren Wert abweicht. Geloeschte Werte stehen als `NULL` im ChangeSet.
- Texte werden nie automatisch getrimmt; normalisiert werden nur Typen, Datumsformate und
  Mehrfachauswahlen (`app/normalize.py`).
- `workspace.edit_revision` erhoeht sich bei jeder Aenderung; Clients muessen ihre Revision
  mitsenden, sonst antwortet der Service mit `WorkspaceConflictError` (mehrere Tabs).
- Entwuerfe laufen nach `DRAFT_TTL_DAYS` (30) ab; unter `EXPIRY_WARNING_DAYS` (7) Resttagen
  warnt die UI. Laufende Schreibauftraege verlaengern die Laufzeit.
- Standardattribute der Datei (`std:*`) und Metadaten (`custom:*`, `standard:*`) werden
  getrennt gelesen: erstere direkt am File, letztere aus `metadataFields[str(feld_id)]`.
  Der Dateistatus kommt aus `fileState.id` und wird ueber die Optionen zu seinem Namen
  aufgeloest; geschrieben wird `fileStateID` als numerische ID.
- Ein Statuswechsel (`std:fileStateID`) verlangt in dieser Anwendung einen Kommentar:
  `build_preview` bricht ohne Kommentar ab und sendet ihn als `fileStateChangeComment`
  im selben Schritt. Der Kommentar steckt im Plan (`plan_json.comment`) und im Digest.
- `app/bench/` arbeitet offline auf synthetischen Daten und nie auf der Anwendungsdatenbank.
- Die Prototyp-Route `/bench` und `/bench/rows` gehoert nur zum Lastnachweis; Fachseiten
  entstehen getrennt davon.
- UI-Farben ausschliesslich aus `app/colors.py` beziehen, auch fuer AG Grid
  (`--ag-*`-Variablen auf dem Grid-Container).
- Sichtbare Texte laufen ueber `t(...)` aus `app/i18n.py`: deutscher Quelltext mit echten
  Umlauten als Schluessel, englische Uebersetzung im Katalog. Neue Texte immer in beiden
  Sprachen ergaenzen (`test_jeder_text_ist_uebersetzt` prueft die Vollstaendigkeit).
  Skript-Parameter (`PARAMS`) sind Daten und bleiben unuebersetzt.
- Aktionen in Werkzeugleisten als Icon-Button mit Tooltip und `aria-label` umsetzen,
  nicht als Textbutton (`app/ui/widgets.py::action_button`); Text bleibt der Tooltip.
  Ausnahmen sind Formular-Abschluesse wie "Anmelden".
- API-Keys liegen ausschliesslich verschluesselt in `profile.api_key_enc` und nie in
  Logs, Fehlermeldungen, Sessions oder im Browser.
- Berechtigungen werden serverseitig je Aktion geprueft; UI-Ausblendungen ersetzen das nicht.
- Zeitstempel werden in UTC ueber `utc_now` geschrieben.
- Fachliche Kennungen englisch im Code; Docstrings und UI-Texte deutsch.
- Keine Live-Schreibaufrufe gegen pixx.io ohne freigegebene File-ID-Liste.
- Schreibzugriffe im Spike nur ueber `assert_write_allowed` (Ledger plus Collection) und
  nur bei `PXTEST_IS_DEV=true`; Loeschungen ueber `assert_deletion_allowed` (nur Ledger).
- Ein unlesbares Ledger wird nie stillschweigend zurueckgesetzt, sondern als Fehler
  gemeldet.
- Standard-Metadaten nur auf Feldern schreiben, die das Asset fuehrt; die Editierbarkeit
  ist im Schema nicht erkennbar und muss aus der API-Antwort gelernt werden.
- `CustomMetadataBuilder` des Clients ist ab `pixxio-client 0.4.4` nutzbar; im Spike
  werden Eintraege trotzdem aus dem bereits geladenen Schema gebaut (kein zweiter Abruf).
- `pageSize`: `files` bis 500, `customMetadata` bis 50, `standardMetadata` ohne Paging
  (`FILES_PAGE_SIZE`/`METADATA_PAGE_SIZE` aus `app/spike/client.py` nutzen).
- `filesPut` ist nicht atomar: vor dem Senden validieren und nach Teilfehlern ruecklesen.
- Datumswerte als `YYYY-MM-DD HH:MM:SS` senden. Die API akzeptiert zusaetzlich den
  `T`-Separator und schneidet Mikrosekunden ab, lehnt aber ein Datum ohne Uhrzeit
  (`2026-12-31`) und Werte mit Offset (`...+02:00`) mit `no DateTime` ab.

## Work Guidance

- Neue Konfigurationswerte in `Settings` mit Default und Grenzen anlegen; Pflichtwerte
  ohne Standardsecret und mit Validator.
- Modelle vor dem Migrieren in `app/models/__init__.py` exportieren, damit Alembic sie sieht.
- `expire_on_commit=False` bleibt aktiv: Objekte werden nach `session_scope` weiter gelesen.

## Verification

- `python -m app init-db` und `python -m app create-superuser --username admin` laufen
  mit gesetzter Konfiguration durch.
- `python -m app serve` liefert die Anmeldeseite unter `http://127.0.0.1:8080/`.
- Gates laut `README.md`.

## Child DOX Index

- `ui/AGENTS.md`: NiceGUI-Seiten, Zugriffsschutz je Seite, Profile-/Benutzerverwaltung
  und Script-Editor.
- `scripts/AGENTS.md`: Script-Vertrag, Sicherheitsschicht, Fassade, Ausfuehrung, Versionen.
- `models/` wird hier mitgefuehrt.
