from __future__ import annotations

import re
from typing import Any


DISCIPLINE_LABELS = {
    "building": "建筑",
    "installation": "安装",
    "municipal": "市政",
    "landscape": "园林",
    "decoration": "装饰",
    "": "未标注",
    None: "未标注",
}

_UNIT_REPLACEMENTS = {
    "m2": "m²",
    "m²": "m²",
    "m3": "m³",
    "m³": "m³",
    "cm2": "cm²",
    "cm3": "cm³",
    "mm2": "mm²",
    "mm3": "mm³",
    "10m2": "10m²",
    "10m3": "10m³",
    "100m2": "100m²",
    "100m3": "100m³",
}

_SECTION_NAMES = (
    "清单标准", "项目编码", "项目名称", "定额编号", "定额名称", "单位",
    "项目特征", "工程量计算规则", "工作内容", "备注", "人材机",
)
_SECTION_RE = re.compile(
    r"(?m)^(?P<name>" + "|".join(map(re.escape, _SECTION_NAMES)) + r")\s*[:：]?\s*"
)
_NOISE_LINE_RE = re.compile(r"^(?:nVolumn|nChapter|nIndex|nItemStart|nItemEnd|DeCodeOld|DECode|Type|Temp|xhlNumber)\s*:", re.I)


def discipline_label(value: str | None) -> str:
    value = (value or "").strip()
    return DISCIPLINE_LABELS.get(value, value or "未标注")


def normalize_unit(value: Any) -> str:
    unit = str(value or "").strip()
    if not unit:
        return ""
    unit = unit.replace("\ue015", "m³").replace("\ue016", "m²")
    compact = re.sub(r"\s+", "", unit).lower()
    if compact in _UNIT_REPLACEMENTS:
        return _UNIT_REPLACEMENTS[compact]
    # Handle common encoded forms such as 10 m3 without changing free text.
    return re.sub(r"(?<![A-Za-z0-9])(\d+\s*)m([23])\b", lambda m: f"{m.group(1).replace(' ', '')}m{'²' if m.group(2) == '2' else '³'}", unit, flags=re.I)


def candidate_row_values(item: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    """Return the six stable spreadsheet columns used by candidate copy actions."""
    discipline = item.get("discipline")
    return (
        str(item.get("code") or "").strip(),
        str(item.get("name") or item.get("title") or "").strip(),
        normalize_unit(item.get("unit")),
        str(
            item.get("version")
            or item.get("quota_edition")
            or item.get("standard_edition")
            or item.get("edition")
            or ""
        ).strip(),
        discipline_label(discipline) if discipline else "",
        str(item.get("pdf_page") or "").strip(),
    )


def candidate_row_tsv(item: dict[str, Any]) -> str:
    """Serialize one candidate as 编码、名称、单位、版本、专业、页码."""
    return "\t".join(candidate_row_values(item))


def _clean(value: str | None, *, limit: int = 1200) -> str:
    value = (value or "").replace("\r", "").replace("\ue015", "m³").replace("\ue016", "m²")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    lines = [line.strip(" \t") for line in value.splitlines()]
    lines = [line for line in lines if line and not _NOISE_LINE_RE.match(line)]
    cleaned = "\n".join(lines).strip(" \n;；")
    return cleaned[:limit]


def parse_sections(text: str | None) -> dict[str, str]:
    """Extract readable sections from bill/quota text without exposing raw metadata."""
    source = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_SECTION_RE.finditer(source))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        name = match.group("name")
        value = _clean(source[match.end():end])
        if value:
            sections[name] = value
    if "单位" in sections:
        sections["单位"] = normalize_unit(sections["单位"].splitlines()[0])
    return sections


def _resource_summary(metadata: dict[str, Any] | None) -> list[str]:
    resources = (metadata or {}).get("resources") or []
    result: list[str] = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        name = str(resource.get("name") or "").strip()
        specification = str(resource.get("specification") or "").strip()
        quantity = resource.get("quantity")
        unit = normalize_unit(resource.get("unit"))
        if not name or quantity is None:
            continue
        label = f"{name}{(' ' + specification) if specification else ''} {quantity:g} {unit}" if isinstance(quantity, (int, float)) else f"{name}{(' ' + specification) if specification else ''} {quantity} {unit}"
        result.append(label.strip())
    return result[:8]


def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    """Add stable display fields used by result cards and AI context."""
    enriched = dict(item)
    sections = parse_sections(enriched.get("text"))
    metadata = enriched.get("metadata") if isinstance(enriched.get("metadata"), dict) else {}
    item_meta = metadata.get("bill") if isinstance(metadata.get("bill"), dict) else {}
    enriched["discipline_label"] = discipline_label(enriched.get("discipline"))
    enriched["unit"] = normalize_unit(enriched.get("unit") or sections.get("单位") or item_meta.get("ItemUnit1"))
    enriched["characteristics"] = sections.get("项目特征", "")
    enriched["calculation_rule"] = sections.get("工程量计算规则", "")
    enriched["work_content"] = sections.get("工作内容", "")
    enriched["remark"] = sections.get("备注", "")
    enriched["resources"] = enriched.get("resources") or _resource_summary(metadata)
    if enriched.get("condition_text"):
        enriched["condition_text"] = _clean(str(enriched["condition_text"]), limit=800)
    if enriched.get("type") in {"conversion", "work_content", "chapter_guidance"}:
        rule = metadata.get("rule") if isinstance(metadata.get("rule"), dict) else {}
        title = str(rule.get("Name") or enriched.get("title") or "").strip(" /")
        tips = _clean(str(rule.get("Tips") or ""), limit=800)
        # Chapter guidance is useful as context, but its generated header text is noise.
        if enriched.get("type") == "chapter_guidance" and enriched.get("title") == "header":
            title = "章节说明"
        enriched["rule_title"] = title
        enriched["rule_text"] = tips or _clean(enriched.get("text"), limit=800)
    return enriched
