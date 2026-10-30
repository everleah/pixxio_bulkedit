# Scripts

## Purpose

- Abfrage-Scripts: Vertrag (PARAMS, COLUMNS, Rueckgabe), Sicherheitsschicht,
  read-only Fassade `px`, Ausfuehrung im Kindprozess, Versionierung und Vorlagen.

## Ownership

- `contract.py`: `ParamSpec`/`ScriptResult`, Pruefung von `PARAMS`, `COLUMNS`,
  Filterbaeumen und Ergebnissen; `FILTER_TYPE_FIELDS` ist die Feldtabelle der pixx.io-API.
- `restricted.py`: `check_source` (AST-Pruefung), `compile_source` (RestrictedPython),
  Namensraum mit Builtin-Whitelist, `read_literals` (PARAMS/COLUMNS ohne Ausfuehrung),
  `execute` und Logsammler.
- `facade.py`: `Filters` (Filter-Dicts) und `Facade` (`px`): Stammdaten, `count`,
  `find_ids`, `file`, `result`, `log`; loest Metadatenfeld-Namen zu IDs auf.
- `worker.py`: Kindprozess-Einstieg; baut den Client und schreibt genau ein Ergebnis.
- `runner.py`: `ScriptRunner` (Pruefen, Parametertypen, Start mit Zeitlimit),
  `ScriptInterface` und `ScriptOutcome`.
- `service.py`: Versionen anlegen, veroeffentlichen, Vorlagen sicherstellen, Runs
  protokollieren, Rechtepruefung.
- `templates.py`: mitgelieferte Vorlagen (Collection, Verzeichnis, ID-Liste, Suche).

## Local Contracts

- `compile_restricted` blockiert keine Imports; deshalb ist `check_source` Pflicht und
  die Builtin-Whitelist in `restricted.py` abschliessend. Keine Imports, kein `open`,
  `eval`, `exec`, `getattr`, keine `_`-Attribute, keine async-Syntax.
- Scripts sehen nur `px` und ihre Parameter; niemals Client, Session oder API-Key.
  Der Client entsteht ausschliesslich im Kindprozess (`worker.py`).
- Jede Ausfuehrung laeuft in einem eigenen Prozess (`spawn`) mit Zeitlimit; bei
  Ueberschreitung wird der Prozess beendet und `timed_out` gemeldet.
- Der Start erfolgt ueber `python -m app serve`: `spawn` importiert das `__main__` des
  Elternprozesses erneut (als `__mp_main__`), deshalb darf nur `app/__main__.py` mit
  `if __name__ == "__main__"`-Schutz als Einstieg dienen.
- Filter nur ueber `FILTER_TYPE_FIELDS`: unbekannte `filterType`/Felder werden vor dem
  Senden abgelehnt. Erlaubte Verknuepfung ist `connectorAnd`/`connectorOr`, Negation
  ueber `inverted`.
- `px`-Methoden liefern einfache Dicts/Listen, begrenzt auf `profile.max_rows` und
  `MAX_CALLS` Aufrufe je Lauf.
- Gespeicherte Versionen sind unveraenderlich; jedes Speichern erzeugt eine neue Version.
  Vorlagen sind unveraenderlich und werden nur kopiert.
- Nur `can_edit_scripts` (Superuser oder Recht) darf speichern/veroeffentlichen;
  Ausfuehren veroeffentlichter Scripts ist fuer alle angemeldeten Benutzer erlaubt.
- Fehlermeldungen an die UI sind deutsch und enthalten nie den API-Key.

## Work Guidance

- Neue Fassadenmethoden zuerst hier und in `contract.FILTER_TYPE_FIELDS` ergaenzen,
  dann im Editor-Formular nichts nachziehen (PARAMS ist der Vertrag).
- Zeitlimits und Ausgabegrenzen aus `Settings` (`script_timeout_seconds`,
  `script_max_output_chars`) verwenden, nicht hart kodieren.
- Kindprozess-Ergebnisse immer im Elternprozess erneut validieren (`normalize_result`).

## Verification

- `python -m pytest -q tests/test_scripts.py` (Vertrag, Sicherheit, Fassade, Service,
  Kindprozess inklusive Zeitlimit).
- Live: `/scripts` oeffnen, Vorlage "Collection" mit `chub` im Dry Run ausfuehren und
  Protokoll sowie Filter pruefen.

## Child DOX Index

- Keine weiteren untergeordneten DOX-Dokumente.
