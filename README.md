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
.\.venv\Scripts\python.exe -m pip install --upgrade --no-cache-dir --index-url https://pypi.org/simple pixxio-client
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
.\.venv\Scripts\python.exe -m pip install --upgrade --no-cache-dir --index-url https://pypi.org/simple pixxio-client
$snapshot = .\.venv\Scripts\python.exe -m pip freeze --exclude pixxio-client
@($snapshot; "pixxio-client") | Set-Content -Encoding UTF8 requirements-dev.lock.txt
```

Vor dem Einsatz im Container dessen Python-Version und Abhaengigkeiten separat
validieren; die lokale Version legt noch kein Docker-Basisimage fest.

Client-Quelle ist ausschliesslich die aktuelle stabile Veroeffentlichung von
[pixxio-client auf PyPI](https://pypi.org/project/pixxio-client/), ohne `--pre`.
Interne Wheels und bearbeitbare Installationen des Nachbarprojekts entfallen.
Nach jedem Update die Gates ausfuehren und die tatsaechlich eingesetzte Version fuer
Abnahmen dokumentieren. `--no-cache-dir` ist noetig, weil pip sonst eine
zwischengespeicherte, veraltete Version installiert, obwohl auf PyPI bereits ein
neueres Release liegt. Lokal vorhandene, unveroeffentlichte Client-Funktionen
duerfen nicht als auf PyPI verfuegbar vorausgesetzt werden. Updates erfolgen bewusst
bei Einrichtung beziehungsweise Wartung, nicht automatisch beim App-Start.

Fuer Abnahmen dokumentierter Stand: `pixxio-client 0.4.5` (PyPI, 30.10.2026).

## Projektstruktur

- `app/`: Anwendungspaket mit Einstellungen, Datenbankschicht, Modellen, Anmeldung,
  Profilen und Client-Factory, Farben, Kommandozeile, NiceGUI-Start, `ui/` fuer Seiten
  und Zugriffsschutz sowie `scripts/` fuer das Abfrage-Script-System.
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

### pixx.io-Profil ohne Key im Terminal anlegen

`create-profile` liest den API-Key aus einer Umgebungsvariablen oder aus `.env`, nie aus
einem Argument. Ein erneuter Aufruf mit demselben Namen aktualisiert das Profil und
rotiert damit auch den Key.

```powershell
.\.venv\Scripts\python.exe -m app create-profile --name test --host <host>.px.media `
    --api-key-env PXTEST_API_KEY [--max-rows 5000] [--read-only] [--inactive]
```

Weitere Profile, Benutzer und Rechte verwaltet ein Superuser unter `/admin/profiles` und
`/admin/users`. Der gespeicherte Key wird dort nur als Hint (`••••abcd`) angezeigt; ein
leeres Key-Feld behaelt den bisherigen Key. "Verbindung testen" meldet den API-Benutzer
und protokolliert das Ergebnis im Admin-Audit.

## Abfrage-Scripts

Scripts bestimmen, welche Assets in einen Arbeitsbestand geladen werden - gelesen wird
ausschliesslich ueber die App, nie im Script. `python -m app init-db` legt vier Vorlagen
an (Collection, Verzeichnis, ID-Liste, Suche); eigene Scripts entstehen unter `/scripts`.

Vertrag eines Scripts:

```python
PARAMS = {
    "collection": {"type": "str", "label": "Collection", "required": True},
    "include_archived": {"type": "bool", "label": "Archivierte einbeziehen", "default": False},
}
COLUMNS = ["std:subject", "custom:Kampagne"]


def query(px, params):
    col = px.collection(params["collection"])          # Name oder ID
    return px.filters.collection(col["id"], include_archived=params["include_archived"])
```

Erlaubte Rueckgaben sind ein Filter-Dict, eine Liste von File-IDs oder
`px.result(filter=..., ids=..., columns=..., note=...)`. Die Fassade liest nur
(`collection(s)`, `directory/directories`, `metadata_fields`, `count`, `find_ids`, `file`,
`log`, `filters`), liefert einfache Dicts und begrenzt Ergebnisse auf `max_rows` des
Profils sowie 1000 API-Aufrufe je Lauf.

Sicherheit: Scripts laufen uebersetzt mit RestrictedPython (keine Imports, kein `open`,
`eval`, `exec`, keine `_`-Attribute) in einem eigenen Prozess mit Zeitlimit
(`BULKEDIT_SCRIPT_TIMEOUT_SECONDS`) und begrenzter Ausgabe
(`BULKEDIT_SCRIPT_MAX_OUTPUT_CHARS`). Der Client mit dem API-Key existiert nur in diesem
Prozess; das Script sieht ihn nicht. Speichern und Veroeffentlichen duerfen nur Benutzer
mit Script-Recht (`can_edit_scripts` oder Superuser); alle anderen fuehren
veroeffentlichte Versionen aus. Jeder Lauf landet mit Version, Parametern und Ergebnis in
der Tabelle `run`.

Filter folgen der pixx.io-API: Verknuepfungen ueber `px.filters.and_(...)`/`or_(...)`
(`connectorAnd`/`connectorOr`), Negation ueber `px.filters.not_(...)` (`inverted`).
Metadatenfilter (`metadata_text`, `metadata_selection`, `metadata_date`,
`has_metadata_field`) akzeptieren eine Feld-ID oder einen Feldnamen; die Fassade loest
Namen vor dem Senden auf.

## Phase-1-Spike (nur lesend)

Die Machbarkeitspruefungen nutzen eigene Variablen und beruehren die
Anwendungskonfiguration nicht:

| Variable | Zweck |
|---|---|
| `PXTEST_HOST` | Host des Testsystems |
| `PXTEST_API_KEY` | API-Key des Testsystems (nie im Repo) |
| `PXTEST_COLLECTION_ID` | Collection fuer die Pruefungen |
| `PXTEST_IS_DEV` | `true` nur auf einem Testsystem; Voraussetzung fuer Schreibzugriffe |
| `PXTEST_LEDGER_PATH` | optional, Standard `data/spike/ledger.json` |

```powershell
.\.venv\Scripts\python.exe -m app.spike report
.\.venv\Scripts\python.exe -m app.spike whoami
.\.venv\Scripts\python.exe -m app.spike collection
.\.venv\Scripts\python.exe -m app.spike collections
.\.venv\Scripts\python.exe -m app.spike schema --json
.\.venv\Scripts\python.exe -m app.spike files --limit 10
.\.venv\Scripts\python.exe -m app.spike paging --page-size 5
.\.venv\Scripts\python.exe -m app.spike fixtures create --count 2
.\.venv\Scripts\python.exe -m app.spike probe
.\.venv\Scripts\python.exe -m app.spike status
.\.venv\Scripts\python.exe -m app.spike fixtures delete
```

`collection`, `files` und `paging` akzeptieren `--collection-id`, um auch andere
Collections lesend zu pruefen (Standard ist `PXTEST_COLLECTION_ID`); Schreibzugriffe
bleiben auf die konfigurierte Collection beschraenkt.

`report`, `whoami`, `collection`, `schema` und `files` lesen nur. `fixtures create`
legt eigene PNG-Testdateien in der Collection an und protokolliert ihre IDs in
`data/spike/ledger.json`; `probe` schreibt ausschliesslich auf Assets aus diesem
Ledger (zusaetzlich muessen sie in `PXTEST_COLLECTION_ID` liegen) und prueft
Mehrfach-Payload, Einzel-ID, Auswahl, Mehrfachauswahl, Standard-Metadaten, Entfernen,
`truncateSubject`, Keywords und Fehlerdetails. `fixtures delete` entfernt die
Ledger-Assets und verifiziert die Loeschung ueber die Collection. Ohne
`PXTEST_IS_DEV=true` werden Anlegen, Schreiben und Loeschen verweigert.
`data/` ist von Git ausgeschlossen.

## Datenbank-Lastnachweis (Phase 1.6.3)

```powershell
.\.venv\Scripts\python.exe -m app.bench --assets 50000 --fields 30
.\.venv\Scripts\python.exe -m app.bench --assets 50000 --fields 30 --json
```

Der Nachweis laeuft vollstaendig offline auf synthetischen Daten und schreibt eine
temporaere SQLite-Datei mit den Produktionsmodellen. Gemessen werden Snapshot-Aufbau,
erster Tabellenblock, Blockabruf, Filter und Sortierung im effektiven Stand,
nebenlaeufiges Lesen waehrend paralleler Aenderungen, Audit-Inserts sowie Groesse und
Wachstum. `--db-path` behaelt die Datei, `--keep` die temporaere. Die Messwerte sind im
[Umsetzungsplan](plan/implementation_plan.md) dokumentiert.

## Grid-Lastnachweis (Phase 1.6.2)

```powershell
.\.venv\Scripts\python.exe -m app.bench.grid --assets 50000 --fields 30 --port 8200
```

Startet einen Prototyp unter `http://127.0.0.1:8200/bench`: AG Grid Community mit
Infinite Row Model, Blockabruf ueber `/bench/rows`, serverseitiger Filter und
serverseitige Sortierung auf dem effektiven Stand. Das Grid fuellt die verfuegbare
Hoehe; Kopfzeile und Steuerelemente liegen darueber. Die Aktionen sind Icon-Buttons mit
Tooltip und `aria-label` (Filter, Sortierung, **An Inhalt anpassen**, **An Anzeige
anpassen**), damit weitere Funktionen die Zeile nicht sprengen. Die Sortierrichtung ist
ein Umschalter aus zwei Pfeil-Icons; die aktive Richtung ist hervorgehoben und wird
zusaetzlich im Statustext genannt. Die beiden
Spaltenbreiten-Aktionen setzen die Breiten auf den Zellinhalt beziehungsweise auf die
sichtbare Breite; wird eine Spalte dabei schmaler als 80 px, meldet die Oberflaeche das
sichtbar. Farben und Kopfzeilenverlauf stammen aus `app/colors.py`. Der erste Start legt
die Datenbank unter `%TEMP%` an; weitere Starts verwenden sie wieder. Die Route ist nur
Teil des Lastnachweises, nicht der Anwendung.

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