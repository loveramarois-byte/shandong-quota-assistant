from __future__ import annotations

from typing import Any

from .formatting import discipline_label

_HEADER = ["类型", "编码", "名称", "单位", "专业", "版本", "置信度", "页码", "命中原因", "待补条件", "冲突提示"]
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
                f"{float(item.get('confidence')):.0%}" if isinstance(item.get("confidence"), (int, float)) else "",
                str(item.get("pdf_page") or ""),
                "；".join(item.get("match_reasons") or []),
                "；".join(item.get("missing_conditions") or []),
                "；".join(item.get("conflicts") or []),
            ])
    return rows
