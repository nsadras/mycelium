"""Consistent portable snapshots and explicit JSON exports of fresh SQLite stores."""

import json
import shutil
import sqlite3
from pathlib import Path

from mycelium.database import database, SCHEMA_VERSION


def snapshot_store(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError(f"Snapshot destination must be fresh: {destination}")
    db = database(source)
    db.publish()
    destination.mkdir(parents=True)
    try:
        target = sqlite3.connect(destination / "memory.sqlite3")
        try:
            db.connection.backup(target)
            # Rebuild files from the backed-up state, never copy a live WAL/index.
            for kind, identifier, payload in target.execute(
                "SELECT kind,id,payload FROM records WHERE kind IN ('wiki','wiki-archive')"
            ):
                folder = "wiki" if kind == "wiki" else "wiki/_archive"
                path = destination / folder / f"{identifier}.md"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.loads(payload)["content"])
        finally:
            target.close()
        copied = database(destination)
        from mycelium.store import LogStore

        logs = LogStore(destination / "logs", db=copied)
        for date in {entry.entry_id.split("#")[0] for entry in logs.list_entries(None)}:
            logs._project(date)
        copied.publish()
        copied.close()
        (destination / ".writer.lock").unlink(missing_ok=True)
        if (source / "diagnostics").exists():
            shutil.copytree(source / "diagnostics", destination / "diagnostics")
    except BaseException:
        shutil.rmtree(destination)
        raise


def export_records(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("Export destination must be fresh")
    destination.mkdir(parents=True)
    connection = sqlite3.connect(
        (source.resolve() / "memory.sqlite3").as_uri() + "?mode=ro", uri=True
    )
    try:
        connection.execute("BEGIN")
        if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise ValueError("Export requires a current SQLite store")
        for kind, identifier, payload in connection.execute(
            "SELECT kind,id,payload FROM records ORDER BY kind,id"
        ):
            path = destination / f"{kind}.jsonl"
            if not path.resolve().is_relative_to(destination.resolve()):
                raise ValueError("Invalid collection name")
            with path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {"id": identifier, "record": json.loads(payload)},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    finally:
        connection.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Export canonical records for inspection."
    )
    parser.add_argument("store", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    export_records(args.store, args.destination)


if __name__ == "__main__":
    main()
