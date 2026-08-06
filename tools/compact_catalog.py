"""Build the structured-only runtime catalogue used by release bundles.

The development database also contains PDF/OCR pages, duplicated search
chunks, raw import payloads and FTS shadow tables. Release bundles rebuild the
runtime search rows from the structured quota, bill, relation and resource
tables so users do not have to download the source-document corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable


REQUIRED_TABLES = (
    "quota_items",
    "bill_items",
    "bill_quota_links",
    "chunks",
)
OPTIONAL_TABLES = (
    "consumptions",
    "materials",
    "rules",
)
COPY_OVERRIDES = {
    "quota_items": {
        "page_id": "NULL",
        "source_path": "NULL",
        "pdf_page": "NULL",
        "context": "NULL",
        "master_json": "'{}'",
        "alignment_status": "'master_only'",
    },
    "bill_items": {"raw_json": "'{}'"},
    "bill_quota_links": {"raw_json": "'{}'"},
    "materials": {"raw_json": "'{}'"},
    "rules": {"raw_json": "'{}'"},
}
RUNTIME_RULE_TYPES = {"work_content", "conversion", "chapter_guidance"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _table_schema(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not row or not row[0]:
        raise RuntimeError(f"source catalogue is missing table: {table}")
    return str(row[0])


def _table_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')]


def _copy_table(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    table: str,
    overrides: dict[str, str] | None = None,
) -> int:
    target.execute(_table_schema(source, table))
    columns = _table_columns(source, table)
    column_sql = ",".join(f'"{column}"' for column in columns)
    overrides = overrides or {}
    select_sql = ",".join(
        overrides.get(column, f'"{column}"') for column in columns
    )
    placeholders = ",".join("?" for _ in columns)
    insert_sql = f'INSERT INTO "{table}" ({column_sql}) VALUES ({placeholders})'
    cursor = source.execute(f'SELECT {select_sql} FROM "{table}"')
    copied = 0
    while True:
        rows = cursor.fetchmany(2_000)
        if not rows:
            break
        target.executemany(insert_sql, rows)
        copied += len(rows)
    return copied


def _select_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: Iterable[str],
) -> str:
    present = set(_table_columns(connection, table))
    return ",".join(
        f'"{column}"' if column in present else f'NULL AS "{column}"'
        for column in columns
    )


def _resource_rows(connection: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    present = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    if not {"consumptions", "materials"}.issubset(present):
        return iter(())
    consumption_columns = set(_table_columns(connection, "consumptions"))
    required = {
        "quota_kind_id",
        "quota_ordinal",
        "resource_id",
        "material_library_id",
        "resource_order",
        "quantity",
    }
    if not required.issubset(consumption_columns):
        return iter(())
    return iter(connection.execute(
        "SELECT c.quota_kind_id,c.quota_ordinal,c.quantity,m.name,m.specification,m.unit "
        "FROM consumptions c LEFT JOIN materials m "
        "ON m.library_id=c.material_library_id AND m.resource_id=c.resource_id "
        "ORDER BY c.quota_kind_id,c.quota_ordinal,c.resource_order"
    ))


def _resource_line(row: sqlite3.Row) -> str:
    name = str(row["name"] or "").strip()
    if not name:
        return ""
    specification = str(row["specification"] or "").strip()
    unit = str(row["unit"] or "").strip()
    quantity = row["quantity"]
    if isinstance(quantity, (int, float)):
        quantity_text = f"{quantity:g}"
    else:
        quantity_text = str(quantity or "").strip()
    return " ".join(
        value for value in (name, specification, quantity_text, unit) if value
    )


def _work_content_map(connection: sqlite3.Connection) -> dict[tuple[int, str], str]:
    present = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rules'"
    ).fetchone()
    if not present:
        return {}
    result: dict[tuple[int, str], str] = {}
    rows = connection.execute(
        "SELECT quota_kind_id,code_hint,title,text FROM rules "
        "WHERE rule_type='work_content' AND quota_kind_id IS NOT NULL "
        "AND code_hint IS NOT NULL ORDER BY rule_id"
    )
    for row in rows:
        key = (int(row["quota_kind_id"]), str(row["code_hint"]))
        result.setdefault(key, str(row["title"] or row["text"] or "").strip())
    return result


def _build_runtime_chunks(connection: sqlite3.Connection) -> tuple[int, set[str]]:
    insert_sql = (
        "INSERT INTO chunks "
        "(chunk_id,chunk_type,edition,discipline,code,title,source_path,pdf_page,text,metadata_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)"
    )
    work_content = _work_content_map(connection)
    resources = _resource_rows(connection)
    current_resource = next(resources, None)
    quota_fields = (
        "quota_kind_id", "ordinal", "edition", "discipline", "code", "name",
        "unit", "remark",
    )
    quota_select = _select_columns(connection, "quota_items", quota_fields)
    quota_rows = connection.execute(
        f"SELECT {quota_select} FROM quota_items ORDER BY quota_kind_id,ordinal"
    )
    batch: list[tuple[object, ...]] = []
    count = 0
    chunk_types: set[str] = set()
    for row in quota_rows:
        key = (int(row["quota_kind_id"]), int(row["ordinal"]))
        lines = [
            f"定额编号: {row['code'] or ''}",
            f"定额名称: {row['name'] or ''}",
            f"单位: {row['unit'] or ''}",
        ]
        if row["remark"]:
            lines.append(f"备注: {str(row['remark']).strip()}")
        content = work_content.get((key[0], str(row["code"] or "")), "")
        if content:
            lines.append(f"工作内容: {content}")
        resource_lines: list[str] = []
        while current_resource is not None:
            resource_key = (
                int(current_resource["quota_kind_id"]),
                int(current_resource["quota_ordinal"]),
            )
            if resource_key < key:
                current_resource = next(resources, None)
                continue
            if resource_key != key:
                break
            if len(resource_lines) < 8:
                value = _resource_line(current_resource)
                if value:
                    resource_lines.append(value)
            current_resource = next(resources, None)
        if resource_lines:
            lines.extend(("人材机:", *resource_lines))
        batch.append((
            f"quota:{key[0]}:{key[1]}",
            "quota_item",
            row["edition"],
            row["discipline"],
            row["code"],
            row["name"],
            None,
            None,
            "\n".join(lines),
            '{"alignment":"master_only"}',
        ))
        if len(batch) >= 2_000:
            connection.executemany(insert_sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        connection.executemany(insert_sql, batch)
        count += len(batch)
        batch.clear()
    chunk_types.add("quota_item")

    bill_fields = (
        "standard_edition", "item_id", "discipline", "code", "name", "unit",
        "characteristics", "calculation_rule", "work_content", "remark",
    )
    bill_select = _select_columns(connection, "bill_items", bill_fields)
    for row in connection.execute(
        f"SELECT {bill_select} FROM bill_items ORDER BY standard_edition,item_id"
    ):
        labels = (
            ("清单标准", row["standard_edition"]),
            ("项目编码", row["code"]),
            ("项目名称", row["name"]),
            ("单位", row["unit"]),
            ("项目特征", row["characteristics"]),
            ("工程量计算规则", row["calculation_rule"]),
            ("工作内容", row["work_content"]),
            ("备注", row["remark"]),
        )
        text = "\n".join(
            f"{label}: {str(value).strip()}" for label, value in labels if value
        )
        batch.append((
            f"bill:{row['standard_edition']}:{row['item_id']}",
            "bill_item",
            row["standard_edition"],
            row["discipline"],
            row["code"],
            row["name"],
            None,
            None,
            text,
            "{}",
        ))
        if len(batch) >= 2_000:
            connection.executemany(insert_sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        connection.executemany(insert_sql, batch)
        count += len(batch)
        batch.clear()
    chunk_types.add("bill_item")

    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='rules'"
    ).fetchone():
        for row in connection.execute(
            "SELECT rule_id,edition,discipline,rule_type,code_hint,title,text "
            "FROM rules ORDER BY rule_id"
        ):
            rule_type = str(row["rule_type"] or "")
            if rule_type not in RUNTIME_RULE_TYPES:
                continue
            batch.append((
                f"rule:{row['rule_id']}",
                rule_type,
                row["edition"],
                row["discipline"],
                row["code_hint"],
                row["title"],
                None,
                None,
                row["text"],
                "{}",
            ))
            chunk_types.add(rule_type)
            if len(batch) >= 2_000:
                connection.executemany(insert_sql, batch)
                count += len(batch)
                batch.clear()
    if batch:
        connection.executemany(insert_sql, batch)
        count += len(batch)
    return count, chunk_types


def build_compact_catalog(source_path: Path, output_path: Path) -> dict[str, object]:
    source_path = source_path.resolve()
    output_path = output_path.resolve()
    if source_path == output_path:
        raise ValueError("source and output catalogue must be different files")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.unlink(missing_ok=True)

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    target = sqlite3.connect(temporary)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
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
            raise RuntimeError(
                "source catalogue is missing tables: " + ", ".join(sorted(missing))
            )
        copied_tables = [
            "quota_items", "bill_items", "bill_quota_links",
            *(table for table in OPTIONAL_TABLES if table in present),
        ]
        counts = {
            table: _copy_table(
                source, target, table, COPY_OVERRIDES.get(table)
            )
            for table in copied_tables
        }
        target.execute(_table_schema(source, "chunks"))
        placeholders = ",".join("?" for _ in copied_tables)
        for row in source.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='index' AND sql IS NOT NULL "
            f"AND tbl_name IN ({placeholders})",
            copied_tables,
        ):
            target.execute(str(row[0]))
        if "rules" in copied_tables:
            target.execute(
                "CREATE INDEX IF NOT EXISTS idx_compact_rules_lookup "
                "ON rules(rule_type,quota_kind_id,code_hint)"
            )
        chunk_count, chunk_types = _build_runtime_chunks(target)
        counts["chunks"] = chunk_count
        target.execute(
            "CREATE INDEX idx_chunks_scope_title "
            "ON chunks(chunk_type,edition,discipline,title)"
        )
        target.execute(
            "CREATE INDEX idx_chunks_scope_code "
            "ON chunks(chunk_type,edition,discipline,code)"
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
    except Exception:
        target.close()
        source.close()
        temporary.unlink(missing_ok=True)
        raise
    else:
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
        "pdf_content_included": False,
        "source_paths_included": False,
        "chunk_types": sorted(chunk_types),
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
