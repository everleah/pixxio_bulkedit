# Anwendung

## Purpose

- Python-Paket der NiceGUI-Anwendung: Konfiguration, Datenbank, Anmeldung und Rechte.
  Fachseiten (Profile, Scripts, Grid, Review, Runs) folgen in den naechsten Meilensteinen.

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
- `profiles.py`: Profile anlegen und aendern (API-Key verschluesselt, Hint statt Key),
  Verbindungstest protokollieren, Host normalisieren; schreibt `AdminAudit`-Eintraege.
- `clients.py`: `ClientFactory` haelt je Profil einen pixx.io-Client, ent- und
  verschluesselt den Key nur dort und liefert `current_user_name` fuer Verbindungstests.
- `ui/`: `guard.py` (Session- und Rollenpruefung), `shell.py` (Palette und Kopfzeile),
  `admin.py` (Seiten `/admin/profiles` und `/admin/users`); Details in `ui/AGENTS.md`.
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
- Werte im effektiven Stand immer als `CASE WHEN change.id IS NOT NULL THEN change.new_value
  ELSE json_extract(...) END` ausdruecken; `COALESCE` wuerde geleerte Werte falsch aufloesen.
- `app/bench/` arbeitet offline auf synthetischen Daten und nie auf der Anwendungsdatenbank.
- Die Prototyp-Route `/bench` und `/bench/rows` gehoert nur zum Lastnachweis; Fachseiten
  entstehen getrennt davon.
- UI-Farben ausschliesslich aus `app/colors.py` beziehen, auch fuer AG Grid
  (`--ag-*`-Variablen auf dem Grid-Container).
- Aktionen in Werkzeugleisten als Icon-Button mit Tooltip und `aria-label` umsetzen,
  nicht als Textbutton; Text bleibt der Tooltip.
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
- Datumswerte als `YYYY-MM-DD HH:MM:SS` senden; ISO mit Offset lehnt die API ab.

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

- `ui/AGENTS.md`: NiceGUI-Seiten, Zugriffsschutz je Seite und Profile-/Benutzerverwaltung.
- `models/` wird hier mitgefuehrt.
