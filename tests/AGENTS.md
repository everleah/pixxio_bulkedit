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
  Migrationen, Kommandozeile, Farbkontrast.
- `test_spike.py`: Phase-1-Spikepruefungen ohne Netzzugriff; die `summarize_*`-Funktionen
  arbeiten auf nachgebauten Antwortobjekten.
- `test_spike_write.py`: Ledger, Schutzgrenze, PNG-Testdateien, Payload-Aufbau und
  CLI-Abbrueche des Schreibpfads; ebenfalls ohne Netzzugriff.
- `test_bench.py`: synthetische Daten, SQL auf dem effektiven Stand (Aenderung gewinnt,
  Leeren faellt nicht auf den Snapshot zurueck) und ein kleiner Lastnachweis.

## Local Contracts

- Standardtests benoetigen weder pixx.io-Zugangsdaten noch Netzwerkzugriff.
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
