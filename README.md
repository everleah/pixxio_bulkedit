# pixxio_bulkedit

Eine Webanwendung, mit der ausgewählte Assets (Files) aus pixx.io tabellarisch geladen, im Grid editiert und nur die geänderten Werte zurückgeschrieben werden.

## Entwicklungsumgebung (Windows)

Grundlage ist der [bestaetigte Umsetzungsplan](plan/implementation_plan.md).
Die lokale `.venv` verwendet CPython 3.14. Implementiert sind Konfiguration, Datenbank
mit Alembic, Anmeldung mit Rollen und Rechten sowie die Kommandozeile; Profil-, Script-,
Grid- und Review-Seiten folgen. Die Live-Anbindung an pixx.io ist noch nicht implementiert.
Die Umgebung ist von anderen Projekten isoliert.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock.txt
.\.venv\Scripts\python.exe -m pip install --upgrade --index-url https://pypi.org/simple pixxio-client
```

Der Lock-Snapshot enthaelt die unter Windows mit Python 3.14 installierten direkten
und transitiven Pakete. Ausnahme: `pixxio-client` bleibt bewusst ungepinnt und wird
bei Einrichtung und Updates explizit auf die aktuelle stabile PyPI-Version aktualisiert.
Der Snapshot ist daher kein vollstaendiger reproduzierbarer oder
plattformuebergreifender Container-Lock. Die direkten Abhaengigkeiten stehen
in `requirements.txt` und `requirements-dev.txt`. Nach bewussten Aenderungen in einer
sauberen Umgebung installieren, alle Gates pruefen und den Snapshot aktualisieren:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install --upgrade --index-url https://pypi.org/simple pixxio-client
$snapshot = .\.venv\Scripts\python.exe -m pip freeze --exclude pixxio-client
@($snapshot; "pixxio-client") | Set-Content -Encoding UTF8 requirements-dev.lock.txt
```

Vor dem Einsatz im Container dessen Python-Version und Abhaengigkeiten separat
validieren; die lokale Version legt noch kein Docker-Basisimage fest.

Client-Quelle ist ausschliesslich die aktuelle stabile Veroeffentlichung von
[pixxio-client auf PyPI](https://pypi.org/project/pixxio-client/), ohne `--pre`.
Interne Wheels und bearbeitbare Installationen des Nachbarprojekts entfallen.
Nach jedem Update die Gates ausfuehren und die tatsaechlich eingesetzte Version fuer
Abnahmen dokumentieren. Lokal vorhandene, unveroeffentlichte Client-Funktionen
duerfen nicht als auf PyPI verfuegbar vorausgesetzt werden. Updates erfolgen bewusst
bei Einrichtung beziehungsweise Wartung, nicht automatisch beim App-Start.

Fuer Abnahmen dokumentierter Stand: `pixxio-client 0.4.3` (PyPI, 30.10.2026).

## Projektstruktur

- `app/`: Anwendungspaket mit Einstellungen, Datenbankschicht, Modellen, Anmeldung,
  Farben, Kommandozeile und NiceGUI-Start.
- `migrations/` und `alembic.ini`: Alembic-Umgebung mit der Initial-Revision `0001`.
- `tests/`: Offline-Tests ohne pixx.io-Zugriff.
- `plan/`: Fachkonzept und bestaetigter Umsetzungsplan.

## Konfiguration und Start

Die Anwendung startet nur mit vollstaendiger Konfiguration; es gibt keine
Standardsecrets und kein Standardpasswort. Die Vorlage [`.env.example`](.env.example)
als `.env` ins Projektwurzelverzeichnis kopieren und ausfuellen; `.env` ist von Git
ausgeschlossen.

```powershell
Copy-Item .env.example .env
```

| Variable | Zweck |
|---|---|
| `BULKEDIT_DB_PATH` | Pfad der SQLite-Datei |
| `BULKEDIT_MASTER_KEY` | Fernet-Schluessel fuer die API-Keys in der Datenbank |
| `BULKEDIT_STORAGE_SECRET` | Secret fuer die signierte NiceGUI-Session (mindestens 16 Zeichen) |

Optional: `BULKEDIT_SESSION_TIMEOUT_MINUTES` (Standard 60),
`BULKEDIT_LOGIN_MAX_ATTEMPTS` (Standard 5), `BULKEDIT_LOGIN_WINDOW_SECONDS` (Standard 300),
`BULKEDIT_SCRIPT_TIMEOUT_SECONDS` (Standard 60), `BULKEDIT_SCRIPT_MAX_OUTPUT_CHARS`
(Standard 20000). Werte koennen auch in einer `.env` im Projektwurzelverzeichnis stehen.

```powershell
.\.venv\Scripts\python.exe -m app generate-master-key   # neuen Fernet-Key ausgeben
.\.venv\Scripts\python.exe -m app init-db               # Datenbank anlegen und migrieren
.\.venv\Scripts\python.exe -m app create-superuser --username admin
.\.venv\Scripts\python.exe -m app serve                 # http://127.0.0.1:8080
```

`create-superuser` fragt das Passwort interaktiv ab oder liest es mit
`--password-stdin` aus der ersten stdin-Zeile; ein erneuter Aufruf setzt das Passwort
zurueck und stellt die Superuser-Rolle wieder her. Schemaaenderungen laufen
ausschliesslich ueber neue Alembic-Revisionen; `python -m alembic check` und der Test
`test_migrationen_passen_zu_modellen` pruefen den Gleichstand mit den Modellen.

## Code-Quality-Gates

Die empfohlenen VS-Code-Erweiterungen sind Python, Pylance und Ruff.
Als Interpreter `.venv\Scripts\python.exe` verwenden. Pylance prueft den gesamten
Workspace; Typpruefmodus und Python-Version kommen fuer Pylance und Pyright aus
`pyproject.toml`. Ruff uebernimmt Formatierung und Importordnung beim Speichern.

VS Code: **Terminal > Run Task > quality: all** fuehrt die Gates nacheinander aus.
Alternativ:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pyright
.\.venv\Scripts\python.exe -m pytest -q
```

Alle Befehle muessen erfolgreich sein. Pyright ist das ausfuehrbare CLI-Typgate;
Pylance liefert zusaetzlich die Editor-Diagnostik. Die Tests pruefen Konfiguration,
Verschluesselung, Rollen und Rechte, Datenbank und Migrationen, Kommandozeile sowie
Farbkontrast; Script-Isolation, Lastziele und Live-API bleiben offen.