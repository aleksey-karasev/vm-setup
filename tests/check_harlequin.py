#!/usr/bin/env python3
"""Run with Harlequin's uv environment; exercise both databases and the TUI."""

import asyncio
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


async def check_adapter(adapter, app_type):
    connection = adapter.connect()
    try:
        connection.execute("CREATE TABLE numbers (value INTEGER)")
        connection.execute("INSERT INTO numbers VALUES (20), (22)")
        cursor = connection.execute("SELECT SUM(value) AS total FROM numbers")
        assert cursor is not None
        assert cursor.fetchone() == (42,)
    finally:
        connection.close()

    app = app_type(adapter=adapter)
    async with app.run_test(size=(120, 40)) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.connection is not None, "Harlequin did not connect"
        assert app.editor is not None, "Harlequin did not mount its SQL editor"
        cursor = app.connection.execute("SELECT SUM(value) AS total FROM numbers")
        assert cursor is not None
        assert cursor.fetchone() == (42,)
        print(f"{type(adapter).__name__}: SQL, persistence and headless TUI passed")


async def main():
    with tempfile.TemporaryDirectory(prefix="vm-setup-harlequin-") as directory, ExitStack() as paths:
        # macOS platformdirs ignores XDG_*; isolate paths before Harlequin imports them.
        for kind in ("cache", "config", "data"):
            target = Path(directory) / kind
            paths.enter_context(patch(f"platformdirs.user_{kind}_dir", return_value=str(target)))
            paths.enter_context(patch(f"platformdirs.user_{kind}_path", return_value=target))

        from harlequin.app import Harlequin
        from harlequin_duckdb import DuckDbAdapter
        from harlequin_sqlite import HarlequinSqliteAdapter

        for name, adapter_type in (("sqlite", HarlequinSqliteAdapter),
                                   ("duckdb", DuckDbAdapter)):
            adapter = adapter_type(conn_str=[str(Path(directory) / f"{name}.db")],
                                   no_init=True)
            await asyncio.wait_for(check_adapter(adapter, Harlequin), timeout=45)


if __name__ == "__main__":
    asyncio.run(main())
