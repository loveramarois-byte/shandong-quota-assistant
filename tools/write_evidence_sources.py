from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: write_evidence_sources.py DATABASE OUTPUT_JSON")
    database, output = map(Path, sys.argv[1:])
    with sqlite3.connect(database) as connection:
        values = [
            row[0]
            for row in connection.execute(
                "select distinct source_path from chunks "
                "where source_path is not null and length(source_path)>0 "
                "order by source_path"
            )
        ]
    output.write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
