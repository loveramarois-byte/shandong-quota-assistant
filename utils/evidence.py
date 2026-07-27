from __future__ import annotations

import copy
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .paths import database_path, resource_path, writable_path


def _positive_page(value: object) -> int | None:
    try:
        page = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def resolve_source_path(value: object, *, catalog_path: Path | None = None) -> Path | None:
    """Resolve a registered source without recursively scanning the machine."""
    raw = str(value or "").strip()
    if not raw:
        return None
    registered = Path(raw)
    candidates = [registered]
    try:
        catalog = (catalog_path or database_path()).resolve()
    except (FileNotFoundError, OSError):
        catalog = None
    filename = registered.name
    if filename:
        candidates.extend((
            writable_path("sources", filename),
            resource_path("sources", filename),
        ))
        if catalog is not None:
            candidates.extend((
                catalog.parent / "sources" / filename,
                catalog.parent.parent / "sources" / filename,
            ))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def open_source_page(source_path: object, pdf_page: object = None) -> bool:
    """Open a local source at its registered PDF page when the shell supports it."""
    path = resolve_source_path(source_path)
    if path is None:
        return False
    page = _positive_page(pdf_page)
    try:
        target = path.as_uri() + (f"#page={page}" if page else "")
        os.startfile(target)  # type: ignore[attr-defined]
        return True
    except (OSError, AttributeError, ValueError):
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True
        except (OSError, AttributeError):
            return False


def _candidate_groups(result: dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    for group in ("bills", "quotas", "links", "guidance"):
        for item in (result or {}).get(group) or []:
            if isinstance(item, dict):
                yield item


def _load_chunk_sources(record_ids: set[str], *, catalog_path: Path | None = None) -> dict[str, dict[str, Any]]:
    if not record_ids:
        return {}
    path = (catalog_path or database_path()).resolve()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    found: dict[str, dict[str, Any]] = {}
    try:
        values = sorted(record_ids)
        for start in range(0, len(values), 500):
            batch = values[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT chunk_id,source_path,pdf_page FROM chunks WHERE chunk_id IN ({placeholders})",
                batch,
            )
            for row in rows:
                found[str(row["chunk_id"])] = {
                    "source_path": row["source_path"],
                    "pdf_page": row["pdf_page"],
                }
    finally:
        connection.close()
    return found


def hydrate_result_sources(result: dict[str, Any] | None, *, catalog_path: Path | None = None) -> dict[str, Any] | None:
    """Return a display copy with source paths/pages restored by stable record ID."""
    if not result:
        return result
    hydrated = copy.deepcopy(result)
    items = list(_candidate_groups(hydrated))
    record_ids = {
        str(value)
        for item in items
        for value in (item.get("record_id"), item.get("quota_record_id"))
        if value
    }
    try:
        sources = _load_chunk_sources(record_ids, catalog_path=catalog_path)
    except (FileNotFoundError, OSError, sqlite3.Error):
        sources = {}
    for item in items:
        direct = sources.get(str(item.get("record_id") or ""), {})
        quota = sources.get(str(item.get("quota_record_id") or ""), {})
        source = direct.get("source_path") or quota.get("source_path") or item.get("source_path")
        page = direct.get("pdf_page") or quota.get("pdf_page") or item.get("pdf_page")
        if source:
            item["source_path"] = source
        if _positive_page(page):
            item["pdf_page"] = _positive_page(page)
    return hydrated


def reference_evidence(reference: str, item: dict[str, Any], *, catalog_path: Path | None = None) -> dict[str, Any]:
    source_path = str(item.get("source_path") or "").strip()
    page = _positive_page(item.get("pdf_page"))
    resolved = resolve_source_path(source_path, catalog_path=catalog_path) if source_path else None
    if resolved is not None and page is not None:
        status = "located"
        reason = f"已定位到原书第 {page} 页"
    elif source_path and page is not None:
        status = "file_missing"
        reason = "页码已登记，但来源文件未安装"
    elif resolved is not None:
        status = "page_missing"
        reason = "已找到来源文件，但原书页码待补"
    else:
        status = "unregistered"
        reason = "原书文件和页码尚未挂载"
    display_path = resolved or (Path(source_path) if source_path else None)
    return {
        "reference": reference.upper(),
        "record_id": item.get("record_id"),
        "code": item.get("code"),
        "title": item.get("title"),
        "source_path": str(display_path or ""),
        "source_name": display_path.name if display_path else "",
        "pdf_page": page,
        "status": status,
        "reason": reason,
        "located": status == "located",
    }
