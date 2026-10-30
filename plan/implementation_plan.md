# Umsetzungsplan: pixx.io Bulk-Editor

Stand: 29.10.2026. Zielbild im gemeinsamen Interview bestaetigt.

Dieser Plan dient als Grundlage fuer die spaetere Implementierung. Seine Ablage
ist keine Freigabe fuer Implementierung, Deployment oder Live-Schreibtests.

## 1. Ziel und Grundlagen

Eine Webanwendung zur sicheren tabellarischen Bearbeitung von pixx.io-Metadaten.
Geschrieben werden ausschliesslich ausdruecklich geaenderte Felder.

Grundlagen:

- [Fachkonzept](first_concept.md).
- Client-Abhaengigkeit: aktuelle stabile Version von
  [pixxio-client auf PyPI](https://pypi.org/project/pixxio-client/).
- Lokaler Client als ergaenzende Informationsquelle:
  `C:\Development\VS Code Projects\pixxio_client`; unveroeffentlichte Funktionen
  duerfen nicht als verfuegbar vorausgesetzt werden.
- Deployment-Vorbild: `C:\Development\VS Code Projects\pdfcrop-web`.

Die folgenden bestaetigten Festlegungen ersetzen widersprechende Annahmen des
urspruenglichen Konzepts. Dieses bleibt als fachliche Detailquelle erhalten.

## 2. Bestaetigter Umfang

### Erster Produktivmeilenstein

- Anmeldung, Rollen, Benutzer- und Profilverwaltung.
- Python-Abfragescripts mit Editor, Versionierung, Veroeffentlichung und Abfrage-Dry-Run.
- Script-Bearbeitung ausschliesslich durch vollstaendig vertrauenswuerdige Superuser.
- Abfragen ueber Collections, Verzeichnisse und File-ID-Listen.
- Grid mit Text, Zahl, Datum, Boolean, Einfachauswahl, Mehrfachauswahl und Keywords.
- Strukturierte Felder zunaechst nur lesbar.
- Massenaktionen: Setzen, Leeren, Hinzufuegen/Entfernen und Suchen/Ersetzen.
- Verpflichtender Schreib-Dry-Run mit Review und Konfliktanzeige.
- Dauerhafte Schreibauftraege, Audit und kontrollierte Wiederaufnahme.
- Undo als inverser Aenderungsvorschlag mit erneuter Pruefung.
- Automatisch gespeicherte private Arbeitsentwuerfe.

### Folgemeilensteine

1. XLSX-Export und -Import mit Drei-Wege-Abgleich.
2. Fill-down und rechteckiges Mehrzellen-Paste.
3. Erweiterungen wie Import ohne Snapshot und Fehlerdatei-Download.

Upload, Asset-Loeschung, Verschieben und pixx.io-Rechteverwaltung bleiben ausgeschlossen.

## 3. Verbindliche Qualitaetsziele

| Merkmal | Ziel |
|---|---|
| Gleichzeitig aktive Benutzer | 5 |
| Assets je geoeffnetem Arbeitsbestand | 50.000 |
| Gewaehlte Metadaten-Spalten | 30, zusaetzlich Identifikation und Vorschau |
| Erster Tabellenblock nach fertigem Snapshot | hoechstens 5 Sekunden |
| Filter, Sortierung und Seitenwechsel | p95 hoechstens 5 Sekunden |
| Bestaetigung langlaufender Auftraege | hoechstens 2 Sekunden |
| Inaktive Arbeitsentwuerfe | 30 Tage |
| Vollstaendige Aenderungswerte und Undo-Grundlage | 90 Tage |

Messungen erfolgen auf dokumentierter Referenzhardware mit repraesentativen
Feldwerten. Die vollstaendige Ladezeit aus pixx.io wird separat gemessen und angezeigt.
Ergebnismengen oberhalb der unterstuetzten Grenze werden ausdruecklich abgelehnt,
nicht still abgeschnitten.

## 4. Architektur

### Anwendung

- NiceGUI als Weboberflaeche.
- AG Grid Community ohne kostenpflichtige Erweiterungen.
- Serverseitiger Arbeitsbestand mit blockweiser Uebertragung zum Browser.
- SQLAlchemy mit Migrationen; SQLite als zu verifizierender Ausgangspunkt.
- Dauerhafte Auftragstabelle und begrenzte Hintergrundausfuehrung.
- Separater Subprozess je Script-Ausfuehrung.

Die Eignung von SQLite und der Community-Grid-Anbindung wird vor dem vollstaendigen
Ausbau nachgewiesen. Ein fehlgeschlagener Lastnachweis erfordert eine ausdrueckliche
Architekturentscheidung, keine stillschweigende Reduzierung der Anforderungen.

### Zentrale Datenobjekte

Zusaetzlich zum urspruenglichen Datenmodell:

- **Arbeitsbestand:** Eigentuemer, Profil, Abfrageversion, Parameter, Ladezustand.
- **Snapshot:** geladene Werte und Aenderungszeitpunkte je Asset.
- **ChangeSet:** ausstehende Aenderungen je Feld.
- **WritePlan:** unveraenderlicher, bestaetigbarer Schreibplan.
- **Auftragsschritt:** Ziel-IDs, Payload, Status, Job-ID und Verifikation.
- **Entwurfszustand:** Sicherungsstand, Ablaufdatum und Bearbeitungsversion.

Filter und Sortierung beruecksichtigen den effektiven Arbeitsstand einschliesslich
ausstehender Aenderungen.

## 5. Phase 0 - Dokumentation und Entwicklungsbasis

### Aufgaben

- Bestehendes Konzept mit den bestaetigten Entscheidungen abgleichen.
- DOX-Hierarchie anhand der tatsaechlich entstehenden Zustaendigkeiten pflegen.
- Projektgrundstruktur, Abhaengigkeiten und Pruefwerkzeuge festlegen.
- Immer die aktuelle stabile PyPI-Version von `pixxio-client` installieren
  beziehungsweise explizit aktualisieren; keine Vorabversionen.
- Keine internen Client-Wheels oder Installationen aus dem lokalen Nachbarprojekt verwenden.
- Client nicht in Requirements oder Lock-Snapshot auf eine Version festlegen.
- Bei Einrichtung, Wartungsupdates und neuen App-Builds den aktuellen Release
  beziehen; kein automatisches Update im laufenden App-Prozess.
- Installierte Version fuer Abnahmen dokumentieren und benoetigte Funktionen gegen
  diesen Release pruefen. Bei fehlenden Funktionen den Umsetzungspfad klaeren.

### Abschlusskriterium

Die aktuelle stabile PyPI-Version ist installiert und dokumentiert; die fuer den
naechsten Meilenstein benoetigten Funktionen sind gegen diesen Release geprueft.

## 6. Phase 1 - Machbarkeit und Lastnachweis

Diese Phase ist Voraussetzung fuer den vollstaendigen Funktionsausbau.

### 6.1 Client- und API-Verhalten pruefen

Auf ausschliesslich freigegebenen Produktiv-Test-Assets:

- Statische und dynamische Collections.
- Paging, Sichtbarkeit und archivierte Assets.
- Tatsaechliche Werteformate aller benoetigten Feldtypen.
- Schreiben mehrerer IDs mit identischem Payload.
- Entfernen von Metadatenwerten und Leeren von Standardattributen.
- Keywords und Mehrfachauswahl.
- Datumsformat und Zeitzonen.
- Job-Endzustaende, Teilfehler und verfuegbare Fehlerdetails.
- Rate-Limits und ausgeloeste Webhooks.

**Schreibschutz (Festlegung 30.10.2026):** Geschrieben wird ausschliesslich auf
Assets, die der Spike selbst auf dem Testsystem angelegt hat. Deren IDs werden in
einem lokalen Ledger protokolliert; jede Ziel-ID wird vor dem Schreiben gegen dieses
Ledger und zusaetzlich gegen die Mitgliedschaft in `PXTEST_COLLECTION_ID` geprueft.
Dateianlage und -loeschung sind nur bei `PXTEST_IS_DEV=true` erlaubt und dienen
allein der Testdatenvorbereitung. Manuell freigegebene File-IDs koennen spaeter
ergaenzt werden; eine Collection allein bleibt keine Schutzgrenze.

**Erste Befunde (Test-System `hoerl-demo.px.media`, Client 0.4.3, 30.10.2026):**

- `pageSize`: `files` bis 500, `customMetadata` bis 50, `collections` mindestens 50,
  `standardMetadata` akzeptiert gar kein `pageSize` (nicht gepaged). Der Client-Default
  100 laesst `CustomMetadata.get_all()` und damit `CustomMetadataBuilder` scheitern.
- `CustomMetadata.get_all()` liefert `editType` und Auswahloptionen erst nach
  `set_response_fields(["id", "name", "editType", "selectionOptions"])`.
- Die Einzelabfrage einer Collection liefert `isDynamic` und `filesQuantity` nicht;
  beide kommen ueber die Listenabfrage mit Response-Feldern.
- `users/current` liefert `{success, user: {id, displayName}}`.
- Der Client wiederholt GET/PUT/DELETE bei 429/503, POST nie. Fuer den Writer ist
  deshalb zu entscheiden, ob PUT-Wiederholungen unklare Ergebnisse wiederholen.
- Upload antwortet mit `{fileID, isDuplicate, storageUsage}`; `fileName` wird ohne
  Endung uebergeben (die API ergaenzt sie), und identischer Inhalt wird als Duplikat
  erkannt.
- `filesPut` beantwortet eine einzelne ID synchron ohne Job; mehrere IDs erzeugen einen
  Job (`jobType filesPut` mit `success`/`error`). `modifyDate` aendert sich durch den
  Schreibvorgang und traegt damit die Konflikterkennung.
- `filesPut` ist **nicht atomar**: enthaelt ein Request ein unbekanntes Feld, antwortet die
  API mit einem Fehler, schreibt die gueltigen Felder aber trotzdem. Der Writer muss vor
  dem Senden validieren und nach Teilfehlern ruecklesen.
- Datumsfelder: gespeichert wird `YYYY-MM-DD HH:MM:SS`. Ein Wert mit `T`-Separator wird
  akzeptiert und normalisiert, Mikrosekunden werden abgeschnitten. Abgelehnt werden ein
  Datum ohne Uhrzeit (`2026-12-31`), fehlende Sekunden (`2026-12-31 23:45`) und Werte mit
  Offset (`2026-12-31T23:45:00+02:00`) mit `no DateTime`.
- Die Testinstanz fuehrt 9 Collections (4 dynamisch, 5 statisch). Seitenabrufe liefern
  `cursor` nur auf nicht-letzten Seiten; 14 Assets wurden ueber 3 Seiten gelesen.
- Diese Instanz hat keine Custom-Felder mit `editType` `number` oder `boolean`; diese
  Typen bleiben ungeprueft.

**Noch offen in Phase 1:** archivierte Assets (im Testsystem nicht vorhanden),
Rate-Limits (kein Lasttest) und ausgeloeste Webhooks (kein Empfaenger).
- Custom-Metadaten: `replace`/`remove` funktionieren mit Feld-IDs und mit
  Optionsnamen; ein unbekanntes Feld meldet `The custom metadata field does not exist.`
- Standard-Metadaten: nur ein Teil der Felder ist editierbar. Schreibbar sind die im
  Asset gefuehrten Standardfelder (z. B. `AltTextAccessibility`, `Caption-Abstract`);
  XMP-/AO-/AI-Felder melden `does not exist or is not editable`. Die Editierbarkeit
  ist im Schema nicht erkennbar.
- Der Client-Default `pageSize=100` liess `CustomMetadata.get_all()` und
  `CustomMetadataBuilder` scheitern (`customMetadata` erlaubt 50). Das war ein
  Client-Fehler und ist in `pixxio-client 0.4.4` behoben (`_max_page_size` je Resource).
- `filesDelete`: eine ID wird synchron mit `success` beantwortet, ohne IDs; mehrere IDs
  starten einen Job, dessen `finishedJobData` `deletedFileIDs` und `notDeletedFileIDs`
  enthaelt. Seit `pixxio-client 0.4.4` liefert `File.delete_and_wait()` den Job; vorher
  fehlte der Wartehelfer und die `delete()`-Doku nannte die IDs faelschlich in der Antwort.
- Die Testcollection `chub` (id 614405567) ist statisch und enthaelt 4 Assets mit
  19 Custom- und 376 Standard-Metadatenfeldern; die Custom-Felder sind derzeit leer.

### 6.2 Grid-Prototyp

Mit synthetischen beziehungsweise bereinigten Testdaten:

- 50.000 Assets und 30 repraesentative Metadatenfelder.
- Blockweises Laden.
- Globale Sortierung und Filter.
- Aenderungen ausserhalb des sichtbaren Blocks.
- Massenaktionen auf alle gefilterten Treffer.
- Bedarfsgeladene Vorschaubilder.
- Fuenf gleichzeitig aktive Benutzer.

Nicht unterstuetzte Filter werden sichtbar abgelehnt, niemals still ignoriert.

**Ergebnis 30.10.2026** (`python -m app.bench.grid`, 50.000 Assets, 30 Metadatenspalten,
lokaler Rechner, AG Grid Community mit Infinite Row Model und 100 Zeilen je Block):

| Messung | Wert | Ziel |
|---|---|---|
| Erster Tabellenblock ab Navigation | 0,43 s | <= 5 s |
| Filter mit 5.555 Treffern | 0,39 s | <= 5 s |
| Filter plus Sortierung nach Zahlfeld | 0,44 s | <= 5 s |
| Blockabruf mit Sortierung, p95 aus 20 Abrufen | 0,25 s | <= 5 s |

Bewertung: Die Anbindung funktioniert mit der Community-Version; das Infinite Row
Model laedt Bloecke ueber einen HTTP-Endpunkt, Filter und Sortierung laufen serverseitig
auf dem effektiven Stand. Die Ziele werden deutlich erreicht.

Einschraenkungen: ein Client, keine Vorschaubilder, keine fuenf gleichzeitigen Benutzer,
Filter nur auf einer Textspalte und synthetische Werte. Aenderungen ausserhalb des
sichtbaren Blocks und Massenaktionen bleiben offen, weil sie Phase 3 voraussetzen.

### 6.3 Datenbank-Prototyp

- Snapshot-Speicherung und Wiederherstellung.
- Abfragen auf effektiven Feldwerten.
- Gleichzeitige Entwurfsaenderungen und Audit-Schreibvorgaenge.
- Speicherbedarf, Datenbankwachstum und Sperrverhalten.

**Ergebnis 30.10.2026** (`python -m app.bench --assets 50000 --fields 30`, Windows,
SQLite mit WAL, synthetische Werte):

| Messung | Wert | Ziel |
|---|---|---|
| Snapshot schreiben (50.000 Zeilen) | 2,33 s (21.500 Zeilen/s) | - |
| Erster Block (100 Zeilen) | 0,05 s | <= 5 s |
| Block 1.000 ab Zeile 25.000 | 0,14 s | <= 5 s |
| Filter auf Textfeld im effektiven Stand | 0,17 s | <= 5 s |
| Bereichsfilter plus Sortierung | 0,19 s | <= 5 s |
| Nebenlaeufiges Lesen p95 bei 4.203 parallelen Commits | 0,20 s, keine Sperrfehler | <= 5 s |
| Audit-Schreiben (50.000 Zeilen) | 0,33 s (152.000 Zeilen/s) | - |
| Datenbankgroesse | 108 MB, 2,27 kB je Asset | - |

Bewertung: SQLite traegt die vereinbarten Ziele im Prototyp mit grossem Abstand;
eine Architekturaenderung ist nicht begruendet. Der effektive Wert ist als
`CASE WHEN change.id IS NOT NULL THEN change.new_value ELSE json_extract(...) END`
modelliert, damit ein geleerter Wert nicht auf den Snapshot zurueckfaellt.

Einschraenkungen der Messung: synthetische Wertgroessen, keine JSON-Ausdrucksindizes,
WAL in der Groesse enthalten und ein Nebenlaeufigkeitsfenster von zwei Sekunden.
Speicherbedarf und Wachstum mit echten Werten und ueber 90 Tage Audit bleiben zu
messen.

### Abschlusskriterium

API-Verhalten und vereinbarte Leistungsziele sind nachgewiesen. Abweichungen werden
vor Phase 2 entschieden.

## 7. Phase 2 - Anmeldung, Profile und Scripts

### Anmeldung und Profile

- Rollen `superuser`, `editor` und `viewer` gemaess Fachkonzept.
- Profilzuordnung und Schreibfreigabe je Profil.
- Erstinstallation ohne Standardpasswort.
- Argon2id-Passworthashes.
- Login-Drosselung, Session-Ablauf und sichere Cookies.
- Serverseitige Berechtigungspruefung bei jeder relevanten Aktion.
- API-Keys verschluesselt, ausschliesslich serverseitig verfuegbar.
- Schutz des letzten aktiven Superusers.

Umgesetzt (Oktober 2026): `app/profiles.py` (Anlegen/Aendern inklusive Key-Rotation,
Verbindungstest, Admin-Audit), `app/clients.py` (`ClientFactory` je Profil mit Cache und
Invalidierung), `app/ui/` mit `/admin/profiles` und `/admin/users` sowie der CLI-Befehl
`create-profile`. Der API-Key wird beim Anlegen aus einer Umgebungsvariablen oder aus
`.env` gelesen (`--api-key-env`) und erscheint nie in Argumenten, Logs oder im Browser;
in der Oberflaeche ist das Key-Feld write-only und zeigt nur den Hint.

Die Anwendung ist oeffentlich ueber HTTPS erreichbar. Ein zweiter Faktor ist nicht
verpflichtend; das verbleibende Risiko wird dokumentiert.

### Script-System

- Editor, unveraenderliche Versionen und Veroeffentlichung.
- Nur Superuser duerfen erstellen, aendern oder unveroeffentlichte Entwuerfe testen.
- Andere Benutzer fuehren ausschliesslich veroeffentlichte Versionen aus.
- Lesende Fassade mit validierten Ergebnissen.
- Zeit-, Ausgabe-, Aufruf- und Mengenlimits.
- Protokollierung von Version, Parametern und Ergebnis.

RestrictedPython und Subprozess sind zusaetzliche Schutzmassnahmen, keine belastbare
Isolation gegenueber boesartigen Script-Autoren. Das im Fachkonzept vorgesehene
delegierbare Script-Bearbeitungsrecht wird im ersten Meilenstein nicht angeboten.

Umgesetzt (Oktober 2026): `app/scripts/` mit Vertrag (`contract.py`), Sicherheitsschicht
(`restricted.py`: AST-Pruefung plus RestrictedPython), read-only Fassade (`facade.py`),
Kindprozess (`worker.py`), Runner mit Zeitlimit (`runner.py`), Versionierung und Runs
(`service.py`) sowie vier Vorlagen (`templates.py`); Seiten `/scripts` und
`/scripts/{id}` in `app/ui/scripts.py`.

**Befunde zu Datei-Filtern (30.10.2026, geprueft gegen `hoerl-demo.px.media`):**

- Die gueltigen `filterType`-Werte und ihre Felder stehen in `openapi.json` des
  Client-Repositories (71 `FilesFilter*`-Schemas). Verknuepfungen laufen ueber
  `connectorAnd`/`connectorOr` mit `filters`, Negation ueber `inverted` auf jedem Filter.
- Live bestaetigt: `collection`, `fileName`, `files` (`fileIDs`), `searchTerm`,
  `fileExtension`, `isArchived`, Metadatenfilter (`metadataFieldText`,
  `hasMetadataField`), `connectorAnd`/`connectorOr` und `inverted`.
  Beispiel: Collection mit 4 Assets ∧ `fileName` "bmp" = 1; `isArchived` = 0, invertiert
  = 1177 (alle Assets).
- `all` hat kein `term`-Feld; ein mitgeschicktes `term` wird ignoriert. Unbekannte Felder
  werden von der API stillschweigend verworfen, deshalb prueft die Anwendung Filter
  selbst gegen die Feldtabelle.
- `includeArchived` ist im Schema vorhanden, im Testsystem aber ohne Wirkung (keine
  archivierten Assets). `includeSubdirectories` bleibt ungeprueft (keine Dateien in
  Unterverzeichnissen).
- Die `directories`-API akzeptiert `pageSize` bis 20; der Client-Default 100 liess
  `Directory.get_all()` scheitern. Behoben im Client (`_max_page_size = 20`, ab 0.4.5) und
  live geprueft (39 Verzeichnisse mit Default-Paging). Gueltige `responseFields` sind `id`,
  `createDate`, `modifyDate`, `parentID`, `name`, `quantity`, `quantityWithSubdirectories`,
  `permissions`, `hasChildren`.
- Das Testsystem fuehrt 19 Custom- und 376 Standard-Metadatenfelder; `metadata_fields`
  laedt beide vollstaendig (395 Eintraege) unabhaengig vom Zeilenlimit des Profils.

Die Fassade weicht damit bewusst vom Fachkonzept ab: `px.filters.and_/or_/not_` heissen
`connectorAnd`/`connectorOr` plus `inverted`, und Metadatenfilter erwarten ein Feld
(ID oder Name), das die Fassade vor dem Senden zu `customMetadataFieldID` bzw.
`standardMetadataFieldID` aufloest.

### Abschlusskriterium

Rollen- und Profilgrenzen sind getestet; Scripts koennen ohne direkte
Schreibmoeglichkeit Assets fuer einen Arbeitsbestand bestimmen.

## 8. Phase 3 - Arbeitsbestaende und Grid

### Aufgaben

- Schema aus Client und API ermitteln.
- Technische Feldkennungen durchgaengig verwenden.
- Feldeditoren und typspezifische Validierung implementieren.
- Texte exakt erhalten; keine automatische Leerzeichenbereinigung.
- Snapshot und Aenderungen getrennt speichern.
- Private Entwuerfe automatisch sichern und wieder oeffnen.
- Gleichzeitige Aenderungen desselben Entwurfs durch mehrere Tabs erkennen.
- Keine gemeinsame Echtzeitbearbeitung eines Entwurfs anbieten.
- Ablaufdatum anzeigen; unter sieben verbleibenden Tagen warnen.
- Nach 30 Tagen Inaktivitaet loeschen, sofern nicht bewusst verlaengert.
- Laufende Schreibauftraege von der Entwurfsbereinigung ausnehmen.

Umgesetzt (30.10.2026, Backend): `app/schema.py` (Spaltenkennungen `std:*`, `custom:<id>`,
`standard:<id>`, Auflösung von Namen, `SchemaCache` mit 15 Minuten TTL), `app/normalize.py`
(Anzeigenormalform je Feldtyp; Texte bleiben unveraendert, Datum wird zu
`YYYY-MM-DD HH:MM:SS`, Mehrfachauswahl zur Liste) und `app/workspaces.py` (Snapshot in
`workspace_asset.values_json`, ChangeSet nur fuer abweichende Zellen, effektive Seiten mit
Filter/Sortierung/`nur geänderte Zeilen`, Massenaktionen, Zielauflösung, Ablauf nach 30
Tagen, `edit_revision` fuer mehrere Tabs, `load_assets` fuer Filter- und ID-Ergebnisse).

Umgesetzt (30.10.2026, Oberflaeche): `/workspaces` laedt aus einem veroeffentlichten Script
mit Parameterformular in einen neuen Arbeitsbestand und listet offene Entwuerfe mit
Zeilen-, Aenderungs- und Ablaufinfo; `/workspaces/{id}` zeigt ein AG Grid (Infinite Row
Model, `GET /workspace/rows`) mit Editoren je Feldtyp, Zell-/Zeilenhervorhebung,
Wertfilter, `nur geaenderte Zeilen`, Sortierung, Massenwert fuer markierte/gefilterte/alle
Zeilen, Verwerfen und Schliessen. Live geprueft: 4 Assets aus Collection `chub`, Zelledit
(Revision 1), Filter (1 Treffer), Bulk-Wert (Revision 2), Verwerfen (Revision 3) und
Mehr-Tab-Warnung.

Umgesetzt (30.10.2026, Spaltenauswahl): Statt fester `COLUMNS` je Script kann die Auswahl
im Grid geaendert werden ("Spalten auswaehlen"): alle Felder des Profils in drei Gruppen,
Feldfilter, Zaehler, "Alle"/"Keine"/"Zuruecksetzen"/"Uebernehmen", Obergrenze 80 Spalten.
Die Auswahl liegt je Arbeitsbestand in `params_json["@columns"]`, wirkt auf Filter,
Sortierung und Excel-Export und ist reine Anzeige-Einstellung (keine neue Revision, Review
prueft ohne Spalteneinschraenkung). Live geprueft: Profil mit 404 Feldern (davon rund 390
Standard-Metadatenfelder), Filter "Datum" auf drei Felder, "Alle" bis zur Obergrenze mit
Hinweis auf 324 nicht gewaehlte Felder, Uebernehmen mit 80 Spalten, Zuruecksetzen auf die
Standardspalten.

### Massenaktionen

Jede Aktion verlangt eine ausdrueckliche Zielauswahl:

- Markierte Assets.
- Alle gefilterten Treffer.
- Gesamter Arbeitsbestand.

Die betroffenen IDs werden fuer die Aktion festgehalten. Anzahl und Wirkung
erscheinen vor der Uebernahme beziehungsweise im Schreibreview.

### Abschlusskriterium

Ein vollstaendiger Arbeitsbestand kann bearbeitet, geschlossen und nach App-Neustart
mit seinen Aenderungen wieder geoeffnet werden.

## 9. Phase 4 - Review und dauerhafte Schreibauftraege

### Schreibpipeline

1. ChangeSet validieren.
2. Aktuelle Werte betroffener Felder lesen.
3. Konflikte und ueberlappende App-Auftraege anzeigen.
4. Schreibplan erzeugen und dauerhaft speichern.
5. Dry Run und Review durchfuehren.
6. Erforderliche Ueberschreibbestaetigung einholen.
7. Bestaetigten Auftrag ausfuehren.
8. Ergebnisse verifizieren und protokollieren.

Aendert sich der Entwurf, verliert sein bisheriger Review die Gueltigkeit.

**Umgesetzt (30.10.2026):** `app/writeplan.py` bildet aus dem ChangeSet die Payloads
(`filesPut`-Felder, Keyword-Diff, Metadaten ueber `MetadataValueBuilder`), gruppiert
identische Payloads zu Schritten (200 IDs je Block) und speichert den Plan mit Digest,
Schritten und Payload-Hash. `app/writer.py` prueft den Entwurf gegen die API
(`review`: Existenz, `modifyDate`-Konflikte, laufende Schreibauftraege desselben Hosts),
fuehrt den Dry Run aus, schreibt live mit einem Client ohne PUT-Wiederholungen
(`ClientFactory.writer_client_for`), speichert die Job-ID vor dem Warten, liest jedes
Ergebnis zurueck und bucht es in `run`/`change_log`. Nach vollstaendigem Erfolg uebernimmt
`commit_applied` die Werte in den Snapshot und leert den ChangeSet. Die Seite
`/workspaces/{id}/review` zeigt Fehler, Hinweise und Aenderungen, verlangt bei Konflikten
eine Bestaetigung und startet Dry Run beziehungsweise Schreiben. Migration `0002` erweitert
`ChangeStatus` um `skipped` und `StepStatus` um `partial`. Live geprueft: drei eigene
Test-Assets, Bulk-Wert im Grid, Review und Dry Run (Lauf 6), Schreiben (Lauf 7, Job
30293895, Ruecklesung 3/3), externer Konflikt blockiert den Lauf ohne Bestaetigung, mit
Bestaetigung erfolgreich (Lauf 8), danach 0 Aenderungen im Entwurf.

Offene Punkte: keine; `reconcile` ist live geprueft (siehe Nachtrag Wiederanlauf).

**Nachtrag Wiederanlauf (30.10.2026):** `reconcile` ist vollstaendig und live geprueft.
Es liest die betroffenen Dateien zurueck, entscheidet je Schritt ueber
`ok`/`partial`/`unknown`, schreibt `verification_json` mit `reconciled: true`, zieht die
`change_log`-Zeilen nach, schliesst den zugehoerigen Lauf ab (Status, `finished_at`,
Statistik) und bucht bei vollstaendigem Erfolg ueber `commit_applied`. Der Laufmodus kommt
aus dem Lauf, weil ein Absturz den Plan im Zustand `draft` laesst. Erreichbar ueber
`/runs/{id}` ("Status abgleichen") bei Live-Laeufen, die nicht `ok` sind. Live geprueft:
rekonstruierter Absturz nach echtem `filesPut` (Job 30296791, Lauf 13 `running`/`planned`)
→ Abgleich meldet `ok`, bucht 2 Aenderungen und leert den ChangeSet; ohne wirksamen
Schreibvorgang (Lauf 14) bleibt es bei `unknown`/`failed`, der Entwurf behaelt die
Aenderung. Zusaetzlich belegt: ein unklarer Job-Timeout wird schon im Lauf ueber die
Ruecklesung zu `ok` aufgeloest (Lauf 12).

Ein Undo eines Statuswechsels verlangt ebenfalls einen Kommentar, weil das Undo als neue
Aenderung an `std:fileStateID` durch dieselbe Pipeline laeuft. Live geprueft: Undo zu Lauf
10 (Arbeitsbestand 8) fordert den Kommentar an, schreibt mit "Sperre aufgehoben (Undo)"
(Lauf 15) und setzt den Status zurueck.

**Nachtrag Dateistatus (30.10.2026):** `fileStateChangeComment` ist API-seitig optional;
auf dem Testsystem greift `fileStateID` ohne Kommentar. Geprueft wurden `fileStateID`
(Name→ID), `truncateFileState` (leert den Status) und eine unbekannte ID (abgelehnt mit
"The specified fileState ID does not exist"). Der Status wird aus `fileState.id` gelesen,
die Optionen kommen aus `GET /filestates`. In der Anwendung ist der Kommentar trotzdem
Pflicht: `build_preview` verlangt ihn bei jeder Aenderung an `std:fileStateID`, sendet ihn
als `fileStateChangeComment` und nimmt ihn in den Digest auf. Live geprueft: Statuswechsel
auf `gesperrt` mit Kommentar (Lauf 10, Ruecklesung 1/1, Change-Log `std:fileStateID`).

### Schreibplan und Client-Nutzung

- Nur geaenderte Felder aufnehmen.
- Identische Payloads gruppieren.
- Gruppengroesse anhand des Spikes festlegen.
- Metadaten ueber bestehende Client-Builder umwandeln.
- Job erzeugen, Job-ID speichern, anschliessend ueberwachen.
- Automatische PUT-Wiederholungen fuer den Writer deaktivieren, soweit sie unklare
  Ergebnisse blind erneut senden wuerden.

### Konfliktregeln

- Der zuletzt wirksam geschriebene Wert gewinnt.
- Erkannte Ueberschneidungen laufender App-Auftraege auf demselben pixx.io-Host
  erzeugen profiluebergreifend Warnungen, keine exklusiven Sperren.
- Im Review erkannte externe Aenderungen benoetigen ausdrueckliche Bestaetigung.
- Spaetere Abweichungen werden protokolliert, stoppen den bestaetigten Auftrag aber
  nicht automatisch.

Ohne bedingtes API-Schreiben gibt es keine atomare Ueberschreibsperre. Bei parallelen
Hintergrundjobs entspricht die wirksame Reihenfolge nicht zwingend der Klickreihenfolge.

### Fehler und Wiederanlauf

- Unabhaengige Schritte nach einzelnen fachlichen Fehlern fortsetzen.
- Systematische Fehler fuehren zu Pause.
- Unklare Schreibergebnisse zunaechst abgleichen.
- Nach Neustart bekannte Jobs erneut pruefen.
- Niemals pauschal einen unterbrochenen Auftrag erneut senden.
- Erfolg erst anhand belastbarer Job-Ergebnisse beziehungsweise Rueckleseverifikation
  feststellen.
- Nicht eindeutig zuordenbare Teilfehler als unklar ausweisen, nicht als Erfolg.

### Abschlusskriterium

Browserabbruch, App-Neustart, Timeout, Teilfehler und unbekannter Request-Ausgang sind
gezielt getestet.

**Umgesetzt (30.10.2026):** Timeout und unbekannter Request-Ausgang werden im Lauf ueber
die Ruecklesung aufgeloest (Live: Lauf 12). App-Neustart beziehungsweise Absturz wird ueber
`reconcile` behandelt: Lauf 13 (rekonstruierter Absturz nach echtem `filesPut`) wurde
abgeglichen, gebucht und abgeschlossen; Lauf 14 ohne Wirkung bleibt `unknown`/`failed`.
Teilfehler decken die Tests in `tests/test_writer.py` ab (Pause, Teilruecklesung,
abweichende Ruecklesung).

## 10. Phase 5 - Audit und Undo

### Aufgaben

- Run-Uebersicht mit Fortschritt, Fehlern und Ergebnissen.
- Feldbezogene Alt-/Neuwerte und technische Zuordnung.
- Verifizierte Erfolge von geplanten oder unklaren Aenderungen unterscheiden.
- Undo ausschliesslich aus nachweislich wirksamen Aenderungen erzeugen.
- Aktuelle Werte beim Undo gegen das damalige Schreibergebnis pruefen.
- Undo durch dieselbe Review- und Schreibpipeline fuehren.
- Vollstaendige Feldwerte nach 90 Tagen entfernen.

Eine kompakte Laufuebersicht darf anschliessend bestehen bleiben. Undo ist eine neue
Aenderung, kein atomarer Rollback.

**Umgesetzt (30.10.2026):** `app/runs.py` liefert die Laufuebersicht mit Zaehlern je
Status (`list_runs`), die Feldhistorie (`run_changes`, `undoable_changes`) und die
Undo-Vorbereitung (`prepare_undo`): nur Felder mit `ChangeStatus.OK`, aktueller Wert muss
dem damals geschriebenen Wert entsprechen, danach entsteht ein Arbeitsbestand
"Undo zu Lauf N" mit dem aktuellen Stand als Snapshot und den alten Werten im ChangeSet –
geschrieben wird ueber die bestehende Review- und Schreibpipeline. Die Seiten `/runs` und
`/runs/{id}` zeigen Laeufe, Felder und den Undo-Knopf; `purge_change_values` (90 Tage,
`python -m app purge-history` oder Schaltflaeche) entfernt alte Feldwerte und laesst die
kompakte Uebersicht stehen. Live geprueft: Undo zu Lauf 8 (Subjekt zurueck auf
"Phase4 Titel", Lauf 11, Ruecklesung 1/1); Undo zu Lauf 10 wurde korrekt abgelehnt, weil
der Status zwischenzeitlich extern geaendert wurde ("1 abweichend").

### Abschlusskriterium

Erfolgreiche und teilweise erfolgreiche Laeufe lassen sich nachvollziehen und
kontrolliert zuruecknehmen.

## 11. Phase 6 - Gestaltung und Deployment

### Meadow-Farbprofil

| Verwendung | Farbe |
|---|---|
| Primaeraktionen, Fokus, Auswahl | `#16a34a` |
| Positive Statusflaechen | `#22c55e` |
| Bildrahmen und Informationen | `#0ea5e9`, `#0891b2` |
| Tabellenrahmen und Warnungen | `#d97706`, `#f59e0b` |
| Fehler | `#dc2626` |
| Text | `#1e293b` |
| Seitenhintergrund | `#f1f5f9` |
| Kopfzeilenverlauf | `#2d5f4f` nach `#4a7c59` |

Farben werden zentral definiert. Kontrast und Fokusdarstellung werden geprueft;
Status wird zusaetzlich durch Text oder Symbole vermittelt.

### Deployment

Analog zum lokalen Projekt `pdfcrop-web`:

- Docker-Image lokal unter Windows bauen.
- Versioniert in die Forgejo-Registry uebertragen.
- VPS zieht das Image ueber Docker Compose.
- Traefik uebernimmt HTTPS und Routing.
- Persistente Daten getrennt vom Image halten.
- Secrets ausschliesslich ueber geschuetzte Betriebskonfiguration.
- Healthcheck, begrenzte Logs und kontrolliertes Herunterfahren.
- Neue Auftraege beim Herunterfahren stoppen; laufende Zustaende dauerhaft sichern.
- Migrationen und Wiederanlauf beim Update pruefen.

### Manuelle Backups

- Konsistente Sicherung von Datenbank und erforderlichen persistenten Daten.
- Verschluesselte Aufbewahrung ausserhalb des VPS.
- Master-Key und weitere notwendige Secrets getrennt sichern.
- Vor migrationspflichtigen Updates manuell sichern.
- Wiederherstellung in einer leeren Umgebung testen.
- Aufbewahrung von Backups mit der Loeschung von Feldwerten abstimmen.

Es gibt zunaechst keinen automatischen Backup-Dienst und kein zugesichertes maximales
Datenverlustfenster. Bereits in pixx.io wirksame Aenderungen verschwinden durch einen
App-Restore nicht; unklare Auftraege muessen anschliessend abgeglichen werden.

### Abschlusskriterium

Installation, Update und Wiederherstellung sind nachvollziehbar getestet; das System
ist ueber HTTPS erreichbar.

**Umgesetzt (30.10.2026):** Farben bleiben zentral in `app/colors.py` und entsprechen der
Tabelle. Fuer Text und gefuellte Schaltflaechen gibt es kontraststarke Varianten(`text_success #15803d`, `text_warning #b45309`, `text_error #b91c1c`, `text_info #0369a1`,
`action #15803d`, gedämpft `text_muted #475569`), weil die Flaechenfarben als Text nur
2.1–2.9:1 erreichen; `TEXT_STYLE`/`text_style` setzen sie, `FOCUS_CSS` liefert einen
sichtbaren Fokusrahmen. Status wird zusaetzlich immer als Text gezeigt. Tests:
`test_palette_entspricht_dem_plan`, Kontrastpruefungen fuer Status, Schaltflaechen und
Fokus.
Deployment: `Dockerfile` (python:3.14-slim, Migrationen im Image, `HEALTHCHECK` auf
`/health`), `.dockerignore`, `docker-compose.vps.yml` (Image
`git.claudiapps.de/hoerl-im/pixxio_bulkedit`, Traefik-Netz `him-net`, Host
`bulkedit.vcs1.him-tools.de`, Volume `/data`, Loggrenzen, `stop_grace_period`),
`.env.vps.example`, `push-to-forgejo.ps1` und `deploy-vps.sh` (Healthcheck-Abfrage,
optionales Backup vor Updates). Die Anwendung liefert `GET /health` (Datenbankpruefung,
Version) und beendet sich mit einem Shutdown-Protokolleintrag. Einen ersten Superuser
gibt es bewusst nicht automatisch: Er wird nach dem Deployment einmalig mit
`docker exec -it pixxio-bulkedit-vps python -m app create-superuser --username admin`
angelegt (Passwort ab 12 Zeichen, kein Default in `.env` oder Compose). Lokal geprueft:
Image
gebaut, Container startet migrationsfrei von 0 auf `0002`, Healthcheck `healthy`,
`/health` = `{"status":"ok","version":"0.1.0"}`, Compose-Konfiguration rendert die
Traefik-Regeln. Nicht lokal pruefbar: Push in die Forgejo-Registry und Deployment auf dem
VPS (Zugangsdaten).
Backups: `backup.sh` (SQLite-Backup-API im Container, `integrity_check`, OpenSSL
AES-256-CBC/PBKDF2, Schluessel in `backup.key`), `restore.sh` mit `--check` und
Volume-Ersetzung. Geprueft: Sicherung aus laufendem Container, `--check` meldet
14 Tabellen und Schema-Version 0002, Wiederherstellung in eine leere Umgebung
(neues Volume, neuer Container) inklusive Anmeldung mit dem gesicherten Benutzer.

**Betriebsnachweis (30.10.2026):** Image in die Forgejo-Registry gepusht, `deploy-vps.sh`
auf dem VPS ausgefuehrt, erster Superuser angelegt, erster `backup.sh`-Lauf erfolgreich.
Von aussen geprueft: `https://bulkedit.vcs1.him-tools.de/health` liefert
`{"status":"ok","version":"0.1.0"}`, die Anmeldeseite antwortet mit 200, `http://` leitet
mit 302 auf `https://` um, das Zertifikat ist von Let's Encrypt (`CN=bulkedit.vcs1.him-tools.de`,
gueltig bis 28.01.2027).

## 12. Produktivfreigabe

Freigabe erst nach:

- Nachweis der Last- und Reaktionsziele.
- Erfolgreichen Rollen- und Profiltests.
- Erfolgreichen Schreibtests auf freigegebenen Test-Assets.
- Pruefung aller unterstuetzten Feldtypen einschliesslich Leeren.
- Erfolgreichen Neustart-, Timeout- und Teilfehlertests.
- Nachweis von Konfliktwarnung und Ueberschreibbestaetigung.
- Erfolgreichem Undo-Test.
- Verifiziertem Backup-/Restore-Verfahren.
- Aktualisierung der direkt betroffenen Dokumentation und DOX-Vertraege.

Die Umsetzung fuehrt Unit-, Integrations-, UI- und Wiederanlauftests ein. Lasttests
veraendern keine grossen Produktivbestaende.

**Stand (30.10.2026):**

| Kriterium | Stand | Nachweis |
|---|---|---|
| Schreibtests auf eigenen Test-Assets | erfuellt | Laeufe 7, 8, 10, 11, 12, 13, 15 (Ruecklesung je 1/1 bis 3/3) |
| Neustart-, Timeout-, Teilfehler | erfuellt | Lauf 12 (Timeout ueber Ruecklesung aufgeloest), 13/14 (`reconcile`), Tests in `test_writer.py` |
| Konfliktwarnung + Bestaetigung | erfuellt | Lauf 8 (blockiert ohne, erfolgreich mit Bestaetigung) |
| Undo | erfuellt | Laeufe 11, 15; Ablehnung bei externer Aenderung (Lauf 10 vor Reset) |
| Backup/Restore | teilweise | Restore in leerer Umgebung lokal geprueft; auf dem VPS bisher nur `backup.sh` gelaufen |
| Feldtypen inklusive Leeren | teilweise | Text, Auswahl (Dateistatus) und Loeschen live; Keywords, Datum, Zahl, Mehrfachauswahl bisher nur per Test |
| Rollen- und Profiltests | teilweise | Rollen offline geprueft und betrachter angelegt; Live-Test auf dem VPS offen |
| Last- und Reaktionsziele | offen | Phase-1-Nachweise auf synthetischen Daten; Messung auf dem VPS offen |
| Doku und DOX | erfuellt | nach jeder Phase aktualisiert (AGENTS.md, README, Plan) |

Vor der Freigabe bleiben damit: Restore auf dem VPS durchspielen, die uebrigen Feldtypen
einmal live schreiben (Keywords, Datum, Zahl, Mehrfachauswahl), Rollen live pruefen und
die Lastziele auf dem Zielsystem messen.

## 13. Folgemeilenstein - Excel

- Versioniertes Format `bulkedit-xlsx/1`.
- Asset-Identifikation ausschliesslich per File-ID.
- Feldidentifikation ausschliesslich per technischem Key.
- Exportdatei und Datenbank-Snapshot verwenden denselben Stand.
- Bei offenen Aenderungen: sauberer Stand oder ausdruecklich gewaehlter unveraenderter
  Basisstand; kein impliziter Export ungeschriebener Bearbeitungen.
- Drei-Wege-Abgleich aus Exportbasis, Excel und aktuellen pixx.io-Werten.
- Import erzeugt ausschliesslich Aenderungsvorschlaege.
- Schreiben erfolgt ueber die bestehende Review-/Auftragspipeline.
- Groessen-, Zeilen- und Verarbeitungslimits.
- Keine Formeln, Makros oder Geheimnisse.
- Formel-Injection beim Export verhindern.
- Schutz gegen uebermaessig expandierende beziehungsweise manipulierte XLSX-Dateien.
- Feldbezogene Importfehler verstaendlich ausweisen.

Import ohne Snapshot und Fehlerdatei-Download folgen erst danach.

**Stand (30.10.2026): umgesetzt.**

| Punkt | Umsetzung |
|---|---|
| Format `bulkedit-xlsx/1` | Blätter `Daten`, `Felder`, `Auswahlwerte`, `Info`; Schluessel in Zeile 1, Anzeigenamen in Zeile 2, Daten ab Zeile 3, `file_id` in Spalte A, `export_id` im Blatt `Info` |
| File-ID und technischer Key | Spalte A ausschliesslich `file_id`; alle weiteren Spalten ueber `std:*`/`custom:<id>`/`standard:<id>`; Informationsspalten mit `@` |
| Gleicher Stand in Datei und Snapshot | `xlsx_export` (Revision `0003`) speichert Spalten, Wertsnapshot und gekuerzte Zellen; der Export liest nur den Snapshot |
| Keine ungeschriebenen Aenderungen | Export vermerkt offene Aenderungen (`pending_changes`, `hinweis`) und die Oberflaeche warnt; mitgeschrieben wird nichts |
| Drei-Wege-Abgleich | `xlsx.diff_rows`: Aenderung, bereits erledigt, Konflikt (uebersprungen und gemeldet), Leeren |
| Import erzeugt nur Vorschlaege | `xlsx.import_workbook` legt einen Arbeitsbestand mit ChangeSet an; geschrieben wird ueber Review, Dry Run und `execute` |
| Bestehende Pipeline | Laeufe tragen `run.source = xlsx` und `run.xlsx_export_id` (Nachweis: Laeufe 16 und 17) |
| Limits | 20 MB, entpackt 200 MB, Zeilenlimit des Profils, 32 767 Zeichen je Zelle, nur `.xlsx` |
| Keine Formeln/Makros | `vbaProject` wird abgelehnt, Formelzellen als Befund gemeldet |
| Formel-Injection | Textzellen werden mit `data_type = "s"` geschrieben und bleiben Text |
| ZIP-Schutz | Pruefung von Signatur und entpackter Groesse vor dem Lesen |
| Feldbezogene Fehler | `CellIssue` mit „Zeile · Spalte · Meldung" in Oberflaeche und Import-Ergebnis; Zellwerte werden schon beim Lesen geprueft |
| Import ohne Snapshot | Zwei-Wege-Vergleich mit ausdruecklicher Bestaetigung; leere Zellen bleiben unberuecksichtigt |
| Fehlerdatei | `xlsx.build_error_workbook`: Kopie der hochgeladenen Arbeitsmappe mit farblich markierten Problemzellen, Kommentar je Zelle, Blatt `Fehler` (Zeile · Spalte · Meldung) und Vermerk im Blatt `Info`; die Kopie bleibt nach der Korrektur importierbar |

Live-Nachweis: Export aus einem Arbeitsbestand, Aenderung von `std:subject` in der Datei,
Import mit genau einer Aenderung, Review ohne Fehler, Dry Run (Lauf 16) und Schreiben
(Lauf 17) mit Ruecklesung `ok`; ein zu alter Snapshot wurde korrekt als Konflikt gemeldet.
Fehlerdatei live geprueft: ungueltiges Datum in `Datum_Test` → Befund „Zeile 3 ·
Datum_Test · …", markierte Zelle `K3` mit Kommentar, Blatt `Fehler` mit einer Zeile; nach
Korrektur derselben Datei importierte der Lauf 2 Aenderungen ohne Befund.

## 14. Abhaengigkeiten und Reihenfolge

```text
Entwicklungsbasis mit aktuellem PyPI-Client
        |
API-Spike + Grid-/Datenbank-Lastnachweis
        |
Anmeldung, Profile und Scripts
        |
Dauerhafte Arbeitsbestaende und Grid
        |
Review und dauerhafte Schreibpipeline
        |
Audit und Undo
        |
Deployment-, Wiederherstellungs- und Produktivabnahme
        |
Excel
        |
Weitere Komfortfunktionen
```

Gestaltung, Tests und Dokumentation begleiten jede Phase. Belastbare
Aufwandsschaetzungen werden nach dem Machbarkeitsnachweis erstellt.
