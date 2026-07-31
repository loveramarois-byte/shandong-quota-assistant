from __future__ import annotations

from typing import Any

from .formatting import discipline_label
from .pricing_pipeline import proposal_confirmable

_HEADER = ["类型", "编码", "名称", "单位", "专业", "版本", "条件吻合度", "页码", "命中原因", "待补条件", "冲突提示"]
_GROUP_LABELS = {"bills": "清单", "quotas": "定额", "links": "关联定额", "guidance": "规则与换算"}


def result_csv(result: dict[str, Any]) -> list[list[str]]:
    """Rows for spreadsheet export (P1-5.2); UTF-8 BOM is added by the caller."""
    rows: list[list[str]] = [_HEADER]
    for group, label in _GROUP_LABELS.items():
        for item in result.get(group) or []:
            rows.append([
                label,
                str(item.get("code") or ""),
                str(item.get("title") or ""),
                str(item.get("unit") or ""),
                discipline_label(item.get("discipline")),
                str(item.get("quota_edition") or item.get("edition") or ""),
                {"high": "高", "medium": "中", "low": "低"}.get(str(item.get("match_level") or ""), ""),
                str(item.get("pdf_page") or ""),
                "；".join(item.get("match_reasons") or []),
                "；".join(item.get("missing_conditions") or []),
                "；".join(item.get("conflicts") or []),
            ])
    return rows


def _evidence_text(proposal: dict[str, Any], line: dict[str, Any] | None = None) -> str:
    pages = [str(value) for value in proposal.get("evidence_pages") or [] if value]
    if pages:
        return "；".join(dict.fromkeys(pages))
    refs = [*(proposal.get("evidence_refs") or []), *((line or {}).get("evidence_refs") or [])]
    return "；".join(dict.fromkeys(str(value) for value in refs if value))


def proposal_csv(result: dict[str, Any], *, confirmed_only: bool = True) -> list[list[str]]:
    rows = [["施工事项", "类型", "角色", "编码", "名称", "单位", "状态", "假设/换算", "证据"]]
    work_items = {str(value.get("id") or ""): value for value in result.get("work_items") or []}
    status_labels = {
        "ready_for_review": "待复核",
        "needs_clarification": "待补条件",
        "multiple_valid_options": "多个有效方案",
        "no_reliable_match": "暂无可靠组合",
    }
    for proposal in result.get("proposals") or []:
        if confirmed_only and (not proposal.get("confirmed") or not proposal_confirmable(proposal)):
            continue
        work_item = work_items.get(str(proposal.get("work_item_id") or ""), {})
        span = str(work_item.get("source_span") or proposal.get("work_item_id") or "")
        status = status_labels.get(str(proposal.get("status") or ""), str(proposal.get("status") or ""))
        if proposal.get("bill_record_id"):
            rows.append([span, "清单", "", str(proposal.get("bill_code") or ""), str(proposal.get("bill_title") or ""), str(proposal.get("bill_unit") or ""), status, "；".join(proposal.get("assumptions") or []), _evidence_text(proposal)])
        for quota in proposal.get("quota_lines") or []:
            role = {"main": "主项", "supplement": "增补", "adjustment": "调整", "transport": "运输", "conversion": "换算", "alternative": "备选"}.get(str(quota.get("role") or ""), str(quota.get("role") or ""))
            rows.append([span, "定额", role, str(quota.get("code") or ""), str(quota.get("title") or ""), str(quota.get("unit") or ""), status, "；".join(proposal.get("assumptions") or []), _evidence_text(proposal, quota)])
    return rows


def confirmed_proposal_payload(result: dict[str, Any]) -> dict[str, Any]:
    confirmed = [value for value in result.get("proposals") or [] if value.get("confirmed") and proposal_confirmable(value)]
    work_ids = {str(value.get("work_item_id") or "") for value in confirmed}
    return {
        "analysis_version": str(result.get("analysis_version") or "1"),
        "query": result.get("query"),
        "quota_edition": result.get("quota_edition"),
        "standard_edition": result.get("standard_edition"),
        "discipline": result.get("discipline"),
        "work_items": [value for value in result.get("work_items") or [] if str(value.get("id") or "") in work_ids],
        "proposals": confirmed,
    }
