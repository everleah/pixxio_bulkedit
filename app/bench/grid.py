"""Grid-Prototyp der Phase 1.6.2: AG Grid mit serverseitigem Blockabruf.

Der Prototyp dient ausschliesslich dem Lastnachweis: 50.000 synthetische Assets aus
SQLite, blockweises Laden ueber das Infinite Row Model, globaler Filter und globale
Sortierung ueber einen HTTP-Endpunkt.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from nicegui import app as nicegui_app
from nicegui import ui
from sqlalchemy import Engine

from app.bench.queries import (
    filter_parameters,
    filtered_count_query,
    json_parameters,
    rows_query,
)
from app.bench.runner import existing_workspace_id, seed_database
from app.bench.synthetic import field_keys
from app.colors import PALETTE
from app.db import SessionFactory, create_session_factory, create_sqlite_engine

PAGE_ROUTE = "/bench"
ROWS_ROUTE = "/bench/rows"
DEFAULT_PORT = 8200
BLOCK_SIZE = 100
MAX_BLOCK_SIZE = 500
DEFAULT_ASSETS = 50_000
DEFAULT_FIELDS = 30


def fetch_rows(
    factory: SessionFactory,
    workspace_id: int,
    start: int,
    count: int,
    sort_field: str,
    descending: bool,
    filter_value: str,
    filter_field: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """Liest einen Block im effektiven Stand und liefert Trefferzahl dazu."""
    like = f"%{filter_value}%" if filter_value else None
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "filter": like,
        **json_parameters(sort_field),
        **filter_parameters(filter_field or sort_field),
    }
    with factory() as session:
        total = session.execute(filtered_count_query(), params).scalar_one()
        rows = (
            session.execute(
                rows_query(descending),
                {**params, "limit": count, "offset": start},
            )
            .mappings()
            .all()
        )

    payload: list[dict[str, Any]] = []
    for row in rows:
        values = json.loads(row["values_json"])
        payload.append(
            {
                "fileId": row["file_id"],
                "fileName": f"Asset {row['file_id']}.png",
                **values,
            }
        )
    return payload, int(total)


def register_rows_endpoint(engine: Engine, workspace_id: int, keys: Sequence[str]) -> None:
    factory = create_session_factory(engine)

    @nicegui_app.get(ROWS_ROUTE)
    async def rows(request: Request) -> JSONResponse:  # pyright: ignore[reportUnusedFunction]
        params = request.query_params
        start = max(0, int(params.get("start", "0")))
        count = min(MAX_BLOCK_SIZE, max(1, int(params.get("count", str(BLOCK_SIZE)))))
        sort_field = params.get("sortField") or keys[0]
        if sort_field not in keys:
            sort_field = keys[0]
        descending = (params.get("sortDir") or "") == "desc"
        filter_value = params.get("filter") or ""

        started = time.perf_counter()
        payload, total = fetch_rows(
            factory,
            workspace_id,
            start,
            count,
            sort_field,
            descending,
            filter_value,
            filter_field=keys[0],
        )
        server_ms = (time.perf_counter() - started) * 1000
        return JSONResponse(
            {
                "rows": payload,
                "rowCount": total,
                "serverMs": round(server_ms, 1),
                "startRow": start,
            }
        )


DATASOURCE_JS = """
({
  getRows: (params) => {
    const sort = (params.sortModel && params.sortModel[0]) || {};
    const query = new URLSearchParams({
      start: String(params.startRow),
      count: String(params.endRow - params.startRow),
      sortField: sort.colId || '',
      sortDir: sort.sort || '',
      filter: window.__bench.filter || '',
    });
    const started = performance.now();
    fetch('/bench/rows?' + query.toString())
      .then((response) => response.json())
      .then((data) => {
        params.successCallback(data.rows, data.rowCount);
        const entry = {
          startRow: params.startRow,
          totalMs: performance.now() - started,
          sinceNavMs: performance.now() - window.__bench.navStart,
          serverMs: data.serverMs,
          rowCount: data.rowCount,
          rows: data.rows.length,
          sortField: sort.colId || '',
          sortDir: sort.sort || '',
          filter: window.__bench.filter || '',
        };
        window.__bench.blocks.push(entry);
        window.__bench.last = entry;
      })
      .catch(() => params.failCallback());
  },
})
"""

HEAD_HTML = f"""
<style>
  body .q-page {{
    padding: 0;
  }}
  body .nicegui-content {{
    height: 100vh;
    padding: 0.5rem;
    box-sizing: border-box;
    gap: 0.5rem;
  }}
  body .bench-grid {{
    flex: 1 1 0;
    min-height: 0;
    --ag-foreground-color: {PALETTE.text};
    --ag-background-color: #ffffff;
    --ag-header-background-color: {PALETTE.page_background};
    --ag-header-foreground-color: {PALETTE.text};
    --ag-odd-row-background-color: #f8fafc;
    --ag-row-hover-color: #e6f6ec;
    --ag-selected-row-background-color: {PALETTE.surface_success};
    --ag-border-color: #cbd5e1;
    --ag-checkbox-checked-color: {PALETTE.primary};
    --ag-input-focus-border-color: {PALETTE.primary};
  }}
</style>
<script>
  window.__bench = {{
    blocks: [],
    navStart: performance.now(),
    filter: '',
    last: null,
  }};
</script>
"""

MIN_COLUMN_WIDTH = 80


def create_page(keys: Sequence[str], assets: int) -> None:
    def action_button(icon: str, label: str, handler: Callable[[], Any]) -> None:
        button = ui.button(on_click=handler, icon=icon).props("flat round dense color=primary")
        button.tooltip(label)
        button.props(f'aria-label="{label}"')

    column_defs: list[dict[str, Any]] = [
        {"field": "fileId", "headerName": "ID", "width": 110},
        {"field": "fileName", "headerName": "Datei", "width": 190},
    ]
    column_defs.extend({"field": key, "headerName": key, "width": 190} for key in keys)

    @ui.page(PAGE_ROUTE)
    def page() -> None:  # pyright: ignore[reportUnusedFunction]
        ui.colors(
            primary=PALETTE.primary,
            secondary=PALETTE.info_dark,
            negative=PALETTE.error,
            warning=PALETTE.warning,
            positive=PALETTE.success,
        )
        ui.add_head_html(HEAD_HTML)
        with (
            ui.row()
            .classes("w-full items-center gap-2 rounded p-3")
            .style(f"background: {PALETTE.header_gradient}; color: #ffffff")
        ):
            ui.label(f"Grid-Prototyp: {assets:,} Assets, {len(keys)} Metadaten-Spalten").classes(
                "text-lg font-semibold"
            )
            status = ui.label("").classes("ml-auto text-sm")

        with ui.row().classes("w-full flex-wrap items-end gap-2") as controls:
            filter_input = ui.input("Filter (enthaelt)").props("outlined dense").classes("w-56")
            sort_select = (
                ui.select(["", *keys], value="", label="Sortierspalte")
                .props("outlined dense")
                .classes("w-44")
            )
            direction: dict[str, str] = {"value": "asc"}
            with ui.button_group().props("flat"):
                ascending_button = ui.button(icon="arrow_upward").props("flat round dense")
                descending_button = ui.button(icon="arrow_downward").props("flat round dense")
            for button, label in (
                (ascending_button, "Aufsteigend sortieren"),
                (descending_button, "Absteigend sortieren"),
            ):
                button.tooltip(label)
                button.props(f'aria-label="{label}"')

        def set_direction(value: str) -> None:
            direction["value"] = value
            refresh_direction()

        def refresh_direction() -> None:
            for button, value in ((ascending_button, "asc"), (descending_button, "desc")):
                active = direction["value"] == value
                background = PALETTE.surface_success if active else "transparent"
                button.style(f"opacity: {1 if active else 0.45}; background: {background}")

        ascending_button.on("click", lambda: set_direction("asc"))
        descending_button.on("click", lambda: set_direction("desc"))
        refresh_direction()

        grid = ui.aggrid(
            {
                "columnDefs": column_defs,
                "defaultColDef": {"resizable": True, "sortable": True},
                "rowModelType": "infinite",
                "cacheBlockSize": BLOCK_SIZE,
                "maxBlocksInCache": 2,
                "rowBuffer": 5,
                "animateRows": False,
                ":datasource": DATASOURCE_JS,
            },
            auto_size_columns=False,
        ).classes("bench-grid w-full")

        async def apply_filter() -> None:
            await ui.run_javascript(
                f"window.__bench.filter = {json.dumps(filter_input.value or '')}"
            )
            await grid.run_grid_method("purgeInfiniteCache")
            status.set_text("Filter angewendet")

        async def apply_sort() -> None:
            field = sort_select.value or ""
            state = [] if not field else [{"colId": field, "sort": direction["value"]}]
            await grid.run_grid_method(
                "applyColumnState", {"state": state, "defaultState": {"sort": None}}
            )
            status.set_text(f"Sortierung: {field or 'keine'} {direction['value']}")

        async def fit_content() -> None:
            await grid.run_grid_method("autoSizeAllColumns", False)
            status.set_text("Spalten an Inhalt angepasst")

        async def fit_display() -> None:
            await grid.run_grid_method("sizeColumnsToFit")
            narrowest = await ui.run_javascript(
                "Math.round(Math.min(...Array.from("
                "document.querySelectorAll('.ag-header-cell'))"
                ".map((cell) => cell.getBoundingClientRect().width)))"
            )
            if isinstance(narrowest, int | float) and narrowest < MIN_COLUMN_WIDTH:
                status.set_text(
                    f"An Anzeige angepasst, aber {len(keys) + 2} Spalten sind nur "
                    f"{narrowest:.0f} px breit - Inhalt nicht lesbar"
                )
            else:
                status.set_text("Spalten an Anzeige angepasst")

        with controls:
            action_button("filter_alt", "Filter anwenden", apply_filter)
            action_button("sort", "Sortierung anwenden", apply_sort)
            action_button("compress", "An Inhalt anpassen", fit_content)
            action_button("fit_screen", "An Anzeige anpassen", fit_display)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.bench.grid",
        description="Grid-Lastnachweis (Phase 1.6.2)",
    )
    parser.add_argument("--assets", type=int, default=DEFAULT_ASSETS)
    parser.add_argument("--fields", type=int, default=DEFAULT_FIELDS)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db-path", default=None, help="Standard: temporaere Datei")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    db_path = (
        Path(args.db_path)
        if args.db_path
        else Path(tempfile.gettempdir()) / "bulkedit_grid.sqlite3"
    )
    workspace_id = existing_workspace_id(db_path)
    if workspace_id is None:
        print(f"Lege Benchmark-Datenbank an: {db_path} ({args.assets} Assets)")
        workspace_id, keys = seed_database(db_path, assets=args.assets, fields=args.fields)
    else:
        keys = field_keys(args.fields)
        print(f"Verwende bestehende Datenbank: {db_path}")

    engine = create_sqlite_engine(db_path)
    register_rows_endpoint(engine, workspace_id, keys)
    create_page(keys, args.assets)
    ui.run(
        port=args.port,
        show=False,
        reload=False,
        title="Grid-Prototyp",
        favicon="\N{HERB}",
    )


if __name__ == "__main__":
    main()
