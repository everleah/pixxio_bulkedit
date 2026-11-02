# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## User Preferences

- Die bestaetigte Implementierungsgrundlage liegt in `plan/implementation_plan.md`;
  sie hat bei Widerspruechen Vorrang vor dem urspruenglichen Fachkonzept.

## Child DOX Index

- `app/AGENTS.md`: Anwendungspaket (Konfiguration, Datenbank, Modelle, Rechte, Profile,
  Client-Factory, CLI, NiceGUI-Start); `app/ui/AGENTS.md`: Seiten und Zugriffsschutz.
- `plan/AGENTS.md`: Fachkonzept, bestaetigter Umsetzungsplan und deren Vorrangregeln.
- `tests/AGENTS.md`: Offline-Tests der Anwendung und der Entwicklungsbasis.
- Root-owned: `README.md`, `LICENSE`, `.gitignore`, `.gitattributes`, `.env.example`,
  `requirements*.txt`, `pyproject.toml`, `.vscode/`, `alembic.ini` und `migrations/`
  (Alembic-Umgebung und Revisionen), `docs/screenshots/` (in `README.md` verwendete
  Oberflaechenbilder mit synthetischen Demodaten) sowie die Deployment-Dateien `Dockerfile`,
  `.dockerignore`, `docker-compose.vps.yml`, `.env.vps.example`, `push-to-forgejo.ps1`,
  `deploy-vps.sh`, `backup.sh` und `restore.sh`. `.env.example` und `.env.vps.example`
  sind die einzigen Vorlagen; echte `.env`-Dateien, `backup.key` und `backups/` bleiben
  ungetrackt.

## Development Environment

- Workspace-lokale `.venv` mit CPython 3.14 verwenden, keine Nachbarprojekt-Umgebung.
- Direkte Abhaengigkeiten in `requirements.txt` und `requirements-dev.txt` pflegen;
  `requirements-dev.lock.txt` ist der gepruefte Windows-/Python-3.14-Snapshot.
- Fuer pixxio-client immer die aktuelle stabile PyPI-Version verwenden, kein internes
  Wheel und keine Installation aus dem Nachbarprojekt. Bei Einrichtung und Updates
  explizit `pip install --upgrade --no-cache-dir --index-url https://pypi.org/simple pixxio-client`
  ausfuehren. Den Client auch im Lock-Snapshot ungepinnt lassen; nach Updates Gates pruefen.
- Ruff und Pyright werden in `pyproject.toml` konfiguriert; Pylance nutzt dieselbe
  Typpruefbasis. VS Code analysiert den gesamten Workspace.
- Pflicht-Env der Anwendung sind `BULKEDIT_DB_PATH`, `BULKEDIT_MASTER_KEY` und
  `BULKEDIT_STORAGE_SECRET`; Datenbank und erster Superuser entstehen ueber
  `python -m app init-db` und `python -m app create-superuser --username ...`.
- Ein pixx.io-Profil entsteht ueber `python -m app create-profile`; der API-Key kommt aus
  einer Umgebungsvariablen oder aus `.env` (`--api-key-env`), nie aus einem Argument.
- Deployment: `.\push-to-forgejo.ps1` baut das Image und pusht es nach
  `git.claudiapps.de/hoerl-im/pixxio_bulkedit`; auf dem VPS zieht `./deploy-vps.sh` das
  Image (Traefik-Netz `him-net`, Host aus `BULKEDIT_HOST`). Shell-Skripte bleiben LF
  (`.gitattributes`, `test_shell_skripte_haben_lf`).
- Sicherungen laufen manuell: `./backup.sh` (konsistente SQLite-Kopie, `integrity_check`,
  OpenSSL AES-256 mit `backup.key`), Wiederherstellung mit `./restore.sh [--check]`.
  Master-Key und Storage-Secret werden getrennt gesichert.
- Vor Abschluss relevanter Aenderungen die in `README.md` dokumentierten Gates
  ausfuehren: `pip check`, Ruff-Lint, Ruff-Formatcheck, Pyright und pytest, jeweils
  ueber `.\.venv\Scripts\python.exe -m ...`.