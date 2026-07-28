from __future__ import annotations

from copy import deepcopy
import re
import threading
import time
from typing import Any, Callable

from .pricing_models import (
    ClarificationQuestion,
    PricingProposal,
    QuotaSelection,
    VALID_PROPOSAL_STATUSES,
    VALID_QUOTA_ROLES,
    WorkItem,
)
from .query_parse import parse_query_conditions, rank_conditions
from .work_items import segment_description


SearchFunction = Callable[..., dict[str, Any]]
_ROLE_LABELS = {
    "main": "主项",
    "supplement": "增补",
    "adjustment": "调整",
    "transport": "运输",
    "conversion": "换算",
    "alternative": "备选",
}
_STATUS_LABELS = {
    "ready_for_review": "待复核",
    "needs_clarification": "待补条件",
    "multiple_valid_options": "有多个方案",
    "no_reliable_match": "暂无可靠组合",
}
_DISCIPLINE_LABELS = {
    "building": "建筑",
    "installation": "安装",
    "municipal": "市政",
    "landscape": "园林",
}
_DISCIPLINE_SIGNALS = {
    "building": (
        (r"混凝土垫层|基础垫层", 9),
        (r"防水|砌筑|抹灰|模板|钢筋|屋面|楼地面|墙面|土方", 5),
        (r"\bC\s*\d{2,3}\b", 2),
    ),
    "installation": (
        (r"电缆|电线|桥架|配管|风管|通风|消防|设备安装|管道安装", 8),
        (r"给排水|采暖|燃气|弱电|照明|配电", 6),
        (r"\bDN\s*\d+\b", 3),
    ),
    "municipal": (
        (r"市政|道路|路基|路面|桥涵|隧道|检查井|雨水井|污水井|路灯", 10),
        (r"雨水管|污水管|市政管网", 8),
    ),
    "landscape": (
        (r"园林|绿化|苗木|乔木|灌木|草坪|栽植|假山|园路", 10),
    ),
}


def infer_discipline(description: str) -> str | None:
    """Return one high-confidence discipline; ambiguous wording stays explicit."""
    text = str(description or "")
    scores = {
        discipline: sum(weight for pattern, weight in signals if re.search(pattern, text, re.I))
        for discipline, signals in _DISCIPLINE_SIGNALS.items()
    }
    ranked = sorted(scores.items(), key=lambda value: (-value[1], value[0]))
    if not ranked or ranked[0][1] < 5:
        return None
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    return ranked[0][0] if ranked[0][1] - runner_up >= 2 else None


def quota_role(title: str) -> str:
    value = str(title or "")
    if re.search(r"每增运|增运|运距|运输|装运", value):
        return "transport"
    if re.search(r"每增减|每增加|每减少|每增|增减|增加一层|增加厚度|第二层", value):
        return "adjustment"
    if "换算" in value:
        return "conversion"
    if re.search(r"附加|保护层|基层处理|泵送|脚手|模板", value):
        return "supplement"
    return "main"


def _attribute_values(work_item: WorkItem) -> dict[str, Any]:
    return {value.key: value.value for value in work_item.attributes}


def _normalized_trade_text(value: str) -> str:
    text = str(value or "").lower()
    replacements = {
        "sbs": "改性沥青",
        "三七灰土": "3:7灰土",
        "3∶7灰土": "3:7灰土",
        "商砼": "商品混凝土",
        "砼": "混凝土",
        "水泥稳定碎(砾)石": "水泥稳定碎石",
        "水泥稳定碎砾石": "水泥稳定碎石",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _bill_relevance(bill: dict[str, Any], work_item: WorkItem) -> float:
    title = _normalized_trade_text(str(bill.get("title") or ""))
    code_query = re.sub(r"\s+", "", work_item.source_span)
    bill_code = str(bill.get("code") or "")
    if re.fullmatch(r"\d{9,12}(?:-\d{3})?", code_query) and bill_code.startswith(code_query.removesuffix("-000")):
        return 1000
    score = 0.0
    semantic_hit = False
    if work_item.object and _normalized_trade_text(work_item.object) in title:
        score += 100
        semantic_hit = True
    if work_item.action and _normalized_trade_text(work_item.action) in title:
        score += 70
        semantic_hit = True
    if work_item.material and _normalized_trade_text(work_item.material) in title:
        score += 75 if len(work_item.material) >= 5 else 55
        semantic_hit = True
    if work_item.location:
        if "墙" in work_item.location and "墙" in title:
            score += 32
        elif "屋面" in work_item.location and "屋面" in title:
            score += 32
        elif _normalized_trade_text(work_item.location) in title:
            score += 24
    if "单独" in title and "单独" not in work_item.source_span:
        score -= 18
    if bill.get("conflicts"):
        score -= 100
    return score if semantic_hit else score - 120


def select_bill_candidate(work_item: WorkItem, bills: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [(value, _bill_relevance(value, work_item)) for value in bills]
    scored.sort(key=lambda pair: (-pair[1], -float(pair[0].get("score") or 0), str(pair[0].get("code") or "")))
    if not scored or scored[0][1] < 60:
        return None
    selected, score = scored[0]
    selected["proposal_bill_score"] = round(score, 3)
    selected["match_reasons"] = list(dict.fromkeys([*(selected.get("match_reasons") or []), "施工事项语义与清单名称一致"]))
    return selected


def _link_relevance(link: dict[str, Any], work_item: WorkItem) -> float:
    text = _normalized_trade_text(f"{link.get('title') or ''} {link.get('condition_text') or ''}")
    source = _normalized_trade_text(work_item.search_text())
    score = 0.0
    for term in (work_item.action, work_item.object, work_item.material, work_item.location):
        if term and _normalized_trade_text(term) in text:
            score += 28 if term in {work_item.object, work_item.material} else 12
    for token in re.findall(r"[\u3400-\u9fff]{2,}|[A-Za-z]+\d*", source):
        if token.lower() in text:
            score += 70 if token in {"暗配", "明配", "埋地", "架空", "热熔", "冷粘", "自粘"} else min(20, len(token) * 3)
    for specialization in ("防爆", "钢结构", "热缩管", "矿物绝缘", "耐火", "阻燃"):
        if specialization in text and specialization not in source:
            score -= 36
    for specialization, aliases in {
        "轻骨料": ("轻骨料", "陶粒"),
        "毛石": ("毛石",),
        "沥青": ("沥青",),
    }.items():
        if specialization in text:
            score += 24 if any(value in source for value in aliases) else -90
    if "无筋" in text:
        score += 36 if not re.search(r"钢筋|有筋", source) else -60
    condition_score, reasons, missing, conflicts = rank_conditions(link, parse_query_conditions(work_item.search_text()))
    link["match_reasons"] = list(dict.fromkeys([*(link.get("match_reasons") or []), *reasons])) or ["清单关联规则召回"]
    link["missing_conditions"] = list(dict.fromkeys([*(link.get("missing_conditions") or []), *missing]))
    link["conflicts"] = list(dict.fromkeys([*(link.get("conflicts") or []), *conflicts]))
    return score + condition_score - 80 * bool(link["conflicts"])


def _question_from_hint(work_item_id: str, hint: str, index: int) -> ClarificationQuestion:
    mappings = (
        ("material_application", r"未明确体现|按回填土还是|材料处理口径", "资料中的关联项未体现该材料，应按哪种做法处理？", ("按主体项目处理", "拆成独立材料做法", "不确定")),
        ("soil_type", r"土类|土类别", "本项土类别是哪一类？", ("一二类土", "三类土", "四类土", "不确定")),
        ("depth", r"深度|挖深|槽深|坑深", "本项施工深度是多少？", ("2m以内", "2~4m", "4m以上", "不确定")),
        ("method", r"人工|机械|施工方法", "本项采用哪种施工方式？", ("人工", "机械", "人工配合机械", "不确定")),
        ("distance", r"运距|运输距离", "本项运输距离是多少？", ("不外运", "1km以内", "1km以上", "不确定")),
        ("material", r"材料|防水类型|卷材|砂浆类型|管材", "本项使用的材料类型是什么？", ("按施工描述", "另行补充", "不确定")),
        ("thickness", r"厚度|厚", "本项设计厚度是多少？", ("按施工描述", "另行补充", "不确定")),
        ("diameter", r"直径|管径|DN", "本项管径或直径是多少？", ("按施工描述", "另行补充", "不确定")),
        ("cross_section", r"电缆截面|截面分档", "本项电缆截面是多少？", ("10mm2以内", "10~50mm2", "50mm2以上", "不确定")),
        ("location", r"部位|位置|室内|室外", "本项施工部位在哪里？", ("室内", "室外", "地下或埋地", "不确定")),
    )
    for field, pattern, question, options in mappings:
        if re.search(pattern, hint):
            return ClarificationQuestion(f"Q{index}", work_item_id, field, question, options, hint)
    return ClarificationQuestion(f"Q{index}", work_item_id, "critical_condition", "还有哪项关键施工条件需要补充？", ("补充说明", "不确定"), hint)


def _questions_for_item(work_item: WorkItem, search_result: dict[str, Any], selected_links: list[dict[str, Any]], start: int) -> list[ClarificationQuestion]:
    hints: list[str] = []
    for link in selected_links:
        hints.extend(link.get("missing_conditions") or [])
    hints.extend(search_result.get("hints") or [])
    questions: list[ClarificationQuestion] = []
    seen_fields: set[str] = set()
    known_fields = set(_attribute_values(work_item))
    if work_item.material:
        known_fields.add("material")
    if work_item.location:
        known_fields.add("location")
    for hint in dict.fromkeys(str(value) for value in hints if value):
        question = _question_from_hint(work_item.id, hint, start + len(questions))
        if question.field in seen_fields or question.field in known_fields:
            continue
        seen_fields.add(question.field)
        questions.append(question)
        if len(questions) == 3:
            break
    return questions


def _reference_items(item_results: list[tuple[WorkItem, dict[str, Any]]]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in ("bills", "quotas", "links", "guidance")}
    references: dict[str, str] = {}
    seen: dict[str, dict[str, Any]] = {}
    counter = 1
    for _work_item, result in item_results:
        for group in groups:
            replaced: list[dict[str, Any]] = []
            for raw_item in result.get(group) or []:
                item = raw_item
                record_id = str(item.get("record_id") or item.get("chunk_id") or "")
                if not record_id:
                    continue
                if record_id not in references:
                    references[record_id] = f"R{counter}"
                    counter += 1
                item["reference"] = references[record_id]
                if record_id not in seen:
                    seen[record_id] = item
                    groups[group].append(item)
                else:
                    item = seen[record_id]
                replaced.append(item)
            result[group] = replaced
    return groups, references


def _assemble_proposal(
    work_item: WorkItem,
    search_result: dict[str, Any],
    references: dict[str, str],
    question_start: int,
) -> tuple[PricingProposal, list[ClarificationQuestion]]:
    bill = select_bill_candidate(work_item, list(search_result.get("bills") or []))
    if bill is None:
        return PricingProposal(work_item_id=work_item.id, bill_record_id=None), []

    bill_id = str(bill.get("record_id") or "")
    links = [
        value for value in (search_result.get("links") or [])
        if str(value.get("bill_record_id") or "") == bill_id
    ]
    for link in links:
        link["proposal_score"] = round(_link_relevance(link, work_item), 3)
    links.sort(key=lambda value: (-float(value.get("proposal_score") or 0), str(value.get("code") or "")))
    viable_links = [value for value in links if not value.get("conflicts") and value.get("quota_record_id")]
    by_role: dict[str, list[dict[str, Any]]] = {}
    for link in viable_links:
        by_role.setdefault(quota_role(str(link.get("title") or "")), []).append(link)

    selected: list[dict[str, Any]] = []
    if by_role.get("main"):
        selected.append(by_role["main"][0])
    attributes = _attribute_values(work_item)
    if attributes.get("layers", 1) and int(attributes.get("layers") or 1) > 1 and by_role.get("adjustment"):
        selected.append(by_role["adjustment"][0])
    elif attributes.get("thickness") is not None and by_role.get("adjustment"):
        selected.append(by_role["adjustment"][0])
    if attributes.get("distance") is not None and by_role.get("transport"):
        selected.append(by_role["transport"][0])
    if "换算" in work_item.source_span and by_role.get("conversion"):
        selected.append(by_role["conversion"][0])
    for role in ("supplement",):
        relevant = by_role.get(role) or []
        if relevant and any(term in work_item.source_span for term in ("保护层", "基层处理", "泵送", "模板", "脚手")):
            selected.append(relevant[0])

    extra_hints: list[str] = []
    if re.fullmatch(r"\s*\d{9,12}(?:-\d{3})?\s*", work_item.source_span):
        extra_hints.append("只提供了清单编码，请补充会影响定额组合的施工做法和规格")
    main_options = by_role.get("main") or []
    method_facets = [value for value in ("热熔", "冷粘", "自粘", "明配", "暗配", "人工", "机械") if any(value in str(link.get("title") or "") for link in main_options[:12])]
    if len(method_facets) > 1 and not any(value in work_item.source_span for value in method_facets):
        extra_hints.append("候选区分" + "/".join(method_facets[:4]) + "施工方法，请补充施工方法")
    material_facets = [value for value in ("钢管", "钢导管", "塑料管", "铜芯", "铝芯") if any(value in str(link.get("title") or "") for link in main_options[:30])]
    if len(material_facets) > 1 and not any(value in work_item.source_span for value in material_facets):
        extra_hints.append("候选区分" + "/".join(material_facets[:4]) + "材料类型，请补充材料类型")
    if work_item.object and "电缆" in work_item.object and "截面" not in work_item.source_span and any("截面" in str(link.get("title") or "") for link in main_options[:30]):
        extra_hints.append("候选涉及电缆截面分档，请补充电缆截面")
    if work_item.material and selected:
        material = _normalized_trade_text(work_item.material)
        if not any(material in _normalized_trade_text(str(link.get("title") or "")) for link in selected):
            extra_hints.append(f"本地关联定额未明确体现“{work_item.material}”，请确认材料处理口径")
            selected = []
    selected_main = next((value for value in selected if quota_role(str(value.get("title") or "")) == "main"), None)
    if selected_main and _requires_thickness_conversion(bill.get("unit"), selected_main.get("unit")) and _thickness_mm(work_item) is None:
        extra_hints.append("清单与定额计量维度需按厚度换算，请补充设计厚度")
    question_source = {**search_result, "hints": [*extra_hints, *(search_result.get("hints") or [])]}
    questions = _questions_for_item(work_item, question_source, selected or viable_links[:1], question_start)
    lines: list[QuotaSelection] = []
    for link in selected:
        role = quota_role(str(link.get("title") or ""))
        reasons = link.get("match_reasons") or ["由所选清单的本地关联表召回"]
        evidence = tuple(value for value in (references.get(str(link.get("record_id") or "")),) if value)
        factor = float(link["factor"]) if isinstance(link.get("factor"), (int, float)) else None
        converted_factor = _thickness_conversion_factor(bill.get("unit"), link.get("unit"), work_item) if role == "main" else None
        if converted_factor is not None:
            factor = converted_factor
        lines.append(QuotaSelection(
            record_id=str(link.get("quota_record_id") or ""),
            code=str(link.get("code") or ""),
            title=str(link.get("title") or ""),
            unit=str(link.get("unit") or ""),
            role=role,
            factor=factor,
            reason="；".join(str(value) for value in reasons[:2]),
            evidence_refs=evidence,
            source_link_record_id=str(link.get("record_id") or ""),
        ))

    status = "ready_for_review"
    if "不确定" in work_item.source_span and lines:
        status = "multiple_valid_options"
    elif questions:
        status = "needs_clarification"
    elif not lines:
        status = "no_reliable_match"
    match_level = "high" if status == "ready_for_review" and lines else "medium" if lines else "low"
    evidence_refs = [references.get(bill_id)] + [value for line in lines for value in line.evidence_refs]
    assumptions: list[str] = [] if links else ["本地关联表没有可验证定额组合，未将全文候选直接拼入方案。"]
    if selected_main and _requires_thickness_conversion(bill.get("unit"), selected_main.get("unit")):
        thickness = _thickness_mm(work_item)
        factor = _thickness_conversion_factor(bill.get("unit"), selected_main.get("unit"), work_item)
        if thickness is not None and factor is not None:
            assumptions.append(
                f"清单按{bill.get('unit') or '-'}、定额按{selected_main.get('unit') or '-'}计量，"
                f"已按{thickness:g}mm厚度换算，定额系数为{factor:g}。"
            )
    return PricingProposal(
        work_item_id=work_item.id,
        bill_record_id=bill_id,
        bill_code=str(bill.get("code") or ""),
        bill_title=str(bill.get("title") or ""),
        bill_unit=str(bill.get("unit") or ""),
        quota_lines=tuple(lines),
        assumptions=tuple(assumptions),
        unresolved_question_ids=tuple(value.id for value in questions),
        evidence_refs=tuple(dict.fromkeys(value for value in evidence_refs if value)),
        match_level=match_level,
        status=status,
    ), questions


def assemble_pricing_result(
    description: str,
    item_results: list[tuple[WorkItem, dict[str, Any]]],
    *,
    quota_edition: str,
    standard_edition: str,
    discipline: str | None,
    elapsed_ms: float | None = None,
) -> dict[str, Any]:
    copied_results = [(work_item, deepcopy(value)) for work_item, value in item_results]
    groups, references = _reference_items(copied_results)
    proposals: list[dict[str, Any]] = []
    questions: list[dict[str, Any]] = []
    for work_item, search_result in copied_results:
        proposal, item_questions = _assemble_proposal(work_item, search_result, references, len(questions) + 1)
        proposals.append(proposal.to_dict())
        questions.extend(value.to_dict() for value in item_questions)

    statuses = {value["status"] for value in proposals}
    if not proposals or statuses == {"no_reliable_match"}:
        decision_status = "no_reliable_match"
    elif "needs_clarification" in statuses:
        decision_status = "needs_clarification"
    elif "multiple_valid_options" in statuses:
        decision_status = "multiple_valid_options"
    else:
        decision_status = "ready_for_review"
    result: dict[str, Any] = {
        "analysis_version": "1",
        "query": description,
        "quota_edition": quota_edition,
        "standard_edition": standard_edition,
        "discipline": discipline,
        "work_items": [value.to_dict() for value, _result in copied_results],
        "work_item_results": [
            {"work_item_id": value.id, **search_result}
            for value, search_result in copied_results
        ],
        "clarification_questions": questions,
        "proposals": proposals,
        "decision_status": decision_status,
        "match_level": "high" if decision_status == "ready_for_review" else "medium" if proposals and decision_status != "no_reliable_match" else "low",
        "conditions": copied_results[0][1].get("conditions") if len(copied_results) == 1 else {},
        "timing": {"local_ms": round(float(elapsed_ms), 1)} if elapsed_ms is not None else {},
        "search_backend": "work_item_pipeline",
        "hints": list(dict.fromkeys(question["reason"] for question in questions)),
        **groups,
    }
    result["validation"] = validate_pricing_result(result)
    if not result["validation"]["valid"]:
        for proposal in result["proposals"]:
            if proposal["status"] == "ready_for_review":
                proposal["status"] = "no_reliable_match"
        result["decision_status"] = "no_reliable_match"
        result["match_level"] = "low"
    return result


def _lookup_tables(result: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    bills = {str(value.get("record_id") or ""): value for value in result.get("bills") or []}
    quotas = {str(value.get("record_id") or ""): value for value in result.get("quotas") or []}
    links: dict[tuple[str, str], dict[str, Any]] = {}
    for value in result.get("links") or []:
        bill_id = str(value.get("bill_record_id") or "")
        quota_id = str(value.get("quota_record_id") or "")
        if bill_id and quota_id:
            links[(bill_id, quota_id)] = value
            quotas.setdefault(quota_id, value)
    return bills, quotas, links


def _unit_measure(value: object) -> tuple[str, float]:
    unit = str(value or "").strip().lower().replace("㎡", "m2").replace("m²", "m2").replace("m³", "m3")
    unit = unit.replace(" ", "")
    match = re.match(r"^(?P<scale>[\d.]+)?(?P<unit>.*)$", unit)
    scale = float(match.group("scale") or 1) if match else 1.0
    base_unit = match.group("unit") if match else unit
    for dimension, aliases in {
        "area": ("m2", "平方米"),
        "volume": ("m3", "立方米"),
        "length": ("m", "米"),
        "mass": ("t", "吨", "kg", "千克"),
        "count": ("个", "套", "台", "组", "樘", "株", "根"),
    }.items():
        if base_unit in aliases:
            return dimension, scale
    return base_unit, scale


def _unit_dimension(value: object) -> str:
    return _unit_measure(value)[0]


def _thickness_mm(work_item: WorkItem) -> float | None:
    value = _attribute_values(work_item).get("thickness")
    try:
        thickness = float(value)
    except (TypeError, ValueError):
        return None
    return thickness if thickness > 0 else None


def _requires_thickness_conversion(bill_unit: object, quota_unit: object) -> bool:
    return {_unit_dimension(bill_unit), _unit_dimension(quota_unit)} == {"area", "volume"}


def _thickness_conversion_factor(bill_unit: object, quota_unit: object, work_item: WorkItem) -> float | None:
    thickness = _thickness_mm(work_item)
    if thickness is None or not _requires_thickness_conversion(bill_unit, quota_unit):
        return None
    bill_dimension, bill_scale = _unit_measure(bill_unit)
    quota_dimension, quota_scale = _unit_measure(quota_unit)
    thickness_m = thickness / 1000
    if bill_dimension == "volume" and quota_dimension == "area":
        factor = bill_scale / thickness_m / quota_scale
    else:
        factor = bill_scale * thickness_m / quota_scale
    return round(factor, 6)


def _result_thickness_mm(result: dict[str, Any], work_item_id: str) -> float | None:
    item = next((value for value in result.get("work_items") or [] if str(value.get("id") or "") == work_item_id), None)
    if not isinstance(item, dict):
        return None
    attribute = next((value for value in item.get("attributes") or [] if value.get("key") == "thickness"), None)
    if not isinstance(attribute, dict):
        return None
    try:
        thickness = float(attribute.get("value"))
    except (TypeError, ValueError):
        return None
    unit = str(attribute.get("unit") or "mm").lower()
    if unit in {"cm", "厘米"}:
        thickness *= 10
    elif unit in {"m", "米"}:
        thickness *= 1000
    return thickness if thickness > 0 else None


def validate_pricing_result(result: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    bills, quotas, links = _lookup_tables(result)
    work_item_ids = {str(value.get("id") or "") for value in result.get("work_items") or []}
    expected_discipline = result.get("discipline")
    quota_edition = str(result.get("quota_edition") or "")
    standard_edition = str(result.get("standard_edition") or "")
    for proposal in result.get("proposals") or []:
        work_item_id = str(proposal.get("work_item_id") or "")
        if work_item_id not in work_item_ids:
            errors.append(f"方案引用了不存在的施工事项：{work_item_id or '空'}")
        status = str(proposal.get("status") or "")
        if status not in VALID_PROPOSAL_STATUSES:
            errors.append(f"{work_item_id} 的方案状态不合法：{status or '空'}")
        bill_id = str(proposal.get("bill_record_id") or "")
        bill = bills.get(bill_id) if bill_id else None
        if bill_id and bill is None:
            errors.append(f"{work_item_id} 的清单记录不在本轮白名单：{bill_id}")
        if bill:
            if standard_edition and str(bill.get("edition") or "") != standard_edition:
                errors.append(f"{work_item_id} 的清单版本越界")
            if expected_discipline and bill.get("discipline") != expected_discipline:
                errors.append(f"{work_item_id} 的清单专业越界")
        seen: set[str] = set()
        main_count = 0
        for line in proposal.get("quota_lines") or []:
            record_id = str(line.get("record_id") or "")
            role = str(line.get("role") or "")
            if record_id not in quotas:
                errors.append(f"{work_item_id} 的定额记录不在本轮白名单：{record_id or '空'}")
                continue
            if record_id in seen:
                errors.append(f"{work_item_id} 重复加入定额：{record_id}")
            seen.add(record_id)
            if role not in VALID_QUOTA_ROLES:
                errors.append(f"{work_item_id} 的定额角色不合法：{role or '空'}")
            if role == "main":
                main_count += 1
            link = links.get((bill_id, record_id)) if bill_id else None
            if bill_id and link is None:
                errors.append(f"{work_item_id} 的清单与定额没有本地关联：{record_id}")
                continue
            if link:
                if quota_edition and str(link.get("quota_edition") or "") != quota_edition:
                    errors.append(f"{work_item_id} 的定额版本越界")
                if standard_edition and str(link.get("standard_edition") or link.get("edition") or "") != standard_edition:
                    errors.append(f"{work_item_id} 的关联清单版本越界")
                if expected_discipline and link.get("discipline") != expected_discipline:
                    errors.append(f"{work_item_id} 的定额专业越界")
                if link.get("conflicts"):
                    errors.append(f"{work_item_id} 含有条件冲突定额：{record_id}")
                bill_dimension = _unit_dimension(bill.get("unit")) if bill else ""
                quota_dimension = _unit_dimension(link.get("unit"))
                if role == "main" and bill_dimension and quota_dimension and bill_dimension != quota_dimension:
                    if {bill_dimension, quota_dimension} == {"area", "volume"}:
                        thickness = _result_thickness_mm(result, work_item_id)
                        pending_thickness = any(
                            value.get("work_item_id") == work_item_id and value.get("field") == "thickness"
                            for value in result.get("clarification_questions") or []
                            if isinstance(value, dict)
                        )
                        if thickness is not None:
                            warnings.append(f"{work_item_id} 的清单与主定额已按{thickness:g}mm厚度换算")
                        elif pending_thickness:
                            warnings.append(f"{work_item_id} 的清单与主定额需在补充厚度后换算")
                        else:
                            errors.append(f"{work_item_id} 的清单与主定额单位维度不一致，且缺少厚度换算依据")
                    else:
                        errors.append(f"{work_item_id} 的清单与主定额单位维度不一致")
        if proposal.get("quota_lines") and main_count != 1:
            errors.append(f"{work_item_id} 的定额组合必须且只能有一个主项")
        if status == "ready_for_review" and (not bill_id or not proposal.get("quota_lines")):
            errors.append(f"{work_item_id} 缺少通过复核所需的清单或主定额")
        if status == "needs_clarification" and not proposal.get("unresolved_question_ids"):
            warnings.append(f"{work_item_id} 标记待补条件，但没有结构化问题")
    return {"valid": not errors, "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings))}


def analyze_pricing_description(
    description: str,
    *,
    quota_edition: str = "2025",
    standard_edition: str = "2024",
    discipline: str | None = None,
    limit: int = 6,
    cancel_event: threading.Event | None = None,
    search_fn: SearchFunction | None = None,
) -> dict[str, Any]:
    if search_fn is None:
        from .catalog import search_catalog

        search_fn = search_catalog
    if not segment_description(description, discipline=discipline):
        raise ValueError("施工描述不能为空")
    started = time.perf_counter()

    def analyze_for(current_discipline: str | None) -> dict[str, Any]:
        item_results: list[tuple[WorkItem, dict[str, Any]]] = []
        for work_item in segment_description(description, discipline=current_discipline):
            if cancel_event is not None and cancel_event.is_set():
                from .catalog import CatalogSearchCancelled

                raise CatalogSearchCancelled("catalogue search cancelled")
            search_result = search_fn(
                work_item.search_text(),
                quota_edition=quota_edition,
                standard_edition=standard_edition,
                discipline=current_discipline,
                limit=limit,
                cancel_event=cancel_event,
            )
            # The first retrieval only finds candidate bills. Once a bill passes
            # the semantic gate, relation-driven retrieval loads its complete
            # quota set so database row order cannot hide a valid combination.
            selected_bill = select_bill_candidate(work_item, list(search_result.get("bills") or []))
            if selected_bill is not None and getattr(search_fn, "__module__", "") == "utils.catalog":
                from .catalog import load_bill_links

                search_result["links"] = load_bill_links(
                    [selected_bill],
                    quota_edition=quota_edition,
                    standard_edition=standard_edition,
                    discipline=current_discipline,
                )
            item_results.append((work_item, search_result))
        return assemble_pricing_result(
            description,
            item_results,
            quota_edition=quota_edition,
            standard_edition=standard_edition,
            discipline=current_discipline,
        )

    analysis = analyze_for(discipline)
    inferred_discipline = infer_discipline(description)
    if analysis.get("decision_status") == "no_reliable_match" and inferred_discipline and inferred_discipline != discipline:
        fallback = analyze_for(inferred_discipline)
        if fallback.get("decision_status") != "no_reliable_match" and any(value.get("bill_record_id") for value in fallback.get("proposals") or []):
            fallback["requested_discipline"] = discipline
            fallback["discipline_auto_switched"] = True
            fallback["discipline_switch_reason"] = (
                f"当前{_DISCIPLINE_LABELS.get(discipline, discipline or '所选')}专业没有可靠清单，"
                f"已按施工描述切换到{_DISCIPLINE_LABELS.get(inferred_discipline, inferred_discipline)}专业。"
            )
            analysis = fallback
    analysis["timing"] = {"local_ms": round((time.perf_counter() - started) * 1000, 1)}
    return analysis


def proposal_plain_text(result: dict[str, Any], *, confirmed_only: bool = False) -> str:
    work_items = {str(value.get("id") or ""): value for value in result.get("work_items") or []}
    lines = ["事项\t类型\t角色\t编码\t名称\t单位\t状态"]
    for proposal in result.get("proposals") or []:
        if confirmed_only and not proposal.get("confirmed"):
            continue
        work_item = work_items.get(str(proposal.get("work_item_id") or ""), {})
        span = str(work_item.get("source_span") or proposal.get("work_item_id") or "")
        status = _STATUS_LABELS.get(str(proposal.get("status") or ""), str(proposal.get("status") or ""))
        if proposal.get("bill_record_id"):
            lines.append("\t".join((span, "清单", "", str(proposal.get("bill_code") or ""), str(proposal.get("bill_title") or ""), str(proposal.get("bill_unit") or ""), status)))
        for quota in proposal.get("quota_lines") or []:
            lines.append("\t".join((span, "定额", _ROLE_LABELS.get(str(quota.get("role") or ""), str(quota.get("role") or "")), str(quota.get("code") or ""), str(quota.get("title") or ""), str(quota.get("unit") or ""), status)))
    return "\n".join(lines if len(lines) > 1 else [])


def merge_clarification_context(previous_result: dict[str, Any] | None, answer: str) -> tuple[str, str] | None:
    """Merge a short follow-up into the original WorkItem instead of searching it alone."""
    if not isinstance(previous_result, dict):
        return None
    questions = [value for value in previous_result.get("clarification_questions") or [] if isinstance(value, dict)]
    work_items = [value for value in previous_result.get("work_items") or [] if isinstance(value, dict)]
    reply = str(answer or "").strip()
    if not questions or not work_items or not reply or len(reply) > 80 or re.search(r"[；;。\n]", reply):
        return None
    question = questions[0]
    target_id = str(question.get("work_item_id") or "")
    spans: list[str] = []
    found = False
    for work_item in work_items:
        span = str(work_item.get("source_span") or "").strip()
        if str(work_item.get("id") or "") == target_id:
            span = f"{span}，{reply}"
            found = True
        if span:
            spans.append(span)
    if not found:
        return None
    return "；".join(spans), str(question.get("id") or "")
