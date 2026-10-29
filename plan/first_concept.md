# Konzept: pixx.io Bulk-Editor (NiceGUI + AG Grid)

Stand: 29.10.2026 (Rev. 3) · Basis: `pixxio_client` (Unreleased, mit `iter_all`, `update_and_wait`, Retry)

Änderungen gegenüber Rev. 2:
- Neues Kapitel 10: Excel-Export/-Import mit festem Format (`bulkedit-xlsx/1`), Identifikation
  per File-ID und Feldkennung, Drei-Wege-Abgleich, Import über dieselbe Dry-Run-/Schreib-Pipeline.
- Kapitel 11–15 entsprechend umnummeriert.

Änderungen gegenüber Rev. 1:
- Profile und Benutzer liegen in SQLite und werden von einem Superuser in der UI gepflegt.
- Abfrage-Scripts liegen versioniert in der DB und werden in der UI bearbeitet.
- Dry Run für Abfrage und Schreiben.
- Kapitel 14: theoretische Prüfung der ersten Anforderung („alle Files einer Collection“).

## 1. Ziel

Eine Webanwendung, mit der ausgewählte Assets (Files) aus pixx.io tabellarisch geladen,
im Grid editiert und **nur die geänderten Werte** zurückgeschrieben werden.

Nicht-Ziele (MVP): Upload, Löschen, Verschieben, Versionsverwaltung, Rechteverwaltung in pixx.io.

## 2. Gesamtarchitektur

```
┌──────────────────────────────── NiceGUI-App ─────────────────────────────────┐
│ Login ─► Session ─► Profilwahl ─► ClientFactory ─► pixxio Client (Server)    │
│                                                                              │
│ Admin-Bereich (Superuser)     Script-Editor          Grid        Review      │
│ Benutzer · Profile        ──► Abfrage + Dry Run ──► Editieren ─► Dry Run /   │
│                                                                  Schreiben   │
│        │                          │                    │            │        │
│        ▼                          ▼                    ▼            ▼        │
│  SQLite: user, profile,   ScriptRunner (Subprozess,  Loader     ChangeSet ─► │
│  script, script_version,  RestrictedPython, Fassade)            Writer       │
│  run, change_log                                                 (Live/Dry)  │
└──────────────────────────────────────────────────────────────────────────────┘
```

Modulstruktur:

```
app/
  main.py               # NiceGUI-Start, Routing, Auth-Middleware
  settings.py           # Bootstrap-Einstellungen aus Env (DB-Pfad, Secrets)
  db.py                 # SQLite (SQLAlchemy oder sqlite3), Migrationen
  crypto.py             # Verschlüsselung der API-Keys (Fernet)
  auth.py               # Login, Passwort-Hash, Rollen, Session
  client_factory.py     # Profil -> pixxio Client (Cache pro Profil, Invalidierung bei Änderung)
  schema.py             # Metadatenfelder -> Spaltendefinitionen
  scripts/
    runner.py           # Ausführung im Subprozess, Timeout, Ausgabe-Capture
    facade.py           # read-only Fassade "px" für Scripts
    templates.py        # mitgelieferte Script-Vorlagen
  loader.py             # Filter/IDs -> Zeilen (Snapshot)
  changes.py            # Diff, ChangeSet, Gruppierung
  writer.py             # ChangeSet -> Plan -> LiveTransport | DryRunTransport
  audit.py              # Runs, Change-Log, Undo-Export
  excel_io.py           # XLSX-Export/-Import im Format bulkedit-xlsx/1 (Kap. 10)
  ui/                   # Seiten: login, admin/users, admin/profiles, scripts, grid, runs
```

## 3. Benutzer, Profile und Konfiguration (SQLite)

### 3.1 Bootstrap (einzige Datei-/Env-Konfiguration)

Nur, was vor dem ersten Login nötig ist:

| Env-Variable                 | Zweck                                                        |
|------------------------------|--------------------------------------------------------------|
| `BULKEDIT_DB_PATH`           | Pfad der SQLite-Datei                                        |
| `BULKEDIT_MASTER_KEY`        | Fernet-Schlüssel zum Ver-/Entschlüsseln der API-Keys in der DB |
| `BULKEDIT_STORAGE_SECRET`    | Secret für NiceGUI `app.storage.user` (signierte Session)    |

Erster Superuser per CLI (kein Default-Passwort):

```
python -m app create-superuser --username admin
```

Ohne Master-Key startet die App nicht. Geht der Master-Key verloren, müssen alle
API-Keys in der UI neu eingegeben werden; die übrigen Daten bleiben nutzbar.

### 3.2 Datenmodell

```sql
CREATE TABLE app_user (
  id            INTEGER PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,              -- argon2id
  role          TEXT NOT NULL CHECK (role IN ('superuser','editor','viewer')),
  can_edit_scripts INTEGER NOT NULL DEFAULT 0,
  is_active     INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL,
  last_login_at TEXT
);

CREATE TABLE profile (
  id               INTEGER PRIMARY KEY,
  name             TEXT UNIQUE NOT NULL,
  host             TEXT NOT NULL,
  api_key_enc      BLOB NOT NULL,           -- Fernet(BULKEDIT_MASTER_KEY)
  api_key_hint     TEXT NOT NULL,           -- z. B. letzte 4 Zeichen, nur zur Anzeige
  max_retries      INTEGER NOT NULL DEFAULT 3,
  max_rows         INTEGER NOT NULL DEFAULT 5000,
  allow_write      INTEGER NOT NULL DEFAULT 1, -- z. B. Prod zunächst nur lesend
  is_active        INTEGER NOT NULL DEFAULT 1,
  last_check_at    TEXT,
  last_check_ok    INTEGER,
  last_check_user  TEXT,                    -- pixx.io-User des API-Keys (users/current)
  updated_by       INTEGER REFERENCES app_user(id),
  updated_at       TEXT NOT NULL
);

CREATE TABLE user_profile (               -- welcher Benutzer darf welches Profil nutzen
  user_id    INTEGER REFERENCES app_user(id) ON DELETE CASCADE,
  profile_id INTEGER REFERENCES profile(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, profile_id)
);
```

Scripts, Runs und Change-Log: siehe Kapitel 4.3 und 9.

### 3.3 Rollen

| Rolle      | Rechte                                                                              |
|------------|-------------------------------------------------------------------------------------|
| superuser  | Benutzer und Profile verwalten, alle Profile nutzen, alle Scripts bearbeiten, alle Runs sehen |
| editor     | zugewiesene Profile nutzen, Scripts ausführen, editieren, Excel exportieren/importieren, Dry Run, schreiben (wenn Profil `allow_write`) |
| viewer     | zugewiesene Profile nutzen, Scripts ausführen, Dry Run, Excel exportieren; kein Import, kein Schreiben |

`can_edit_scripts` ist ein eigenes Recht, weil Script-Bearbeitung serverseitige
Codeausführung bedeutet (siehe 4.4). Der Superuser hat es implizit.

### 3.4 Admin-UI (nur Superuser)

**Benutzer:** Liste, Anlegen, Rolle, Script-Recht, Profilzuordnung, Deaktivieren, Passwort zurücksetzen.
Den letzten aktiven Superuser kann man weder löschen noch herabstufen.

**Profile:**
- Felder: Name, Host, API-Key, max_retries, max_rows, allow_write, aktiv.
- Der API-Key ist **write-only**: Im Formular erscheint nur `••••abcd`. Mit „Key ersetzen“
  wird ein neuer Key eingegeben; das Klartext-Feld wird nach dem Speichern geleert.
- Button **„Verbindung testen“**: `User(client).get_current()`. Das Ergebnis (OK, pixx.io-Benutzername
  des Keys) wird in `last_check_*` gespeichert. Speichern mit ungültigem Key ist nur nach Bestätigung möglich.
- Nach dem Speichern verwirft die `ClientFactory` den gecachten Client dieses Profils.
- Änderungen an Profilen und Benutzern werden im Audit-Log protokolliert (ohne Key).

### 3.5 Login und Session

- NiceGUI-Login-Seite, `app.storage.user` für die Session, Session-Timeout, Rate-Limit beim Login.
- Nach dem Login wählt der Benutzer ein zugewiesenes Profil. Der Client wird serverseitig erzeugt:
  `Client.create_client(decrypt(api_key_enc), host, max_retries=profile.max_retries)`.
- API-Keys gelangen nie in den Browser.
- Alle Schreibvorgänge laufen mit dem API-Key des Profils. In pixx.io erscheint daher der
  API-User, nicht der App-Benutzer. Deshalb ist das App-eigene Audit-Log (Kap. 9) Pflicht.

## 4. Datenermittlung über Scripts

### 4.1 Grundidee

Eine Abfrage ist ein in der DB gespeichertes Python-Script mit festem Vertrag. Es bekommt eine
**read-only Fassade `px`** und die vom Benutzer eingegebenen Parameter. Zurück gibt es,
welche Files geladen werden sollen. Geladen und geschrieben wird immer über den regulären
Loader und Writer der App, nie im Script selbst.

### 4.2 Script-Vertrag

```python
# Parameter, aus denen die UI ein Formular erzeugt
PARAMS = {
    "collection": {"type": "str", "label": "Collection (Name oder ID)", "required": True},
    "include_archived": {"type": "bool", "label": "Archivierte einbeziehen", "default": False},
}

# Optional: Standardspalten für das Grid
COLUMNS = ["std:subject", "std:description", "custom:Kampagne"]

def query(px, params):
    ...
    return px.filters.collection(123)          # Filter-Dict  (bevorzugt)
    # oder: return [101, 102, 103]             # Liste von File-IDs
    # oder: return px.result(filter=..., columns=[...], note="...")
```

Erlaubte Rückgaben:

| Rückgabe        | Weiterverarbeitung im Loader                                                         |
|-----------------|--------------------------------------------------------------------------------------|
| Filter-Dict     | `File.iter_all(filter=..., page_size=200)`; ein Durchlauf, serverseitig gefiltert     |
| Liste von IDs   | in Blöcken zu 100–200 IDs als `{"filterType": "files", "fileIDs": [...]}` (URL-Länge) |
| `px.result(...)`| wie oben, plus Spaltenvorschlag und Hinweistext für die UI                           |

Validierung: Filter müssen ein `filterType` haben, IDs müssen positive Integer sein.
Ergebnismengen über `profile.max_rows` werden abgelehnt (Dry Run zeigt das vorher an).

### 4.3 Speicherung und Versionierung

```sql
CREATE TABLE query_script (
  id                 INTEGER PRIMARY KEY,
  name               TEXT UNIQUE NOT NULL,
  description        TEXT,
  owner_id           INTEGER REFERENCES app_user(id),
  is_shared          INTEGER NOT NULL DEFAULT 1,   -- für alle Benutzer sichtbar/ausführbar
  is_template        INTEGER NOT NULL DEFAULT 0,   -- mitgelieferte Vorlage (read-only)
  current_version_id INTEGER,                      -- veröffentlichte Version
  created_at         TEXT NOT NULL
);

CREATE TABLE query_script_version (
  id          INTEGER PRIMARY KEY,
  script_id   INTEGER NOT NULL REFERENCES query_script(id) ON DELETE CASCADE,
  version_no  INTEGER NOT NULL,
  source      TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  comment     TEXT,
  created_by  INTEGER REFERENCES app_user(id),
  created_at  TEXT NOT NULL,
  UNIQUE (script_id, version_no)
);
```

- Jedes Speichern erzeugt eine neue Version (unveränderlich). „Veröffentlichen“ setzt
  `current_version_id`. Ausgeführt wird standardmäßig die veröffentlichte Version.
- Ein Entwurf (ungespeicherter Editorinhalt) kann im Dry Run getestet werden, ohne zu speichern.
- Versionsliste mit Diff-Ansicht und „diese Version wiederherstellen“.
- Jeder Run speichert `script_version_id` und die Parameter. So ist nachvollziehbar, welche
  Abfrage zu welchen Änderungen geführt hat.

### 4.4 Ausführung und Sicherheit

Python lässt sich nicht verlässlich sandboxen. Mehrere Schutzschichten:

1. **Recht:** Nur Benutzer mit `can_edit_scripts` dürfen Scripts anlegen oder ändern;
   andere dürfen veröffentlichte Scripts nur ausführen.
2. **Übersetzung mit RestrictedPython** (`compile_restricted`), schon beim Speichern:
   kein `import`, kein `open`, `exec`, `eval`, kein Zugriff auf `_`-Attribute.
   Erlaubte Builtins: Whitelist (`len`, `range`, `sorted`, `min`, `max`, `str`, `int`, `dict`, `list`, `set`, …),
   dazu `re`, `datetime` und `json` als vorbereitete Objekte.
3. **Subprozess** pro Ausführung (`multiprocessing`, Spawn) mit Timeout (z. B. 60 s) und
   Begrenzung der Ausgabe. Der Client mit dem API-Key existiert nur im Subprozess, hinter der
   Fassade. Das Script sieht keinen Client und kein `session`.
4. **Fassade read-only:** Sie bietet ausschließlich lesende Methoden mit Mengenlimits.
5. `px.log(...)` und `print` werden gesammelt und im Dry Run angezeigt.

### 4.5 Fassade `px` (read-only)

```python
px.collection(name_or_id)          # -> dict (id, name, isDynamic, filesQuantity); Fehler bei 0 oder >1 Treffern
px.collections(search=None)        # -> list[dict]
px.directory(path_or_id)           # -> dict
px.directories(search=None)        # -> list[dict]
px.metadata_fields()               # -> list[dict] (custom + standard, id, name, editType, options)
px.count(filter)                   # -> int (quantity; pageSize=1)
px.find_ids(filter, max_items)     # -> list[int] (iter_all mit responseFields=["id"])
px.file(file_id)                   # -> dict (ausgewählte Felder)
px.filters.collection(id, include_archived=False)
px.filters.directory(id, include_subdirectories=True)
px.filters.files(ids)
px.filters.and_(*filters) / px.filters.or_(*filters) / px.filters.not_(f)
px.filters.metadata_text(field, term, exact=False) / metadata_selection(field, option)
px.result(filter=None, ids=None, columns=None, note=None)
px.log(message)
```

Die Methoden der Fassade benutzen intern `iter_all`/`get_all` des Clients und liefern
Python-Dicts (keine `_ResponseObject`s), damit RestrictedPython-Guards greifen.

### 4.6 Script-Editor (UI)

- Liste der Scripts (eigene, geteilte, Vorlagen); Suche.
- Editor: `ui.codemirror` (Python), daneben das aus `PARAMS` erzeugte Parameterformular.
- Buttons: **Prüfen** (Restricted-Compile, Vertrag), **Dry Run**, **Speichern** (neue Version),
  **Veröffentlichen**, **Ausführen** (→ Grid).
- Vorlagen werden mitgeliefert: „Collection“, „Verzeichnis“, „ID-Liste“, „Metadatenfeld leer“.

## 5. Schema: verfügbare Attribute ermitteln

Quellen:

| Quelle                                   | Inhalt                                           |
|------------------------------------------|--------------------------------------------------|
| `CustomMetadata(client).get_all()`       | id, name, editType, selectionOptions (custom)    |
| `StandardMetadata(client).get_all()`     | id, name, editType, selectionOptions (IPTC/EXIF/…) |
| `MetadataValueBuilder` / Subklassen      | Wertumwandlung je editType (Name→ID, Datum, Zahl, Bool) |
| File-Response `metadataFields`           | Map `"<fieldId>" → {name, editType, type, value, selectionTerms, isImportant}` |
| Standardattribute der File               | subject, description, rating, keywords, fileState, creator, createDate, location, fileName |

Das Schema wird pro Profil gecacht (TTL z. B. 15 min, Button „Schema neu laden“).

### Spaltenmodell

```python
@dataclass
class ColumnDef:
    key: str              # "std:subject" | "custom:12" | "standard:5"
    label: str
    source: Literal["file_attr", "custom", "standard"]
    field_id: int | None
    edit_type: str        # text, number, date, boolean, selection, multiselection, language, ...
    options: list[str]    # selection/multiselection
    editable: bool
```

In Scripts (`COLUMNS`) dürfen Felder per Name angegeben werden (`custom:Kampagne`).
Die App löst sie beim Laden in IDs auf und meldet unbekannte Namen im Dry Run.

### editType → AG-Grid-Editor

| editType         | Editor                                  | Hinweis                               |
|------------------|-----------------------------------------|---------------------------------------|
| text / none      | `agTextCellEditor` / `agLargeTextCellEditor` | lange Texte als Large-Editor     |
| number           | `agNumberCellEditor`                    |                                       |
| date             | `agDateStringCellEditor`                | Format `YYYY-MM-DD HH:MM:SS` beachten |
| boolean          | `agCheckboxCellEditor`                  |                                       |
| selection        | `agSelectCellEditor` (values = options) |                                       |
| multiselection   | Tag-/Chips-Editor (Custom) oder Komma-Text | AG Grid Community hat keinen Multi-Select |
| language         | Select mit Sprachcodes                  |                                       |
| map, focalpoint, orientation | read-only (MVP)             | strukturierte Werte                   |
| keywords (std)   | Chips/Komma-Text                        | Schreiben über keywordsToAdd/Remove   |

Filter in der Darstellung:
- Serverseitig bestimmt das Script, welche Files geladen werden.
- Clientseitig gibt es AG-Grid-Spaltenfilter, Quick-Filter und Sortierung.
- Zusätzlich die Filter „nur geänderte Zeilen“ und „nur Zeilen mit Fehlern“.

## 6. Grid (NiceGUI `ui.aggrid`)

- Eine Zeile pro File. Spalten: Vorschau (`previewFileURL` als Thumbnail), id, fileName (read-only),
  danach die gewählten Felder.
- `getRowId = id`. Das Event `cellValueChanged` ruft `ChangeSet.set(file_id, column_key, new_value)` auf.
- Geänderte Zellen werden hervorgehoben (`cellClassRules`). Rückgängig machen geht pro Zelle, Zeile oder für alles.
- Bulk-Funktionen: Wert auf markierte Zeilen setzen, Fill-down, Suchen und Ersetzen in einer Spalte, Paste aus Excel.
- Mengen bis etwa 5.000 Zeilen sind clientseitig unkritisch. Begrenzt wird über `profile.max_rows`.

## 7. Änderungserkennung (Diff)

- Beim Laden werden ein **Snapshot** (`original[file_id][column_key]` in Schreibnormalform) und
  das `modifyDate` jeder File gespeichert.
- Das `ChangeSet` hält nur Zellen mit `new != original`. Vor dem Vergleich wird normalisiert:
  Leerzeichen am Rand entfernen, `None` gleich `""`, Mehrfachauswahl als Menge.
- Wird eine Zelle auf ihren Originalwert zurückgesetzt, fällt sie aus dem ChangeSet.

## 8. Schreiben und Dry Run

### 8.1 Mapping Spalte → filesPut-Feld

| Spalten-Quelle            | filesPut-Feld                                            |
|---------------------------|----------------------------------------------------------|
| std: subject/description/creator/rating/fileStateID/createDate/location/fileName | gleichnamiges Feld (FileUpdateBuilder) |
| std: Leeren eines Felds   | `truncateSubject`, `truncateDescription`, `truncateRating`, … |
| std: keywords             | `keywordsToAdd` / `keywordsToRemove` (Diff der Mengen)  |
| custom metadata           | `metadataCustom=[{"action": "replace"/"remove", "id", "value"}]` |
| standard metadata         | `metadataStandard=[…]` (gleiches Format)                |

Die Map-Felder `metadataText`, `metadataSelection`, `metadataMultiSelectionToAdd` usw. sind in der
API als **deprecated** markiert und werden nicht verwendet. Werte werden über
`CustomMetadataBuilder`/`StandardMetadataBuilder` umgewandelt; ein leerer Wert wird zu `remove`.

### 8.2 Plan: Gruppierung

`filesPut` setzt **identische Werte für alle `ids`**. Deshalb:

1. Pro geänderter File einen Payload bilden (Dict der filesPut-Felder).
2. Payloads kanonisch serialisieren und gruppieren: Gleicher Payload ergibt eine Anfrage mit mehreren IDs.
3. Große Gruppen in Blöcke teilen (z. B. 200 IDs).

Ergebnis ist ein **WritePlan**, eine Liste von Schritten `(ids, payload)`. Dry Run und Live-Lauf
nutzen denselben Plan.

### 8.3 Dry Run

Dry Run gibt es auf zwei Ebenen. Beide laufen über denselben Code wie der echte Lauf; nur der
letzte, schreibende Schritt wird ersetzt.

**a) Abfrage-Dry-Run** (Script-Editor):
- Führt das Script aus (auch einen ungespeicherten Entwurf) und zeigt:
  - aufgelösten Filter bzw. ID-Anzahl
  - Trefferzahl über `px.count` (eine Anfrage mit `pageSize=1`)
  - geschätzte Anzahl Lade-Requests
  - erste 20 Treffer (id, fileName, Vorschau), Log-Ausgaben, Laufzeit
  - Warnungen: über `max_rows`, unbekannte Spalten in `COLUMNS`, leere Treffermenge
- Lädt das Grid nicht und schreibt nichts.

**b) Schreib-Dry-Run** (Review vor dem Schreiben):
- Baut aus dem ChangeSet den WritePlan und führt ihn mit einem `DryRunTransport` aus.
  Statt `update_and_wait` wird jeder Request protokolliert.
- Zeigt:
  - Änderungen als Tabelle *File · Feld · alt → neu*
  - die exakten filesPut-Requests (ids, Felder, `metadataCustom`-JSON) und ihre Anzahl
  - Validierungsfehler: Auswahloption unbekannt, Zahl oder Datum ungültig,
    `fileStateChangeComment` fehlt bei erzwungenem Kommentar, Feld nicht editierbar
  - Konfliktprüfung: `modifyDate` der betroffenen Files neu lesen (lesend, daher auch im Dry Run erlaubt)
- Wird als Run mit `mode = 'dry_run'` gespeichert und lässt sich als JSON exportieren.
- „Jetzt schreiben“ nutzt genau diesen Plan. Hat sich das ChangeSet seitdem geändert, wird der Dry Run erneut verlangt.

```python
class Transport(Protocol):
    def apply(self, ids: list[int], payload: dict) -> StepResult: ...

class LiveTransport:
    def apply(self, ids, payload):
        return StepResult.from_job(File(client).update_and_wait(ids=ids, timeout=900, **payload))

class DryRunTransport:
    def apply(self, ids, payload):
        self.recorded.append({"ids": ids, "payload": encode_structured_params(payload)})
        return StepResult(ok=True, simulated=True)
```

Profile mit `allow_write = 0` erlauben nur den Dry Run. Das ist sinnvoll für Produktion in der Einführungsphase.

### 8.4 Live-Lauf

- Der Writer läuft im Hintergrund (`run.io_bound`). Die UI zeigt den Fortschritt (Schritte erledigt/gesamt, Job-Status über `callback`).
- Höchstens 1–2 Schritte laufen parallel. Der Client ist mit `max_retries` konfiguriert und behandelt 429/503 mit `Retry-After`.
- Erfolgreiche Schritte werden aus dem ChangeSet entfernt und aktualisieren den Snapshot. Fehlgeschlagene bleiben markiert im Grid.
- Danach können die betroffenen Files neu geladen werden (Verifikation, neues `modifyDate`).

### 8.5 Konflikterkennung (optimistisch)

pixx.io bietet kein ETag/If-Match. Ersatz: Vor dem Schreiben (und im Dry Run) wird `modifyDate`
neu geladen, per `iter_all(filter={"filterType": "files", "fileIDs": [...]}, responseFields=["id", "modifyDate"])`.
Bei einer Abweichung kann der Benutzer überschreiben, überspringen oder neu laden.

## 9. Runs, Audit und Undo

```sql
CREATE TABLE run (
  id                INTEGER PRIMARY KEY,
  kind              TEXT NOT NULL CHECK (kind IN ('query','write')),
  mode              TEXT NOT NULL CHECK (mode IN ('dry_run','live')),
  source            TEXT NOT NULL DEFAULT 'grid' CHECK (source IN ('grid','xlsx','undo')),
  xlsx_export_id    TEXT REFERENCES xlsx_export(id),  -- bei source = 'xlsx' (Kap. 10)
  user_id           INTEGER REFERENCES app_user(id),
  profile_id        INTEGER REFERENCES profile(id),
  script_version_id INTEGER REFERENCES query_script_version(id),
  params_json       TEXT,
  plan_json         TEXT,       -- WritePlan bzw. aufgelöster Filter
  status            TEXT NOT NULL,  -- running, ok, partial, failed
  stats_json        TEXT,       -- Anzahl Files, Requests, Fehler, Dauer
  started_at        TEXT NOT NULL,
  finished_at       TEXT
);

CREATE TABLE change_log (
  id         INTEGER PRIMARY KEY,
  run_id     INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
  file_id    INTEGER NOT NULL,
  field_key  TEXT NOT NULL,
  old_value  TEXT,
  new_value  TEXT,
  status     TEXT NOT NULL,     -- planned, ok, failed, skipped_conflict
  job_id     INTEGER,
  error      TEXT
);

CREATE TABLE admin_audit (    -- Benutzer-/Profiländerungen (ohne Keys)
  id INTEGER PRIMARY KEY, user_id INTEGER, action TEXT, target TEXT, details_json TEXT, at TEXT
);
```

- Run-Übersicht: wer, wann, welches Profil, welches Script in welcher Version, Ergebnis.
- Undo: Aus einem Live-Write-Run wird ein inverses ChangeSet erzeugt. Es geht durch dieselbe
  Pipeline, also Dry Run und dann Schreiben.
- Geladene Tabelle und Änderungen lassen sich als XLSX im festen Format exportieren (Kap. 10).
  Der Change-Log eines Runs zusätzlich als CSV (nur Auswertung, nicht re-importierbar).

## 10. Excel-Export/-Import (Format `bulkedit-xlsx/1`)

Ziel: Fachabteilungen bearbeiten Daten offline in Excel. Die geänderte Datei geht über dieselbe
Pipeline zurück wie Grid-Änderungen (Diff → ChangeSet → Dry Run → Schreiben). **Ein Import
schreibt nie direkt.**

### 10.1 Grundsätze

- **Assets** werden ausschließlich über die **File-ID** identifiziert, nie über Dateinamen.
- **Attribute** werden ausschließlich über die **technische Feldkennung** identifiziert (dieselben
  Keys wie im Grid, Kap. 5): `std:<attribut>`, `custom:<fieldId>`, `standard:<fieldId>`.
  Anzeigenamen dienen nur der Lesbarkeit. Ein umbenanntes Feld bricht den Import daher nicht.
- Das Format ist versioniert. Der Import lehnt unbekannte Versionen ab.
- Die Datei ist ein Arbeitsdokument, keine Quelle für Berechtigungen. Rechte, Profil und
  Validierung prüft beim Import immer die App.

### 10.2 Aufbau der Arbeitsmappe

| Blatt          | Inhalt                                                                  | Beim Import |
|----------------|-------------------------------------------------------------------------|-------------|
| `Daten`        | eine Zeile pro File, Spalten = Felder                                   | ausgewertet |
| `Felder`       | Legende: Key, Anzeigename, Quelle, Feld-ID, editType, editierbar, Formathinweis | ignoriert |
| `Auswahlwerte` | eine Spalte pro Auswahlfeld mit den erlaubten Optionen (Quelle für Dropdowns) | ignoriert |
| `Info`         | Schlüssel/Wert-Paare zur Herkunft der Datei                             | ausgewertet |

**Blatt `Daten`:**

| Zeile | Inhalt                                                                                       |
|-------|----------------------------------------------------------------------------------------------|
| 1     | technische Keys (grau, zentral für den Import), z. B. `file_id`, `@fileName`, `std:subject`, `custom:12` |
| 2     | Anzeigenamen (fett, AutoFilter), z. B. „File-ID“, „Dateiname“, „Titel“, „Kampagne“             |
| 3 ff. | Daten                                                                                        |

Beispiel:

| file_id | @fileName   | @modifyDate         | std:subject | std:keywords      | custom:12     | custom:17 |
|---------|-------------|---------------------|-------------|-------------------|---------------|-----------|
| File-ID | Dateiname   | Geändert am         | Titel       | Schlagwörter      | Kampagne      | Freigabe bis |
| 4711    | img_001.jpg | 2026-10-20 14:03:11 | Messestand  | Messe; Stand 2026 | Herbst 2026   | 2027-03-31 |
| 4712    | img_002.jpg | 2026-10-21 09:12:45 |             | Messe             | Herbst 2026   |           |

Regeln für Spalten:
- `file_id` ist Pflicht und steht in Spalte A.
- Spalten mit Präfix `@` sind Informationsspalten (`@fileName`, `@modifyDate`, `@previewUrl`).
  Sie werden beim Import ignoriert; Änderungen daran ergeben eine Warnung.
- Read-only-Felder (z. B. `map`, `focalpoint`) werden grau hinterlegt und beim Import ignoriert.
- Spalten dürfen umsortiert oder gelöscht werden. Eine fehlende Spalte bedeutet „Feld nicht anfassen“.
- Spalten ohne Key in Zeile 1 gelten als Hilfsspalten des Benutzers und werden ignoriert (Hinweis im Dry Run).
- Ein unbekannter Key oder ein doppelter Key ist ein Fehler. Der Import bricht ab.

Regeln für Zeilen:
- Gelöschte Zeilen bedeuten „File nicht anfassen“.
- Leere Zeilen werden übersprungen.
- Doppelte File-IDs, nicht numerische IDs und IDs, die im Profil nicht sichtbar sind, sind Fehler.
  Sie werden pro Zeile gemeldet; die übrigen Zeilen bleiben verwendbar.

**Blatt `Info`** (Schlüssel in Spalte A, Wert in Spalte B):

| Schlüssel        | Beispiel                              | Prüfung beim Import                          |
|------------------|---------------------------------------|----------------------------------------------|
| `format`         | `bulkedit-xlsx`                       | muss exakt passen                            |
| `format_version` | `1`                                   | muss unterstützt sein                        |
| `export_id`      | UUID                                  | verweist auf den Snapshot in der DB (10.4)   |
| `profile`        | `Produktion`                          | Hinweis, falls abweichend                    |
| `host`           | `kunde.px.media`                      | muss zum gewählten Profil passen, sonst Abbruch |
| `exported_at`    | `2026-10-29T10:30:00Z`                | Anzeige, Alter wird als Warnung gemeldet     |
| `exported_by`    | `mmuster`                             | Anzeige                                      |
| `script`         | `Collection` v3, Parameter als JSON   | Anzeige                                      |
| `row_count`      | `1840`                                | Plausibilitätsprüfung                        |

Keine API-Keys, Passwörter oder Session-Daten in der Datei.

### 10.3 Wertformate je editType

| editType / Feld   | Excel-Zelle                                   | Hinweise                                       |
|-------------------|-----------------------------------------------|------------------------------------------------|
| text              | Text (Zellformat `@`)                         | verhindert, dass Excel „1-2“ zu einem Datum macht; max. 32.767 Zeichen |
| number            | Zahl                                          | Text, der als Zahl lesbar ist, wird akzeptiert  |
| date              | Excel-Datum (Format `JJJJ-MM-TT hh:mm:ss`)    | ISO-Text wird ebenfalls akzeptiert; Zeitzone wie pixx.io-Anzeige (Spike) |
| boolean           | `WAHR`/`FALSCH` (Excel-Boolean)               | auch `ja`/`nein`, `1`/`0`                      |
| selection         | Optionsname, Dropdown über Datenüberprüfung   | Abgleich ohne Groß-/Kleinschreibung; Umwandlung Name → ID über die Builder |
| multiselection    | Optionsnamen, getrennt durch `; `             | Reihenfolge egal (Vergleich als Menge)         |
| std:keywords      | Schlagwörter, getrennt durch `; `             | Diff ergibt `keywordsToAdd`/`keywordsToRemove` |
| std:rating        | Zahl 0–5                                      |                                                |
| std:fileState     | Statusname, Dropdown                          | ggf. Kommentar-Pflicht beachten (Kap. 8.3)     |
| language          | Sprachcode, Dropdown                          |                                                |
| map, focalpoint, orientation | nicht exportiert bzw. read-only    |                                                |

- Eine leere Zelle bedeutet „Wert leer“. Ob daraus ein Löschen wird, entscheidet der Abgleich (10.4).
- Formeln werden nicht ausgewertet. Eine Zelle mit Formel ist ein Fehler. Bei Bedarf
  „Werte einfügen“ in Excel nutzen.
- Das Trennzeichen `; ` ist fest. Optionen, die selbst `;` enthalten, meldet der Export als Warnung (Spike: kommt das vor?).

### 10.4 Abgleich beim Import (Drei-Wege-Diff)

Beim Export speichert die App einen **Snapshot** der exportierten Werte in der DB (nicht in der
Datei, dort wäre er manipulierbar):

```sql
CREATE TABLE xlsx_export (
  id            TEXT PRIMARY KEY,          -- UUID, steht im Blatt Info
  user_id       INTEGER REFERENCES app_user(id),
  profile_id    INTEGER REFERENCES profile(id),
  run_id        INTEGER REFERENCES run(id), -- Abfrage, aus der exportiert wurde
  columns_json  TEXT NOT NULL,             -- exportierte Keys inkl. editType
  snapshot_blob BLOB NOT NULL,             -- gzip(JSON): file_id -> {key: Wert, "@modifyDate": ...}
  row_count     INTEGER NOT NULL,
  created_at    TEXT NOT NULL,
  expires_at    TEXT                       -- z. B. 90 Tage, danach Aufräumen
);
```

Beim Import werden pro Zelle drei Stände verglichen (alle in Schreibnormalform, Kap. 7):

| Basis (Snapshot) | Excel (Datei) | Aktuell (pixx.io) | Ergebnis                                  |
|------------------|---------------|-------------------|-------------------------------------------|
| A                | A             | beliebig          | keine Änderung                            |
| A                | B             | A                 | Änderung A → B                            |
| A                | B             | B                 | keine Änderung (bereits erledigt)         |
| A                | B             | C                 | **Konflikt**: überschreiben / überspringen |
| A                | leer          | A                 | Feld leeren (`remove` bzw. `truncate*`)   |

Ablauf:
1. Datei hochladen (Größenlimit z. B. 20 MB). Danach wird `Info` geprüft: Format, Version, Host.
2. Die Kopfzeile von `Daten` wird gegen das aktuelle Schema geprüft (Keys vorhanden, editierbar).
3. Die Zeilen werden gelesen und pro Zelle validiert (Typ, Auswahloption existiert, Datum gültig).
4. Die aktuellen Werte der enthaltenen File-IDs werden geladen (`iter_all` mit Filter
   `{"filterType": "files", "fileIDs": [...]}` in Blöcken). Dabei fallen auch unbekannte oder
   nicht sichtbare IDs auf.
5. Aus dem Drei-Wege-Abgleich entsteht ein ChangeSet. Es wird im Grid angezeigt: geänderte
   Zellen hervorgehoben, Konflikte rot, und es kann vor dem Schreiben noch nachbearbeitet werden.
6. Danach folgt der normale Schreib-Dry-Run und das Schreiben (Kap. 8). Der Run erhält
   `source = 'xlsx'` und die `xlsx_export_id`.

**Fallback ohne Snapshot** (z. B. abgelaufener Export oder eine von Hand gebaute Datei mit
korrekter Kopfzeile) ist ein Zwei-Wege-Abgleich Excel ↔ aktuell:
- Er ist nur nach ausdrücklicher Bestätigung möglich und wird im Dry Run als Warnung angezeigt.
- Leere Zellen werden standardmäßig **ignoriert** (Option „leere Zellen leeren das Feld“ muss
  bewusst aktiviert werden). Ohne Basis lässt sich „absichtlich gelöscht“ nicht von „nie befüllt“ unterscheiden.
- Konflikte sind nicht erkennbar. Der Dry Run zeigt das deutlich an.

Damit kann eine Datei auch ohne vorherige Abfrage importiert werden: Die File-IDs in der Datei
bestimmen die Treffermenge, ein Script ist nicht nötig.

### 10.5 Export

- Quelle ist der aktuelle Grid-Stand mit der Spaltenauswahl. Wahlweise alle Zeilen oder nur die
  gefilterten bzw. markierten. Nicht gespeicherte Grid-Änderungen werden **nicht** exportiert.
  Ist das ChangeSet nicht leer, erscheint ein Hinweis, denn sonst stimmt die Basis nicht.
- Erzeugt wird die Datei mit `openpyxl`:
  - `Daten`: Fenster fixiert bei `B3`, AutoFilter auf Zeile 2, Spaltenbreiten passend
  - Datenüberprüfung (Liste) für selection, fileState und language mit Verweis auf `Auswahlwerte`
  - Kommentar an der Kopfzelle mit Formathinweis aus `Felder`
  - Blattschutz nur für Zeile 1 und `@`-Spalten, ohne Passwort. Er dient als Schutz vor
    Versehen, nicht als Sicherheit. Sortieren und Filtern bleiben erlaubt.
- Schutz vor Formel-Injection: Texte, die mit `=`, `+`, `-` oder `@` beginnen, werden explizit
  als Text geschrieben (`cell.data_type = "s"`). openpyxl würde sie sonst als Formel speichern.
- Dateiname: `<profil>_<script>_<JJJJMMTT-hhmm>.xlsx`. Der Export wird als Query-Run protokolliert.

### 10.6 Import: Technik und Sicherheit

- Gelesen wird mit `openpyxl.load_workbook(read_only=True, data_only=False)`. Formeln werden so
  erkannt und abgelehnt. `defusedxml` ist installiert, damit openpyxl gegen XML-Angriffe abgesichert ist.
- Limits: Dateigröße, maximal `profile.max_rows` Zeilen, Zeitlimit für das Parsen. Nur `.xlsx`,
  also kein `.xls` und kein `.xlsm` (Makros).
- Die hochgeladene Datei wird nach dem Import nicht dauerhaft gespeichert. Im Run stehen nur
  ihr SHA-256-Hash und der Dateiname.
- Fehlerbericht: Alle Probleme kommen als Liste *Zeile · Spalte · Meldung*. Optional lässt sich
  die Datei mit markierten Fehlerzellen herunterladen (rot plus Kommentar), damit der Benutzer in Excel korrigieren kann.
- Import ist nur für `editor`/`superuser` erlaubt. Bei Profilen mit `allow_write = 0` endet der Import im Dry Run.

### 10.7 Grenzen

- Excel ist kein Mehrbenutzer-Werkzeug. Parallele Bearbeitung derselben Files fängt nur die
  Konflikterkennung ab (10.4).
- Sehr lange Texte (> 32.767 Zeichen) sind in Excel nicht darstellbar. Solche Felder werden
  beim Export als read-only markiert und abgeschnitten, mit Warnung.
- Neue Files anlegen, Upload und Löschen geht über Excel nicht. Es werden nur bestehende Files per ID geändert.

## 11. Sicherheit

- API-Keys liegen verschlüsselt in der DB (Fernet, Master-Key aus Env), sind in der UI write-only
  und erscheinen nicht in Logs, Run-Daten oder Exporten.
- Passwörter werden mit argon2id gehasht. Login hat ein Rate-Limit, es gibt Session-Timeout und
  HTTPS über einen Reverse Proxy.
- Scripts: Recht `can_edit_scripts`, RestrictedPython, Subprozess mit Timeout, read-only Fassade (Kap. 4.4).
- Schreiben nur für `editor`/`superuser` und nur, wenn das Profil `allow_write` hat. Vorher ist der Dry Run Pflicht.
- Excel: Export ohne Secrets, Schutz vor Formel-Injection. Import nur `.xlsx` mit Größen- und
  Zeilenlimit, ohne Formeln und mit `defusedxml`; er schreibt nie direkt (Kap. 10.6).
- Die SQLite-Datei kommt ins Backup. Die Datei selbst enthält keine Klartext-Secrets.

## 12. Umsetzungsphasen

| Phase | Inhalt                                                                                     |
|-------|--------------------------------------------------------------------------------------------|
| 0     | Spike gegen das Testsystem (Kap. 13), insbesondere die Collection-Anforderung (Kap. 14)     |
| 1 MVP | DB und Bootstrap, Login, Superuser-UI für Benutzer und Profile, Script-Editor mit Versionen und Abfrage-Dry-Run, Fassade (Collection/Verzeichnis/IDs), Schema und Spaltenauswahl, Grid für text/number/date/boolean/selection, Diff, Schreib-Dry-Run, Live-Schreiben, Runs/Change-Log |
| 2     | Mehrfachauswahl und Keywords, Fill-down, Suchen/Ersetzen, Konfliktprüfung, XLSX-Export und -Import im Format `bulkedit-xlsx/1` mit Drei-Wege-Abgleich (Kap. 10), Versions-Diff im Script-Editor |
| 3     | Undo aus Runs, Import-Fallback ohne Snapshot, Fehlerdatei-Download, weitere Fassaden-Funktionen nach Bedarf |

## 13. Offene Punkte für den Spike (Testsystem)

1. Akzeptiert `GET /files` den JSON-kodierten `filter` wie dokumentiert? Gibt es Grenzen bei der URL-Länge (z. B. `files`-Filter mit vielen IDs)?
2. Wie erwartet `filesPut` mehrere `ids` (wiederholte Formularfelder oder JSON-Array)? Mit einer ID funktioniert es bereits; mehrere IDs müssen noch geprüft werden.
3. In welchem Format stehen die Werte in `metadataFields[...].value` je editType (Datum, Auswahl als Name oder ID, Mehrfachauswahl)?
4. Liefert ein fertiger Job verwertbare Fehlerdetails pro File (`finishedJobData`, `error`)?
5. Welche Rate-Limits bzw. Quoten gelten für den API-Key?
6. Wie verhält sich `replace` bei Mehrfachauswahl, und was macht `remove` ohne Wert?
7. Löst `filesPut` Webhooks aus, und stört das andere Integrationen bei Massenänderungen?
8. Für die Collection-Anforderung siehe Kap. 14.4.
9. Excel-Import: Welche Zeitzone haben Datumswerte in `metadataFields[...].value`? Kommen `;` in Auswahloptionen oder Keywords vor (Trennzeichen)?

## 14. Erste Anforderung: alle Files einer Collection (theoretische Prüfung)

### 14.1 API-Grundlage

- `GET /files` unterstützt den Filter `FilesFilterCollection`:
  `{"filterType": "collection", "collectionID": <id>, "includeArchived": false, "inverted": false}`.
- Paging: `page`/`pageSize` mit `pageSize` ≤ 500. Die Antwort enthält `quantity` (Gesamttreffer) und `files`.
- Die File-Liste enthält bereits `metadataFields`. Ein zusätzlicher Request pro File ist also nicht nötig.
- `GET /collections` (`searchTerm`, paged, `responseFields`) und `GET /collections/{id}` liefern
  u. a. `id`, `name`, `isDynamic`, `filesQuantity`.

### 14.2 Abdeckung durch den Client

| Schritt                          | Client                                                                 | Status |
|----------------------------------|------------------------------------------------------------------------|--------|
| Collection per ID                | `Collection(client).get(id)` → `.collection`                           | vorhanden |
| Collection per Name              | `Collection(client).iter_all(searchTerm=name, responseFields=[...])` + exakter Namensvergleich | vorhanden (`iter_all` neu) |
| Files mit Collection-Filter      | `File(client).iter_all(filter={...}, page_size=200)`                   | vorhanden; `filter` wird erst seit dem heutigen Fix korrekt als JSON kodiert |
| Gesamtzahl für den Dry Run       | `File(client).get(filter=..., pageSize=1).quantity`                    | vorhanden |
| Metadaten pro File               | `metadataFields` in der Liste (Standard-`responseFields` von `File`)    | vorhanden |

Hinweis: `examples/download_collection_assets.py` geht über Umwege (`previewFiles` der Collection,
Durchsuchen aller Files über `staticCollections`). Das lag sehr wahrscheinlich am früheren
Kodierungsfehler bei `filter`. Mit dem Collection-Filter wird das überflüssig.

### 14.3 Script (Vorlage „Collection“)

```python
PARAMS = {
    "collection": {"type": "str", "label": "Collection (Name oder ID)", "required": True},
    "include_archived": {"type": "bool", "label": "Archivierte einbeziehen", "default": False},
}

def query(px, params):
    col = px.collection(params["collection"])
    px.log(f"Collection '{col['name']}' (ID {col['id']}), "
           f"{col['filesQuantity']} Dateien, dynamisch: {col['isDynamic']}")
    return px.filters.collection(col["id"], include_archived=params["include_archived"])
```

Fassade (Ausschnitt):

```python
def collection(self, name_or_id):
    res = Collection(self._client)
    fields = ["id", "name", "isDynamic", "filesQuantity"]
    if isinstance(name_or_id, int) or str(name_or_id).isdigit():
        res.set_response_fields(fields)
        return to_dict(res.get(int(name_or_id)).collection)
    hits = [c for c in res.iter_all(searchTerm=name_or_id, responseFields=fields, max_items=500)
            if c.name == name_or_id]
    if len(hits) != 1:
        raise ScriptError(f"{len(hits)} Collections mit Namen '{name_or_id}' gefunden")
    return to_dict(hits[0])
```

Loader (danach, außerhalb des Scripts):

```python
seen = set()
for f in File(client).iter_all(filter=flt, page_size=200, sortBy="uploadDate",
                               sortDirection="asc", max_items=profile.max_rows + 1):
    if f.id not in seen:      # Schutz gegen Verschiebungen während des Pagings
        seen.add(f.id)
        rows.append(to_row(f))
```

### 14.4 Bewertung und Risiken

**Machbar mit dem aktuellen Client, ohne weitere Client-Änderungen.**

Aufwand für 2.000 Files: 1 Request für die Collection, 1 für den Count im Dry Run und
10 Lade-Requests mit `pageSize` 200. Die Antwort kann wegen `metadataFields` groß werden;
`pageSize` 100–200 ist ein guter Kompromiss.

| Risiko / offene Frage | Bewertung | Maßnahme |
|---|---|---|
| Filterkodierung in der Praxis | Fix ist offline getestet, live noch nicht | im Spike als Erstes prüfen |
| **Dynamische Collections** (`isDynamic`) | Ob der Collection-Filter sie auflöst, ist in der API nicht beschrieben | im Spike testen; sonst im Dry Run warnen bzw. sperren |
| Abweichung `filesQuantity` vs. `quantity` | durch Berechtigungen, archivierte Files oder Subversionen möglich | im Dry Run beide Zahlen anzeigen und Abweichung erklären |
| Archivierte Files / Subversionen | Standard: nur nicht archivierte Hauptversionen | `include_archived` als Parameter; Subversionen im MVP nicht |
| Änderungen während des Pagings | neue Uploads können Seiten verschieben | stabile Sortierung (aufsteigend), Deduplizierung über ID, `modifyDate`-Prüfung vor dem Schreiben |
| Mehrdeutige Namen | Collection-Namen sind nicht eindeutig | exakter Vergleich, bei mehreren Treffern Fehler mit Kandidatenliste; ID-Eingabe möglich |
| Rechte des API-Keys | der API-User muss Collection und Files sehen | „Verbindung testen“ und Dry Run zeigen 0 Treffer bzw. 403 klar an |
| Mengen | große Collections | `profile.max_rows`; Dry Run warnt vor dem Laden |

Spike-Checkliste für diese Anforderung:

1. Eine statische Collection mit bekannter Anzahl laden: Stimmt die Anzahl? Gibt es keine Duplikate?
2. Dasselbe mit einer dynamischen Collection.
3. Collection mit archivierten Files: Unterschied mit und ohne `includeArchived`.
4. Collection mit mehr als 500 Files: Paging über mehrere Seiten.
5. Mit dem Profil-Key eines eingeschränkten API-Users prüfen, wie sich Rechte auf die Trefferzahl auswirken.

## 15. Abhängigkeiten

- `pixxio_client` (≥ aktueller Unreleased-Stand), `nicegui`, `sqlalchemy` (oder `sqlite3`),
  `cryptography` (Fernet), `argon2-cffi`, `RestrictedPython`, `openpyxl` und `defusedxml` (Excel, Kap. 10).
