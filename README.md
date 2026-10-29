# pixxio_bulkedit

Eine Webanwendung, mit der ausgewählte Assets (Files) aus pixx.io tabellarisch geladen, im Grid editiert und nur die geänderten Werte zurückgeschrieben werden.

## Entwicklungsumgebung (Windows)

Grundlage ist der [bestaetigte Umsetzungsplan](plan/implementation_plan.md).
Die lokale `.venv` verwendet CPython 3.14; Anwendung und Live-Anbindung sind noch
nicht implementiert. Die Umgebung ist von anderen Projekten isoliert.

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
Pylance liefert zusaetzlich die Editor-Diagnostik. Die vorhandenen Tests pruefen
zunaechst nur die Importierbarkeit der geplanten Anwendungsbibliotheken, noch keine
Anwendungsfunktionen, Script-Isolation oder Live-API.