from __future__ import annotations

import re
from typing import Any

from .formatting import normalize_unit

# Quota sub-item codes such as 1-2-9 / 10-4-1-23; bill codes are 9-12 digits.
_QUOTA_CODE_RE = re.compile(r"(?<![\dA-Za-z])(\d{1,2}(?:-\d{1,3}){1,4})(?![\dA-Za-z-])")
_BILL_CODE_RE = re.compile(r"(?<!\d)(\d{9,12})(?:-\d{3})?(?!\d)")
_REFERENCE_RE = re.compile(r"\[R(\d+)\]", re.IGNORECASE)
_RECORD_ID_RE = re.compile(r"\b(?:quota|bill|link):[A-Za-z0-9_.:-]+\b")
_NOISE_CODE_RE = re.compile(r"^(?:19|20)\d{2}$")  # years such as 2016/2025 are not codes
_KEY_CONCLUSION_MARKERS = ("建议候选", "主选", "建议", "应套", "推荐", "结论", "选用", "套取", "套用")


def extract_codes(ai_text: str) -> list[str]:
    codes: list[str] = []
    for match in _QUOTA_CODE_RE.finditer(ai_text):
        value = match.group(1)
        if not _NOISE_CODE_RE.match(value.replace("-", "")):
            codes.append(value)
    for match in _BILL_CODE_RE.finditer(ai_text):
        codes.append(match.group(0).split("-")[0])
    return list(dict.fromkeys(codes))


def _normalise_code(value: object) -> str:
    code = str(value or "").strip()
    return code.split("-")[0] if re.fullmatch(r"\d{9,12}(?:-\d{3})?", code) else code


def _code_aliases(item: dict[str, Any]) -> set[str]:
    code = str(item.get("code") or "").strip()
    return {value for value in (code, _normalise_code(code)) if value}


def _all_candidates(result: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    entries: list[tuple[str, dict[str, Any]]] = []
    for group in ("bills", "quotas", "links", "guidance"):
        for raw_item in (result or {}).get(group) or []:
            if isinstance(raw_item, dict):
                entries.append((group, raw_item))
    return entries


def _in_result_scope(group: str, item: dict[str, Any], code: str, result: dict[str, Any] | None) -> bool:
    """Check the full local identity; never use another edition as a fallback."""
    if code not in _code_aliases(item):
        return False
    result = result or {}
    requested_discipline = result.get("discipline")
    if requested_discipline and item.get("discipline") != requested_discipline:
        return False
    is_bill = bool(re.fullmatch(r"\d{9,12}", code))
    if is_bill:
        return group == "bills" and str(item.get("edition") or "") == str(result.get("standard_edition") or "")
    if group not in {"quotas", "links"}:
        return False
    candidate_edition = item.get("quota_edition") or item.get("edition")
    return str(candidate_edition or "") == str(result.get("quota_edition") or "")


def _candidate_matches(code: str, result: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    return [
        (group, item)
        for group, item in _all_candidates(result)
        if _in_result_scope(group, item, code, result)
    ]


def _reference_index(result: dict[str, Any] | None) -> dict[str, tuple[str, dict[str, Any]]]:
    index: dict[str, tuple[str, dict[str, Any]]] = {}
    for group, item in _all_candidates(result):
        reference = str(item.get("reference") or "").upper()
        if reference:
            index[reference] = (group, item)
    return index


def verify_codes(codes: list[str], result: dict[str, Any] | None = None) -> dict[str, str]:
    """Validate only against the current result snapshot and its chosen scope.

    This deliberately does not query SQLite. A number that happens to exist in
    another edition/profession is not evidence for an AI claim in this turn.
    """
    statuses: dict[str, str] = {}
    for code in codes:
        matches = _candidate_matches(code, result)
        statuses[code] = "candidate" if len(matches) == 1 else "unverified"
    return statuses


def find_uncited_lines(ai_text: str) -> list[str]:
    """Key conclusion lines that carry no [R#] citation."""
    uncited: list[str] = []
    for raw_line in ai_text.splitlines():
        line = raw_line.strip().lstrip("#*-–>0123456789.、 ").strip()
        if len(line) < 8:
            continue
        if any(marker in line for marker in _KEY_CONCLUSION_MARKERS) and not _REFERENCE_RE.search(raw_line):
            uncited.append(line[:80])
    return uncited[:5]


def _claim_line(ai_text: str, code: str) -> str:
    return next((line for line in ai_text.splitlines() if code in line), "")


def _matches_structured_claim(line: str, item: dict[str, Any]) -> bool:
    """When the prompt format is used, guard the quoted name/unit as well."""
    if "｜" not in line:
        return True
    title = re.sub(r"\s+", "", str(item.get("title") or ""))
    unit = normalize_unit(item.get("unit"))
    compact_line = re.sub(r"\s+", "", line)
    if title and title not in compact_line:
        return False
    return not unit or unit in compact_line


def _claim_status(code: str, line: str, result: dict[str, Any] | None) -> tuple[str, dict[str, Any] | None, str]:
    matches = _candidate_matches(code, result)
    if not matches:
        return "unverified", None, "当前筛选口径下没有该编号"

    references = [f"R{number}" for number in _REFERENCE_RE.findall(line)]
    record_ids = set(_RECORD_ID_RE.findall(line))
    ref_index = _reference_index(result)
    cited_matches = [
        entry for reference in references
        for entry in [ref_index.get(reference.upper())]
        if entry is not None and entry in matches
    ]
    if not cited_matches:
        return "unverified", None, "未引用与该编号一致的本轮本地候选"

    group, item = cited_matches[0]
    record_id = str(item.get("record_id") or "")
    if record_ids and record_id not in record_ids:
        return "unverified", item, "记录 ID 与引用候选不一致"
    if not _matches_structured_claim(line, item):
        return "unverified", item, "名称或单位与引用候选不一致"
    return "candidate", item, "本轮候选、版本、专业、单位与引用一致"


def validate_ai_answer(ai_text: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate AI claims against this result snapshot, not the whole catalog.

    Evidence-registry support is intentionally separate. Until it exists, a
    matched ``[R#]`` is only a local-candidate pointer and must never be shown
    as a verified source claim.
    """
    codes = extract_codes(ai_text)
    statuses: dict[str, str] = {}
    claims: list[dict[str, Any]] = []
    for code in codes:
        line = _claim_line(ai_text, code)
        status, item, reason = _claim_status(code, line, result)
        statuses[code] = status
        claims.append({
            "code": code,
            "status": status,
            "record_id": item.get("record_id") if item else None,
            "edition": (item.get("quota_edition") or item.get("edition")) if item else None,
            "standard_edition": item.get("standard_edition") if item else None,
            "discipline": item.get("discipline") if item else None,
            "unit": item.get("unit") if item else None,
            "reason": reason,
        })
    unverified = sorted(code for code, status in statuses.items() if status != "candidate")
    uncited = find_uncited_lines(ai_text)
    references = {f"R{number}" for number in _REFERENCE_RE.findall(ai_text)}
    known_references = set(_reference_index(result))
    invalid_references = sorted(references - known_references)
    warnings: list[str] = []
    if unverified:
        warnings.append("AI 提到了未能在本轮筛选口径内核验的编号：" + "、".join(unverified) + "。这些编号不作为建议候选，请以本地列表和原书为准。")
    if invalid_references:
        warnings.append("AI 使用了本轮结果中不存在的资料编号：" + "、".join(invalid_references) + "。")
    if uncited:
        warnings.append("AI 部分关键结论未标注本地候选编号，属于模型推断，不可直接作为套项依据。")
    warnings.append("当前资料库尚未建立可定位证据链；[R#] 仅指向本轮本地候选，所有 AI 结论均为“未核验”。")
    return {
        "codes": statuses,
        "claims": claims,
        "unverified_codes": unverified,
        "uncited_lines": uncited,
        "invalid_references": invalid_references,
        "warnings": warnings,
        "referenced": bool(references & known_references),
        "evidence_verified": False,
    }
