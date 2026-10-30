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
  Benutzer, Profile, Scripts, Arbeitsbestand, Snapshot, ChangeSet, WritePlan, Runs,
  Excel-Exporte (`xlsx_export`) und Admin-Audit.
- `auth.py`: Argon2id-Hashes, Rollen und Rechte, Login-Drosselung, Session-Helfer,
  Schutz des letzten aktiven Superusers.
- `colors.py`: Meadow-Palette und WCAG-Kontrastberechnung; `TEXT_STYLE`/`text_style`
  liefern kontraststarke Textfarben (≥ 4.5:1 auf dem Seitenhintergrund), `FOCUS_CSS`
  den sichtbaren Fokusrahmen.
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
- `xlsx.py`: Excel-Schnittstelle `bulkedit-xlsx/1`. `export_workbook` schreibt den
  Snapshot des Arbeitsbestands (Blaetter `Daten`, `Felder`, `Auswahlwerte`, `Info`) und
  legt den Exportstand in `xlsx_export` ab; `parse_workbook`, `diff_rows` und
  `import_workbook` lesen die Arbeitsmappe, vergleichen Exportbasis, Excel und aktuellen
  Stand (Drei-Wege) und legen daraus einen neuen Arbeitsbestand mit ChangeSet an.
  `purge_exports` haelt die Aufbewahrungsfrist ein.
- `profiles.py`: Profile anlegen und aendern (API-Key verschluesselt, Hint statt Key),
  Verbindungstest protokollieren, Host normalisieren, Nutzung zaehlen (`profile_usage`)
  und unbenutzte Profile loeschen (`delete_profile`, nur Superuser); schreibt
  `AdminAudit`-Eintraege.
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
  `create-profile`, `purge-history`, `serve`.
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
  gibt `SecretBox`/`ClientFactory` als Anwendungszustand weiter. `GET /health` prueft die
  Datenbank und liefert Version und Status (Docker/Traefik), `on_shutdown` protokolliert
  das Beenden. Host und Port kommen aus `BULKEDIT_HOST`/`BULKEDIT_PORT`.
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
  Neustart ohne erneutes Senden: Ruecklesung entscheidet ueber `ok`/`partial`/`unknown`,
  der zugehoerige Lauf wird abgeschlossen, `ChangeLog`-Zeilen werden nachgezogen und bei
  vollstaendigem Erfolg `commit_applied` ausgefuehrt. Der Laufmodus stammt aus dem Lauf,
  nicht aus dem Plan (ein Absturz laesst den Plan im Zustand `draft`).
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
  Schaltflaeche in `/runs`. Derselbe Aufruf entfernt Export-Snapshots nach
  `EXPORT_TTL_DAYS` (90) Tagen ueber `purge_exports`.
- Loeschen ist nur ohne Verwendung erlaubt: `delete_script` verlangt `can_edit_scripts`,
  lehnt Vorlagen ab und prueft `script_usage` (Arbeitsbestaende und Laeufe ueber die
  Versionen, per `count(distinct)`); `delete_profile` verlangt die Superuser-Rolle und
  prueft `profile_usage` (Arbeitsbestaende und Laeufe). `workspace.profile_id` ist
  `RESTRICT`, die uebrigen Verweise sind `SET NULL` — die Pruefung im Service ist deshalb
  Pflicht, damit kein Protokoll seinen Bezug verliert. Beide Loeschungen landen im
  `AdminAudit` (Profil) beziehungsweise entfernen die Versionen per `CASCADE`.
- Excel-Export liest ausschliesslich den Snapshot (`workspace_asset`), nie den effektiven
  Stand: ungeschriebene Grid-Aenderungen werden nicht exportiert, der Export vermerkt sie
  nur (`pending_changes`/`hinweis` im Blatt `Info`). Zeile 1 haelt technische Schluessel,
  Zeile 2 die Anzeigenamen (AutoFilter), Daten ab Zeile 3, Spalte A `file_id`.
- Nicht schreibbare Spalten (`std:fileName`, `map`/`focalpoint`/`orientation`) sowie
  `@modifyDate` tragen das Praefix `@` und werden beim Import ignoriert.
- Textzellen werden immer als Text geschrieben (`cell.data_type = "s"`), damit Werte mit
  `=` keine Formel werden. Zellwerte ueber 32 767 Zeichen werden gekuerzt; die
  Exportbasis merkt sich das, damit der Import die Kuerzung nicht als Aenderung wertet.
- Der Import braucht den Export-Snapshot aus `xlsx_export` (Schluessel `export_id` im
  Blatt `Info`) fuer den Drei-Wege-Abgleich; ohne ihn ist nur ein Zwei-Wege-Vergleich
  moeglich, leere Zellen bleiben dann unberuecksichtigt und die Oberflaeche verlangt eine
  ausdrueckliche Bestaetigung. Zellen mit zwischenzeitlicher externer Aenderung werden
  uebersprungen und gemeldet, nie still ueberschrieben.
- Der Import legt einen regulaeren Arbeitsbestand an (`params_json.xlsx` mit Dateiname,
  `export_id`, `three_way`); Laeufe daraus tragen `run.source = xlsx` und
  `run.xlsx_export_id`. Die weitere Pruefung laeuft ueber Review, Dry Run und Schreiben
  wie bei jeder Grid-Aenderung.
- Zellwerte werden bereits beim Lesen geprueft (`canonical`); fehlerhafte Zellen landen als
  `CellIssue` mit `key` und Zeile im Ergebnis und werden nicht in den Abgleich uebernommen.
  `build_error_workbook` erzeugt daraus eine Kopie der hochgeladenen Arbeitsmappe mit
  markierten Zellen (`ERROR_FILL`), Kommentar je Zelle und dem Blatt `Fehler` (Zeile,
  Spalte, Meldung); `Info` erhaelt `fehler`/`hinweis`. Das Format bleibt `bulkedit-xlsx`,
  damit die korrigierte Datei erneut importiert werden kann.
- Werte im effektiven Stand immer als `CASE WHEN change.id IS NOT NULL THEN change.new_value
  ELSE json_extract(...) END` ausdruecken; `COALESCE` wuerde geleerte Werte falsch aufloesen.
- `effective_page` gibt mit `columns` genau die angezeigten Spalten zurueck und mischt
  ChangeSet-Werte auch fuer Schluessel ein, die noch nicht im Snapshot stehen. Sonst
  wuerde eine Bearbeitung in einer nachtraeglich gewaehlten Spalte im Grid sofort wieder
  verschwinden.
- Wird die Spaltenauswahl erweitert, laedt die Oberflaeche die fehlenden Spalten ueber
  `read_files` nach und ergaenzt sie mit `merge_snapshot_values` im Snapshot — nur
  fehlende Schluessel, vorhandene Werte bleiben unveraendert (der Diff-Basisstand darf
  nicht kippen). `missing_columns` ermittelt den Bedarf aus dem ersten Asset.
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
- Die Spaltenauswahl je Arbeitsbestand liegt in `params_json` unter dem reservierten
  Schluessel `VIEW_PARAM` (`"@columns"`, kein gueltiger Script-Parametername) und ist auf
  `MAX_SELECTED_COLUMNS` (80) begrenzt. Sie ist eine Anzeige-Einstellung: `stored_columns`,
  `store_columns` und `clear_columns` erhoehen bewusst nicht `edit_revision`, und die
  Review-Seite prueft ohne Spalteneinschraenkung (`script_columns=None`), damit eine
  verborgene Spalte keine erfasste Aenderung blockiert. Der Excel-Import speichert die
  Spalten der Datei als Auswahl.
- `close_workspace` setzt nur `status = closed` und laesst Snapshot und ChangeSet stehen;
  `list_workspaces(..., include_closed=True)` zeigt solche Entwuerfe, `reopen_workspace`
  setzt sie wieder auf `ready` und verlaengert die Frist. Erst `delete_workspace` loescht
  Daten (CASCADE auf Snapshot und ChangeSet). Die UI fragt vor beiden Aktionen nach.
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
- Statusfarben nie ueber Quasars `text-positive`/`text-negative`/`text-warning` setzen,
  sondern ueber `TEXT_STYLE[...]`/`text_style(...)`: Die Planfarben sind Flaechenfarben und
  als Text zu hell. Status wird zusaetzlich immer als Text ausgegeben.
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
