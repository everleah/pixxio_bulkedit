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
- Datumsfelder akzeptieren `YYYY-MM-DD HH:MM:SS`; ein ISO-Wert mit Offset
  (`2026-12-31T23:45:00+00:00`) wird mit `no DateTime` abgelehnt. Der gespeicherte Wert
  kommt unveraendert zurueck; die Zeitzonen-Semantik des Servers bleibt offen.
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
