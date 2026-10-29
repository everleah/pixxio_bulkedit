# Tests

## Purpose

- Automatisierte Verifikation der Entwicklungsbasis und spaeter der Anwendung.

## Ownership

- `test_environment.py`: Import-Smoke-Tests der geplanten Anwendungsabhaengigkeiten.

## Local Contracts

- Standardtests benoetigen weder pixx.io-Zugangsdaten noch Netzwerkzugriff.
- Import-Smoke-Tests sind kein Nachweis fuer API-Verhalten oder Lastziele.

## Work Guidance

- Zuerst die vom geaenderten Verhalten betroffenen Tests ausfuehren.

## Verification

- `.\.venv\Scripts\python.exe -m pytest -q`

## Child DOX Index

- Keine weiteren untergeordneten DOX-Dokumente.
