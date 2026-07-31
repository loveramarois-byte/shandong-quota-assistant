from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 3

DISCIPLINES = {
    "building": ("演示基础构件", "演示基础构件浇筑", "m3", "10m3"),
    "installation": ("演示低压线管", "演示低压线管敷设", "m", "10m"),
    "municipal": ("演示园区路基", "演示园区路基铺筑", "m2", "100m2"),
    "landscape": ("演示庭院苗木", "演示庭院苗木栽植", "株", "10株"),
}


def default_demo_path() -> Path:
    if getattr(sys, "frozen", False):
        from utils.paths import app_data_dir

        return app_data_dir() / "demo" / "demo_catalog.sqlite"
    return ROOT / "data" / "demo" / "demo_catalog.sqlite"


def _schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA user_version=3;
        PRAGMA application_id=1397838163;
        CREATE TABLE quota_items (
            quota_kind_id INTEGER NOT NULL,
            ordinal INTEGER NOT NULL,
            edition TEXT NOT NULL,
            discipline TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            unit TEXT,
            pdf_page INTEGER,
            source_path TEXT,
            resource_count INTEGER NOT NULL DEFAULT 0,
            alignment_status TEXT NOT NULL DEFAULT 'master_only',
            PRIMARY KEY (quota_kind_id, ordinal)
        );
        CREATE INDEX idx_demo_quota_scope ON quota_items(edition, discipline, name);
        CREATE TABLE bill_items (
            item_id INTEGER NOT NULL,
            standard_edition TEXT NOT NULL,
            discipline TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            unit TEXT,
            PRIMARY KEY (standard_edition, item_id)
        );
        CREATE INDEX idx_demo_bill_scope ON bill_items(standard_edition, discipline, name);
        CREATE TABLE bill_quota_links (
            link_edition TEXT NOT NULL,
            link_id INTEGER NOT NULL,
            bill_item_id INTEGER NOT NULL,
            quota_kind_id INTEGER NOT NULL,
            quota_code TEXT NOT NULL,
            quota_title TEXT NOT NULL,
            unit TEXT,
            factor REAL,
            condition_text TEXT,
            PRIMARY KEY (link_edition, link_id)
        );
        CREATE TABLE chunks (
            chunk_id TEXT PRIMARY KEY,
            chunk_type TEXT NOT NULL,
            edition TEXT NOT NULL,
            discipline TEXT NOT NULL,
            code TEXT,
            title TEXT,
            source_path TEXT,
            pdf_page INTEGER,
            text TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            title,
            text,
            tokenize='trigram'
        );
        CREATE TABLE consumptions (
            consumption_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            unit TEXT
        );
        """
    )


def _bill_text(standard: str, code: str, name: str, unit: str, discipline: str) -> str:
    return (
        f"清单标准：合成演示 {standard}\n项目编码：{code}\n项目名称：{name}\n单位：{unit}\n"
        f"项目特征：{discipline} 专业的虚构演示条件\n工程量计算规则：仅用于演示软件流程\n"
        "工作内容：合成检索、关联、复核与导出示例"
    )


def _quota_text(edition: str, code: str, name: str, unit: str) -> str:
    return (
        f"定额编号：{code}\n定额名称：{name}\n单位：{unit}\n"
        f"工作内容：{edition} 合成演示记录，不对应任何真实定额条文或价格"
    )


def _populate(connection: sqlite3.Connection) -> None:
    chunks: list[tuple] = []
    link_id = 1
    for discipline_index, (discipline, values) in enumerate(DISCIPLINES.items(), start=1):
        bill_name, quota_name, bill_unit, quota_unit = values
        bill_id = 9000 + discipline_index
        for standard in ("2013", "2024"):
            bill_code = f"9{discipline_index:02d}{standard[-2:]}0001-000"
            connection.execute(
                "INSERT INTO bill_items VALUES (?,?,?,?,?,?)",
                (bill_id, standard, discipline, bill_code, bill_name, bill_unit),
            )
            bill_chunk_id = f"bill:{standard}:{bill_id}"
            bill_text = _bill_text(standard, bill_code, bill_name, bill_unit, discipline)
            chunks.append((bill_chunk_id, "bill_item", standard, discipline, bill_code, bill_name, "", 1, bill_text, "{}"))

        for edition in ("2016", "2025"):
            quota_kind_id = int(f"{edition}{discipline_index}")
            quota_code = f"{discipline_index}-{edition[-2:]}-1"
            connection.execute(
                "INSERT INTO quota_items "
                "(quota_kind_id,ordinal,edition,discipline,code,name,unit,pdf_page,source_path,resource_count,alignment_status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (quota_kind_id, 1, edition, discipline, quota_code, quota_name, quota_unit, 1, "", 1, "master_only"),
            )
            quota_chunk_id = f"quota:{quota_kind_id}:1"
            quota_text = _quota_text(edition, quota_code, quota_name, quota_unit)
            chunks.append((quota_chunk_id, "quota_item", edition, discipline, quota_code, quota_name, "", 1, quota_text, "{}"))

            standard = "2013" if edition == "2016" else "2024"
            connection.execute(
                "INSERT INTO bill_quota_links VALUES (?,?,?,?,?,?,?,?,?)",
                (standard, link_id, bill_id, quota_kind_id, quota_code, quota_name, quota_unit, 1.0, "合成演示关联，必须人工复核"),
            )
            link_id += 1

        guide_id = f"guide:2025:{discipline_index}"
        guide_text = "演示说明：所有记录均为虚构数据，不可用于真实工程。"
        chunks.append((guide_id, "chapter_guidance", "2025", discipline, "", "演示使用说明", "", 1, guide_text, json.dumps({"rule": {"Name": "演示使用说明", "Tips": guide_text}}, ensure_ascii=False)))

        connection.execute(
            "INSERT INTO consumptions(name,unit) VALUES (?,?)",
            (f"演示资源 {discipline_index}", bill_unit),
        )

    connection.executemany(
        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?)",
        chunks,
    )
    connection.executemany(
        "INSERT INTO chunks_fts(chunk_id,title,text) VALUES (?,?,?)",
        [(row[0], row[5], row[8]) for row in chunks],
    )


def build_demo_catalog(output: Path) -> Path:
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        _schema(connection)
        _populate(connection)
        connection.commit()
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("demo catalog quick_check failed")
    finally:
        connection.close()
    os.replace(temporary, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="生成无版权 schema v3 演示资料库")
    parser.add_argument("--output", type=Path, default=default_demo_path())
    args = parser.parse_args()
    path = build_demo_catalog(args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
