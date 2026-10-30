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

## Arbeitsbestände und Grid

`/workspaces` lädt die Assets eines veröffentlichten Scripts (Parameterformular aus
`PARAMS`) in einen Arbeitsbestand: Snapshot der geladenen Werte plus ChangeSet der
Änderungen, beides in der Anwendungsdatenbank. `/workspaces/{id}` zeigt das Grid.

- Spalten kommen aus `COLUMNS` des Scripts (`std:subject`, `custom:Kampagne`,
  `standard:DateSent`); ohne `COLUMNS` erscheinen Dateiname, Titel, Beschreibung und bis
  zu zwölf Custom-Felder.
- „Spalten auswählen" (Icon `view_column`) öffnet die Spaltenauswahl: alle Felder des
  Profils in drei Gruppen (Standardattribute, eigene Metadatenfelder,
  Standard-Metadatenfelder), mit Feldfilter, Zähler und den Schaltflächen „Alle",
  „Keine", „Zurücksetzen" und „Übernehmen". Die Auswahl gilt nur für diesen
  Arbeitsbestand, wird in `params_json` gespeichert (höchstens 80 Spalten) und wirkt
  auch auf Filter, Sortierung und Excel-Export. „Zurücksetzen" stellt die
  Script- beziehungsweise Standardspalten wieder her.

  > Hinweis: Ein Profil kann sehr viele Standard-Metadatenfelder mitbringen (im
  > Testsystem rund 390). Ohne Feldfilter ist die Liste lang; „Alle" wählt dann nur bis
  > zur Obergrenze und meldet, wie viele Felder übrig blieben.
- Editoren je Typ: Text, Zahl, Datum (`JJJJ-MM-TT HH:MM:SS`), Wahrheitswert,
  Auswahlliste; `map`/`focalpoint`/`orientation` und `std:fileName` sind nur lesbar.
- Texte werden exakt gespeichert (kein Trimmen). Geänderte Zellen sind grün markiert,
  betroffene Zeilen tragen eine Markierung am linken Rand.
- Toolbar: Wertfilter auf einer Spalte, „nur geänderte Zeilen", Sortierung auf- und
  absteigend, Spalten an Inhalt/Anzeige anpassen, Massenwert für markierte/gefilterte/
  alle Zeilen, Änderungen verwerfen, Arbeitsbestand schließen.
- `GET /workspace/rows` liefert den effektiven Stand (ChangeSet vor Snapshot) mit
  Trefferzahl und Revision; `GET /workspace/changes` die geänderten Zellen je Asset.
- Jede Änderung erhöht `edit_revision`. Sieht ein Tab eine neuere Revision, erscheint
  der Hinweis „in einem anderen Tab geändert"; Schreibversuche mit veralteter Revision
  werden abgelehnt.
- Entwürfe laufen nach 30 Tagen Inaktivität ab; ab sieben Resttagen warnt die Liste.
  Schließen entfernt den Arbeitsbestand aus der Liste, Löschen entfernt ihn ganz.

## Review und Schreiben

`/workspaces/{id}/review` zeigt jede geplante Feldänderung (Datei, Feld, alt → neu) und
schreibt erst nach Dry Run und Bestätigung.

- Geschrieben werden ausschließlich geänderte Felder; identische Payloads werden
  gruppiert (ein `filesPut` je Payload und Block von 200 IDs).
- Der Plan ist unveränderlich und über einen Digest an den Entwurf gebunden. Ändert sich
  der Entwurf nach dem Review, blockiert der Lauf und verlangt einen neuen Dry Run.
- Externe Änderungen erkennt der Review am `modifyDate` des Snapshots; sie verlangen die
  ausdrückliche Bestätigung „Externe Änderungen überschreiben". Laufende Schreibaufträge
  auf demselben Host werden profilübergreifend als Hinweis gemeldet.
- Der Writer nutzt einen Client ohne automatische PUT-Wiederholungen, speichert die
  Job-ID vor dem Warten und liest jedes Ergebnis zurück. Unklare Ausgänge werden als
  „unklar" ausgewiesen und nie blind wiederholt; Autorisierungsfehler pausieren den Rest
  des Auftrags.
- Nach vollständigem Erfolg wandern die geschriebenen Werte in den Snapshot und
  verschwinden aus dem Entwurf; `run` und `change_log` bleiben als Protokoll (Grundlage
  für Audit und Undo).
- Der Dateistatus (`std:fileStateID`) wird als Auswahlliste angeboten; ein Statuswechsel
  verlangt im Review einen Kommentar, der als `fileStateChangeComment` mitgeschrieben wird.

## Läufe, Audit und Undo

`/runs` listet alle Läufe mit Status und Zählern je Feld (ok, geplant, unklar,
fehlgeschlagen, übersprungen); `/runs/{id}` zeigt jede Feldübernahme mit Alt-/Neu-Wert,
Status und Fehlertext.

- Grundlage ist das Change-Log: `run`, `change_log` mit Datei, Feld, Alt-/Neu-Wert,
  Status, Job-ID und Fehler.
- „Undo vorbereiten“ nimmt nur nachweislich wirksame Felder (`ok`) zurück. Vorher wird der
  aktuelle Wert gegen den damals geschriebenen Wert geprüft; abweichende Felder werden
  übersprungen und gemeldet. Fehlt eine Datei oder ist kein Feld mehr zurücknehmbar,
  bricht die Vorbereitung ab.
- Das Undo ist eine neue Änderung: Es entsteht ein Arbeitsbestand „Undo zu Lauf N“ mit dem
  aktuellen Stand als Snapshot und den alten Werten im ChangeSet; geschrieben wird über
  dieselbe Review- und Schreibpipeline. Kein atomarer Rollback.
- Feldwerte älter als 90 Tage werden entfernt (`python -m app purge-history` oder die
  Schaltfläche in `/runs`); die kompakte Laufübersicht bleibt erhalten.
- „Status abgleichen“ bei Läufen, die nicht sauber mit `ok` endeten: Der Writer liest die
  betroffenen Dateien zurück und entscheidet neu — bestätigte Werte gelten als Erfolg und
  werden aus dem Entwurf gebucht, unklare bleiben unklar. Es wird nie erneut gesendet.

## Excel-Export und -Import

Der Weg über Excel nutzt dasselbe Sicherheitsnetz wie das Grid: exportieren, in Excel
bearbeiten, importieren, prüfen (Review/Dry Run) und erst dann schreiben.

- **Export** in der Werkzeugleiste des Grids (Icon „Excel-Export"): exportiert die
  markierten Zeilen, sonst die gefilterten Zeilen, sonst den ganzen Arbeitsbestand.
  Grundlage ist immer der gespeicherte Snapshot — ungeschriebene Grid-Änderungen werden
  nie mitgeschrieben, sondern nur im Blatt `Info` vermerkt.
- Die Arbeitsmappe hat vier Blätter: `Daten` (Zeile 1 technische Schlüssel, Zeile 2
  Anzeigenamen mit AutoFilter, Daten ab Zeile 3, `file_id` in Spalte A), `Felder`
  (Legende je Spalte), `Auswahlwerte` (Quelle der Auswahllisten) und `Info`
  (Format, Version, `export_id`, Profil, Host, Zeitpunkt, Anzahl Zeilen).
- Nur schreibbare Spalten werden importiert. Informationsspalten (`@std:fileName`,
  `@modifyDate`, Karten/Fokuspunkt/Ausrichtung) tragen ein `@` und bleiben unberücksichtigt.
  Mehrfachwerte werden mit `;` getrennt; Text mit führendem `=` bleibt Text.
- **Import** über `/workspaces` (Icon „Excel importieren"): Profil wählen, Datei
  hochladen, Zusammenfassung und Zellbefunde („Zeile · Spalte · Meldung") prüfen,
  importieren. Der Import legt einen neuen Arbeitsbestand an und führt direkt in dessen
  Review.
- Übernommen werden nur Zellen, die sich gegenüber dem Export geändert haben
  (Drei-Wege-Abgleich aus Exportbasis, Excel und aktuellem pixx.io-Stand). Bereits
  erledigte Zellen werden still übersprungen, zwischenzeitlich extern geänderte Zellen
  gemeldet und nicht überschrieben.
- Ohne Exportbasis (Snapshot abgelaufen oder fremde Datei) ist nur ein Zwei-Wege-Vergleich
  möglich: leere Zellen bleiben dann unberücksichtigt, und die Oberfläche verlangt eine
  ausdrückliche Bestätigung.
- Beanstandete Zellen lassen sich als **Fehlerdatei** herunterladen: eine Kopie der
  hochgeladenen Arbeitsmappe, in der jede Problemzelle farbig markiert und mit einem
  Kommentar versehen ist; zusätzlich listet das Blatt `Fehler` alle Befunde als
  „Zeile · Spalte · Meldung". Die Kopie bleibt importierbar — markierte Zellen in Excel
  korrigieren und dieselbe Datei erneut hochladen.
- Grenzen: nur `.xlsx` (keine Makros, keine Formeln), 20 MB Dateigröße, Zeilenlimit des
  Profils, Zelltexte bis 32 767 Zeichen (längere werden gekürzt und als solche behandelt).
- Export-Snapshots liegen in `xlsx_export` und werden nach 90 Tagen mit
  `python -m app purge-history` entfernt. Läufe aus einem Import tragen die Quelle `xlsx`.

## Oberfläche und Sprache

Die Oberfläche ist zweisprachig (Deutsch und Englisch). Deutsch ist die Quelle: alle
sichtbaren Texte stehen im Code, englische Übersetzungen in `app/i18n.py`. Gewechselt
wird die Sprache in der Kopfzeile über `DE`/`EN`; sie gilt für die Sitzung.

- Aktionen sind Icon-Buttons mit Tooltip (z. B. Download-Symbol für „Arbeitsbestand
  laden"), damit weitere Funktionen die Werkzeugleiste nicht sprengen.
- Texte enthalten echte Umlaute und werden nie automatisch getrimmt.
- Script-Parameter (`PARAMS`) und Metadatenwerte sind Daten und bleiben unübersetzt.
- `tests/test_i18n.py` prüft, dass jeder verwendete Text eine englische Übersetzung hat.

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

## Deployment (Docker, Forgejo, Traefik)

Das Image enthält Anwendung, Migrationen und Abhängigkeiten; beim Start läuft
`alembic upgrade head`, danach startet `python -m app serve`.

```powershell
.\push-to-forgejo.ps1 -Tag 0.2.0        # bauen und nach git.claudiapps.de pushen
```

Auf dem VPS liegen `docker-compose.vps.yml`, `deploy-vps.sh`, `backup.sh`, `restore.sh`
und eine `.env` (Vorlage: `.env.vps.example`) in einem Ordner:

```bash
bash deploy-vps.sh            # Image ziehen, Container neu starten, Healthcheck abwarten
bash deploy-vps.sh --backup   # zusätzlich vorher sichern (Empfehlung bei Updates)
```

- Traefik übernimmt HTTPS und Routing über das externe Netz `him-net`
  (`BULKEDIT_HOST=bulkedit.vcs1.him-tools.de`), Zertifikate über `letsencrypt`.
- Persistente Daten liegen in den Volumes `bulkedit_data` (`/data`) und
  `bulkedit_nicegui` (`/app/.nicegui`), nicht im Image.
- Secrets kommen ausschließlich aus der `.env` (`BULKEDIT_MASTER_KEY`,
  `BULKEDIT_STORAGE_SECRET`); ohne gültige Konfiguration startet die Anwendung nicht.
- Healthcheck: `GET /health` prüft die Datenbank und liefert Version und Status;
  Docker und Traefik nutzen ihn. Logs sind auf 10 MB × 5 Dateien begrenzt.
- Herunterfahren: `stop_grace_period` 30 s; laufende Schreibvorgänge werden nicht neu
  gesendet — nach dem Start in `/runs` „Status abgleichen“ ausführen.

### Erster Superuser (Pflicht, kein Standardpasswort)

Die Anwendung bringt bewusst keinen vorgefertigten Benutzer mit: Ohne angelegten
Superuser kann sich niemand anmelden. Nach dem ersten `bash deploy-vps.sh` einmalig im
Container anlegen (Passwort mindestens 12 Zeichen):

```bash
docker exec -it pixxio-bulkedit-vps python -m app create-superuser --username admin
# fragt "Passwort:" und "Passwort wiederholen:" ab
```

Ohne TTY (z. B. aus einem Skript) das Passwort über stdin übergeben, damit es nicht in
der Shell-Historie oder in `docker inspect` landet:

```bash
read -rsp "Passwort: " PW; echo
printf '%s\n' "$PW" | docker exec -i pixxio-bulkedit-vps python -m app create-superuser \
    --username admin --password-stdin
unset PW
```

Ein erneuter Aufruf mit demselben Namen setzt das Passwort zurück und stellt die
Superuser-Rolle wieder her. Prozess umgebungsvariablen wie `BULKEDIT_MASTER_KEY` gelten
im Container automatisch, weil `docker exec` die Compose-Umgebung des Containers nutzt —
die Datenbank liegt dabei unter `/data/bulkedit.sqlite3`. Weitere Benutzer legt der
Superuser danach in der Oberfläche unter „Benutzer“ an.

## Sicherung und Wiederherstellung

Es gibt keinen automatischen Backup-Dienst. Gesichert wird manuell und verschlüsselt:

```bash
openssl rand -base64 48 > backup.key && chmod 600 backup.key   # einmal, getrennt aufbewahren
bash backup.sh /pfad/ausserhalb-des-vps                        # konsistente Kopie + Verschlüsselung
bash restore.sh --check                                        # neueste Sicherung prüfen
bash restore.sh --check backups/bulkedit-20261030T120000Z.tar.gz.enc
bash restore.sh backups/bulkedit-20261030T120000Z.tar.gz.enc   # Container stoppen, Daten ersetzen
```

Ohne Pfadangabe nimmt `restore.sh` die neueste Sicherung aus `./backups` (`BACKUP_DIR`
überschreibt den Ordner). Die Skripte sind mit `bash …` aufrufbar und brauchen kein
Ausführungsbit.

- `backup.sh` erzeugt die Datenbankkopie über die SQLite-Backup-API im Container (auch bei
  laufender Anwendung konsistent), prüft `PRAGMA integrity_check` und verschlüsselt das
  Archiv mit OpenSSL (AES-256-CBC, PBKDF2).
- `BULKEDIT_MASTER_KEY` und `BULKEDIT_STORAGE_SECRET` gehören **nicht** ins Archiv und
  werden getrennt aufbewahrt; ohne Master-Key sind gespeicherte API-Keys unlesbar.
- Vor migrationspflichtigen Updates sichern (`bash deploy-vps.sh --backup`).
- Wiederherstellung wurde in einer leeren Umgebung getestet: neues Volume, Archiv
  einspielen, Anmeldung mit dem gesicherten Benutzer.
- Bereits in pixx.io wirksame Änderungen verschwinden durch einen Restore nicht;
  unklare Aufträge nach dem Restore über `/runs` abgleichen.
- Aufbewahrung abstimmen: Feldwerte verschwinden nach 90 Tagen
  (`python -m app purge-history`), Sicherungen entsprechend länger oder kürzer halten.

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
Verschluesselung, Rollen und Rechte, Datenbank und Migrationen, Kommandozeile,
Farbkontrast und Deployment-Artefakte; Script-Isolation, Lastziele und Live-API bleiben
offen.