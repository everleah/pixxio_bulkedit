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
- `cli.py` mit `__main__.py`: `init-db`, `generate-master-key`, `create-superuser`, `serve`.
- `spike/`: Machbarkeitspruefungen der Phase 1 gegen ein Testsystem. `settings.py` liest
  `PXTEST_*`, `client.py` haelt die Seitenlimits, `discovery.py` liest Schema und Werte,
  `ledger.py` fuehrt selbst angelegte Test-Assets, `guard.py` setzt die Schutzgrenze,
  `fixtures.py` erzeugt lokale PNG-Testdateien, `probe.py` enthaelt Anlage, Schreibpruefungen
  und Aufraeumen.
- `main.py`: NiceGUI-Start, Anmeldung und Session-Ablauf.
- `alembic.ini` und `migrations/`: root-owned; Schemaaenderungen laufen ausschliesslich
  ueber Alembic-Revisionen.

## Local Contracts

- Neue Spalten oder Tabellen nur als Alembic-Revision; `test_migrationen_passen_zu_modellen`
  und `alembic check` muessen ohne Diff bleiben.
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
  ist im Schema nicht erkennbar.
- `pageSize`: `files` bis 500, `customMetadata` bis 50, `standardMetadata` ohne Paging
  (`FILES_PAGE_SIZE`/`METADATA_PAGE_SIZE` aus `app/spike/client.py` nutzen).

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

- Keine weiteren untergeordneten DOX-Dokumente; `models/` wird hier mitgefuehrt.
