# Tests

## Purpose

- Automatisierte Verifikation der Entwicklungsbasis und der Anwendung.

## Ownership

- `conftest.py`, `support.py`: gemeinsame Fixtures (temporaere SQLite-Datei, Engine,
  Session, Schluessel) und der typisierte `make_settings`-Helfer.
- `test_environment.py`: Import-Smoke-Tests der Abhaengigkeiten.
- `test_app_modules.py`: Import-Smoke-Tests der Anwendungsmodule.
- `test_settings.py`, `test_crypto.py`, `test_auth.py`, `test_db.py`, `test_cli.py`,
  `test_colors.py`: Konfiguration, Verschluesselung, Rollen und Rechte, Datenbank und
  Migrationen, Kommandozeile (inklusive Profil-Anlage und Key-Rotation), Farbkontrast.
- `test_spike.py`: Phase-1-Spikepruefungen ohne Netzzugriff; die `summarize_*`-Funktionen
  arbeiten auf nachgebauten Antwortobjekten.
- `test_spike_write.py`: Ledger, Schutzgrenze, PNG-Testdateien, Payload-Aufbau und
  CLI-Abbrueche des Schreibpfads; ebenfalls ohne Netzzugriff.
- `test_bench.py`: synthetische Daten, SQL auf dem effektiven Stand (Aenderung gewinnt,
  Leeren faellt nicht auf den Snapshot zurueck) und ein kleiner Lastnachweis.
- `test_profiles.py`: Profile (Verschluesselung, Namenspruefung, Key-Rotation, Audit),
  Verbindungstest und `ClientFactory`-Cache; `current_user_name` und `response_mapping`
  laufen gegen nachgebaute Client-Antworten.
- `test_scripts.py`: Script-Vertrag (`PARAMS`, `COLUMNS`, Filter, Ergebnisse),
  RestrictedPython-Abweisungen, Fassade gegen einen nachgebauten Client, Versionierung
  und Vorlagen sowie der Kindprozess mit Zeitlimit.
- `test_workspaces.py`: Normalisierung (Texte exakt, Datum/Zahl/Boolean/Auswahl),
  Schemaaufloesung und SchemaCache, Arbeitsbestaende (Snapshot, ChangeSet, Revision,
  effektive Seiten mit Filter/Sortierung, Massenaktionen, Ablauf) und der Loader gegen
  einen nachgebauten Client.
- `test_i18n.py`: Vollstaendigkeit des englischen Katalogs (jeder `t(...)`-Text muss
  uebersetzt sein), Platzhalterformatierung, Sprachumschaltung und Rueckfall auf Deutsch.

## Local Contracts

- Standardtests benoetigen weder pixx.io-Zugangsdaten noch Netzwerkzugriff.
- Tests duerfen nicht von einer vorhandenen Projekt-`.env` abhaengen; wenn der Fall
  "keine Konfiguration" geprueft wird, mit `monkeypatch.chdir(tmp_path)` in ein leeres
  Verzeichnis wechseln.
- Tests schreiben ausschliesslich in temporaere SQLite-Dateien aus `tmp_path`.
- Import-Smoke-Tests sind kein Nachweis fuer API-Verhalten oder Lastziele.
- Schemaaenderungen muessen `test_migrationen_passen_zu_modellen` bestehen.

## Work Guidance

- Zuerst die vom geaenderten Verhalten betroffenen Tests ausfuehren.
- Tabellen in Tests ueber `Base.metadata.create_all` erzeugen, Migrationen nur im
  Migrationstest.

## Verification

- `.\.venv\Scripts\python.exe -m pytest -q`

## Child DOX Index

- Keine weiteren untergeordneten DOX-Dokumente.
