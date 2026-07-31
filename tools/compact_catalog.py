"""Build the small runtime catalogue used by public releases.

The extraction database contains several duplicated PDF/OCR search tables.  The
application only needs the structured records and the ``chunks`` table at
runtime; title/scope indexes keep the LIKE fallback bounded when the optional
large FTS5 index is omitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path


REQUIRED_TABLES = (
    "quota_items",
    "bill_items",
    "bill_quota_links",
    "chunks",
)
OPTIONAL_TABLES = (
    "consumptions",
    "materials",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _copy_table(source: sqlite3.Connection, target: sqlite3.Connection, table: str) -> int:
    schema = source.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not schema or not schema[0]:
        raise RuntimeError(f"source catalogue is missing table: {table}")
    target.execute(schema[0])
    columns = [row[1] for row in target.execute(f'PRAGMA table_info("{table}")')]
    column_sql = ",".join(f'"{column}"' for column in columns)
    placeholders = ",".join("?" for _ in columns)
    insert_sql = f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})'
    cursor = source.execute(f'SELECT {column_sql} FROM "{table}"')
    copied = 0
    while True:
        rows = cursor.fetchmany(2_000)
        if not rows:
            break
        target.executemany(insert_sql, rows)
        copied += len(rows)
    return copied


def build_compact_catalog(source_path: Path, output_path: Path) -> dict[str, object]:
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    if source_path == output_path:
        raise ValueError("source and output catalogue must be different files")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    if temporary.exists():
        temporary.unlink()

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    target = sqlite3.connect(temporary)
    try:
        target.execute("PRAGMA journal_mode=OFF")
        target.execute("PRAGMA synchronous=OFF")
        target.execute("PRAGMA temp_store=MEMORY")
        target.execute("PRAGMA cache_size=-262144")
        present = {
            str(row[0])
            for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = set(REQUIRED_TABLES) - present
        if missing:
            raise RuntimeError("source catalogue is missing tables: " + ", ".join(sorted(missing)))
        tables = (*REQUIRED_TABLES, *(table for table in OPTIONAL_TABLES if table in present))
        counts = {table: _copy_table(source, target, table) for table in tables}
        placeholders = ",".join("?" for _ in tables)
        for (index_sql,) in source.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL "
            f"AND tbl_name IN ({placeholders})",
            tables,
        ):
            target.execute(index_sql)
        target.execute(
            "CREATE INDEX idx_chunks_scope_title "
            "ON chunks(chunk_type, edition, discipline, title)"
        )
        user_version = int(source.execute("PRAGMA user_version").fetchone()[0])
        application_id = int(source.execute("PRAGMA application_id").fetchone()[0])
        target.execute(f"PRAGMA user_version={user_version}")
        target.execute(f"PRAGMA application_id={application_id}")
        target.commit()
        target.execute("VACUUM")
        target.commit()
        quick_check = str(target.execute("PRAGMA quick_check").fetchone()[0])
        if quick_check != "ok":
            raise RuntimeError(f"compact catalogue quick_check failed: {quick_check}")
    finally:
        target.close()
        source.close()

    os.replace(temporary, output_path)
    result = {
        "source": str(source_path),
        "source_sha256": _sha256(source_path),
        "output": str(output_path),
        "output_sha256": _sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "fts5_included": False,
        "counts": counts,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build_compact_catalog(args.source, args.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
