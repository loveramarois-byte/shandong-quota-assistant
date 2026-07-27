from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import sessions_dir

SESSION_SCHEMA_VERSION = 2
CATALOG_BUILD_ID = "legacy-v3-06a9df5102a9"
PROMPT_VERSION = "quota-assistant-v2"
_LAST_UPDATED_AT = 0.0
_WRITE_LOCK = threading.RLock()


class SessionDeletedError(RuntimeError):
    pass


def _next_updated_at() -> float:
    """Produce a strictly ordered timestamp when Windows writes occur in one tick."""
    global _LAST_UPDATED_AT
    now = time.time()
    _LAST_UPDATED_AT = max(now, _LAST_UPDATED_AT + 0.000001)
    return _LAST_UPDATED_AT


def _safe_id(session_id: str) -> str:
    return re.sub(r"[^0-9A-Za-z_-]", "", str(session_id or ""))


def _session_file(session_id: str) -> Path:
    return sessions_dir() / f"{_safe_id(session_id)}.json"


def _tombstone_file(session_id: str) -> Path:
    return sessions_dir() / f"{_safe_id(session_id)}.tombstone"


def _trash_dir() -> Path:
    path = sessions_dir() / "trash"
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def new_turn_id() -> str:
    return uuid.uuid4().hex[:12]


def _new_session_data(title: str, *, session_id: str | None = None, created_at: float | None = None) -> dict[str, Any]:
    now = created_at or _next_updated_at()
    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "id": session_id or new_session_id(),
        "title": title[:60] or "新的检索",
        "created_at": now,
        "updated_at": now,
        "revision": 0,
        "turns": [],
    }


def create_session(title: str = "新的检索") -> dict[str, Any]:
    session = _new_session_data(title)
    save_session(session)
    return session


def _json_safe_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"text", "metadata", "source_path"}
        and isinstance(value, (str, int, float, bool, list, dict, type(None)))
    }


def serialize_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    """Persist the complete returned candidate snapshot without silent slicing."""
    if not result:
        return None
    keep: dict[str, Any] = {}
    for key in ("query", "quota_edition", "standard_edition", "discipline", "conditions", "timing", "search_backend", "hints", "confidence", "decision_status"):
        if key in result:
            keep[key] = result[key]
    for group in ("bills", "quotas", "links", "guidance"):
        keep[group] = [_json_safe_item(item) for item in (result.get(group) or []) if isinstance(item, dict)]
    return keep


def _snapshot_hash(snapshot: dict[str, Any] | None) -> str | None:
    if snapshot is None:
        return None
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest().upper()


def create_turn(
    session: dict[str, Any],
    query: str,
    *,
    quota_edition: str,
    standard_edition: str,
    discipline: str | None,
    request_id: int | None = None,
) -> dict[str, Any]:
    turn = {
        "turn_id": new_turn_id(),
        "query": str(query),
        "filters": {
            "quota_edition": str(quota_edition),
            "standard_edition": str(standard_edition),
            "discipline": discipline,
        },
        "parsed_conditions": {},
        "catalog_build_id": CATALOG_BUILD_ID,
        "retrieval_snapshot": None,
        "retrieval_snapshot_sha256": None,
        "ai_attempts": [],
        "human_selections": {"primary": {}},
        "human_edits": [],
        "exports": [],
        "request_id": request_id,
        "status": "searching",
        "created_at": _next_updated_at(),
        "completed_at": None,
    }
    session.setdefault("turns", []).append(turn)
    return turn


def find_turn(session: dict[str, Any] | None, turn_id: str | None) -> dict[str, Any] | None:
    if not session or not turn_id:
        return None
    return next((turn for turn in session.get("turns") or [] if turn.get("turn_id") == turn_id), None)


def set_turn_local_result(session: dict[str, Any], turn_id: str, result: dict[str, Any], *, ai_enabled: bool) -> dict[str, Any]:
    turn = find_turn(session, turn_id)
    if turn is None:
        raise KeyError(f"turn not found: {turn_id}")
    snapshot = serialize_result(result)
    if turn.get("retrieval_snapshot") is not None and turn.get("retrieval_snapshot") != snapshot:
        raise ValueError("retrieval snapshot is immutable once stored")
    turn["retrieval_snapshot"] = snapshot
    turn["retrieval_snapshot_sha256"] = _snapshot_hash(snapshot)
    turn["parsed_conditions"] = dict(result.get("conditions") or {})
    turn["status"] = "ai_running" if ai_enabled else "local_ready"
    if not ai_enabled:
        turn["completed_at"] = _next_updated_at()
    return turn


def start_ai_attempt(session: dict[str, Any], turn_id: str, *, request_id: int, model: str = "") -> dict[str, Any]:
    turn = find_turn(session, turn_id)
    if turn is None:
        raise KeyError(f"turn not found: {turn_id}")
    attempt = {
        "request_id": request_id,
        "model": str(model or ""),
        "prompt_version": PROMPT_VERSION,
        "status": "running",
        "response": None,
        "validation": None,
        "started_at": _next_updated_at(),
        "completed_at": None,
    }
    turn.setdefault("ai_attempts", []).append(attempt)
    turn["status"] = "ai_running"
    return attempt


def finish_ai_attempt(
    session: dict[str, Any],
    turn_id: str,
    *,
    request_id: int,
    status: str,
    response: str | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    turn = find_turn(session, turn_id)
    if turn is None:
        raise KeyError(f"turn not found: {turn_id}")
    attempt = next((item for item in reversed(turn.get("ai_attempts") or []) if item.get("request_id") == request_id), None)
    if attempt is None:
        attempt = start_ai_attempt(session, turn_id, request_id=request_id)
    attempt.update({
        "status": status,
        "response": response,
        "validation": validation,
        "completed_at": _next_updated_at(),
    })
    turn["status"] = "completed" if status == "completed" else status
    turn["completed_at"] = _next_updated_at()
    return turn


def set_turn_status(session: dict[str, Any], turn_id: str, status: str) -> None:
    turn = find_turn(session, turn_id)
    if turn is None:
        return
    turn["status"] = status
    if status in {"completed", "cancelled", "error", "local_ready"}:
        turn["completed_at"] = _next_updated_at()


def set_turn_selection(session: dict[str, Any], turn_id: str, kind: str, item: dict[str, Any]) -> None:
    turn = find_turn(session, turn_id)
    if turn is None:
        raise KeyError(f"turn not found: {turn_id}")
    record_id = str(item.get("record_id") or "").strip()
    if not record_id:
        raise ValueError("selection requires a stable record_id")
    turn.setdefault("human_selections", {}).setdefault("primary", {})[kind] = {
        "record_id": record_id,
        "code": item.get("code"),
        "title": item.get("title"),
        "unit": item.get("unit"),
        "edition": item.get("quota_edition") or item.get("edition"),
        "standard_edition": item.get("standard_edition"),
        "discipline": item.get("discipline"),
        "kind_label": "清单" if kind == "bill" else "定额",
    }


def _validate_session(data: Any) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        return False
    if data.get("schema_version") != SESSION_SCHEMA_VERSION or not isinstance(data.get("turns"), list):
        return False
    for turn in data["turns"]:
        if not isinstance(turn, dict) or not isinstance(turn.get("turn_id"), str) or not isinstance(turn.get("query"), str):
            return False
        if not isinstance(turn.get("filters"), dict) or not isinstance(turn.get("human_selections"), dict):
            return False
    return True


def _migrate_v1(data: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(data.get("id"), str):
        return None
    migrated = _new_session_data(
        str(data.get("title") or "旧版检索记录"),
        session_id=data["id"],
        created_at=float(data.get("created_at") or _next_updated_at()),
    )
    migrated["updated_at"] = float(data.get("updated_at") or migrated["created_at"])
    migrated["migrated_from"] = 1
    messages = [item for item in data.get("messages") or [] if isinstance(item, dict)]
    result = data.get("result") if isinstance(data.get("result"), dict) else None
    user_messages = [str(item.get("text") or "") for item in messages if item.get("role") == "user" and item.get("text")]
    ai_messages = [item for item in messages if item.get("role") == "ai" and item.get("text")]
    query = str((result or {}).get("query") or (user_messages[-1] if user_messages else "旧版未配对查询"))
    if result or messages:
        turn = create_turn(
            migrated,
            query,
            quota_edition=str((result or {}).get("quota_edition") or "2025"),
            standard_edition=str((result or {}).get("standard_edition") or "2024"),
            discipline=(result or {}).get("discipline"),
        )
        if result:
            set_turn_local_result(migrated, turn["turn_id"], result, ai_enabled=bool(ai_messages))
        if ai_messages:
            latest_ai = ai_messages[-1]
            finish_ai_attempt(
                migrated,
                turn["turn_id"],
                request_id=-1,
                status="completed",
                response=str(latest_ai.get("text") or ""),
                validation=latest_ai.get("validation") if isinstance(latest_ai.get("validation"), dict) else {},
            )
        legacy_primary = ((data.get("selections") or {}).get("primary") or {}) if isinstance(data.get("selections"), dict) else {}
        if isinstance(legacy_primary, dict):
            turn["human_selections"] = {"primary": legacy_primary}
    if len(user_messages) > 1 or len(ai_messages) > 1:
        migrated["migration_warnings"] = [
            "V1 只保存最后一份候选，旧消息无法可靠绑定；原消息保存在 legacy_unpaired_messages，未伪造成检索证据。"
        ]
        migrated["legacy_unpaired_messages"] = messages
    return migrated


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(session: dict[str, Any]) -> None:
    if not session.get("id"):
        session["id"] = new_session_id()
    session_id = str(session["id"])
    session["schema_version"] = SESSION_SCHEMA_VERSION
    session["updated_at"] = _next_updated_at()
    session["revision"] = int(session.get("revision") or 0) + 1
    if not _validate_session(session):
        raise ValueError("invalid V2 session structure")
    path = _session_file(session_id)
    with _WRITE_LOCK:
        if _tombstone_file(session_id).exists():
            raise SessionDeletedError(f"session was deleted: {session_id}")
        if path.exists():
            try:
                old = _read_json(path)
            except (OSError, json.JSONDecodeError):
                old = None
            if isinstance(old, dict) and old.get("schema_version") != SESSION_SCHEMA_VERSION:
                migration_backup = path.with_suffix(".v1.bak")
                if not migration_backup.exists():
                    shutil.copy2(path, migration_backup)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(session, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                shutil.copy2(path, path.with_suffix(".bak"))
            os.replace(tmp, path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def load_session(session_id: str) -> dict[str, Any] | None:
    if _tombstone_file(session_id).exists():
        return None
    path = _session_file(session_id)
    if not path.exists():
        return None
    candidates = (path, path.with_suffix(".bak"))
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            data = _read_json(candidate)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("schema_version") == SESSION_SCHEMA_VERSION:
            return data if _validate_session(data) else None
        if isinstance(data, dict):
            migrated = _migrate_v1(data)
            if migrated and _validate_session(migrated):
                return migrated
    return None


def list_sessions() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sessions_dir().glob("*.json"):
        session_id = path.stem
        if _tombstone_file(session_id).exists():
            continue
        session = load_session(session_id)
        if session is None:
            continue
        try:
            updated_at = float(session.get("updated_at") or 0)
        except (TypeError, ValueError):
            updated_at = 0.0
        result.append({"id": session["id"], "title": str(session.get("title") or "未命名检索")[:60], "updated_at": updated_at})
    result.sort(key=lambda item: -item["updated_at"])
    return result


def rename_session(session_id: str, title: str) -> bool:
    session = load_session(session_id)
    if session is None:
        return False
    session["title"] = title.strip()[:60] or session.get("title") or "未命名检索"
    try:
        save_session(session)
        return True
    except (OSError, ValueError, SessionDeletedError):
        return False


def delete_session(session_id: str) -> bool:
    path = _session_file(session_id)
    if not path.exists() or _tombstone_file(session_id).exists():
        return False
    timestamp = int(time.time() * 1000)
    trash_path = _trash_dir() / f"{_safe_id(session_id)}-{timestamp}.json"
    tombstone = _tombstone_file(session_id)
    tombstone_tmp = tombstone.with_suffix(".tmp")
    with _WRITE_LOCK:
        try:
            tombstone_tmp.write_text(str(timestamp), encoding="ascii")
            os.replace(tombstone_tmp, tombstone)
            os.replace(path, trash_path)
            return True
        except OSError:
            try:
                tombstone_tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False


def export_session_markdown(session: dict[str, Any]) -> str:
    lines = [f"# {session.get('title') or '本地检索记录'}", ""]
    lines.append(f"- 导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 会话格式：V{session.get('schema_version') or 1}")
    for index, turn in enumerate(session.get("turns") or [], start=1):
        filters = turn.get("filters") or {}
        lines.extend([
            "",
            f"## 第 {index} 轮",
            "",
            f"- 查询：{turn.get('query') or ''}",
            f"- 定额版本：山东 {filters.get('quota_edition') or '-'} · 清单依据：山东 {filters.get('standard_edition') or '-'}",
            f"- 专业：{filters.get('discipline') or '全部专业'}",
            f"- 候选快照：{turn.get('retrieval_snapshot_sha256') or '未生成'}",
        ])
        primary = ((turn.get("human_selections") or {}).get("primary") or {})
        if primary:
            lines.extend(["", "### 已暂存候选"])
            for item in primary.values():
                if isinstance(item, dict):
                    lines.append(f"- {item.get('kind_label', '条目')}：{item.get('code', '')} {item.get('title', '')} [{item.get('record_id', '无记录ID')}]")
        attempts = turn.get("ai_attempts") or []
        if attempts and attempts[-1].get("response"):
            lines.extend(["", "### AI 辅助解释（未核验证据链）", "", str(attempts[-1]["response"])])
    for warning in session.get("migration_warnings") or []:
        lines.extend(["", f"> 迁移提示：{warning}"])
    lines.extend(["", "---", "本记录由山东定额助手导出；候选和 AI 解释不等于正式计价成果，须回到原书和项目依据复核。"])
    return "\n".join(lines)
