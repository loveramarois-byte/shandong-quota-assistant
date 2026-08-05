"""Presentation adapter for beginner-friendly AI pricing suggestions."""
from __future__ import annotations

import re
from typing import Any


_ATTRIBUTE_LABELS = {
    "thickness": "材料厚度",
    "diameter": "管径",
    "strength_grade": "强度等级",
    "method": "施工方式",
    "pump": "混凝土输送",
    "cast_in_place": "构件做法",
    "hot_melt": "施工方式",
    "self_adhesive": "施工方式",
}

_QUESTION_LABELS = {
    "method": "施工方式",
    "material": "材料类型",
    "material_application": "材料处理方式",
    "location": "使用部位",
    "soil_type": "土类别",
    "depth": "施工深度",
    "distance": "运输距离",
    "thickness": "材料厚度",
    "diameter": "管径",
    "plant_spec": "苗木规格",
}

_METHOD_OPTIONS = {
    "热熔法": ("使用喷灯加热粘贴", "通常先加热卷材底面，再粘贴到基层。"),
    "冷粘法": ("使用胶粘剂粘贴", "通常不使用明火，通过胶粘剂完成粘贴。"),
    "自粘法": ("撕开隔离膜后直接粘贴", "卷材自带粘结层，通常不需要喷灯加热。"),
    "热风焊接法": ("使用热风设备焊接", "使用热风设备处理卷材或搭接位置。"),
    "明配": ("管线沿墙面或顶面安装", "安装完成后通常可以直接看到管线。"),
    "暗配": ("管线埋入墙体或楼板", "安装完成后管线通常被饰面或结构遮蔽。"),
    "人工": ("主要由人工完成施工", "用于区分人工与机械施工对应的定额。"),
    "机械": ("主要使用机械完成施工", "用于区分机械与人工施工对应的定额。"),
}


def option_presentation(value: str) -> dict[str, str]:
    professional_name = str(value or "").strip() or "未获取到"
    title, description = _METHOD_OPTIONS.get(professional_name, (professional_name, "选择后会重新匹配对应的清单与定额。"))
    return {
        "value": professional_name,
        "title": title,
        "professional_name": professional_name,
        "description": description,
        "display": title if title == professional_name else f"{title}  ·  {professional_name}",
    }


def _text(value: Any, fallback: str = "未获取到") -> str:
    cleaned = str(value or "").strip()
    return cleaned or fallback


def _question_label(question: dict[str, Any] | None) -> str:
    field = str((question or {}).get("field") or "")
    return _QUESTION_LABELS.get(field, "关键信息")


def _ai_note(text: str, *, needs_confirmation: bool) -> str:
    match = re.search(r"(?:^|\n)#{1,3}\s*结论\s*\n(?P<body>.*?)(?=\n#{1,3}\s|\Z)", str(text or ""), re.S)
    body = match.group("body") if match else ""
    line = next((value.strip().lstrip("-• ") for value in body.splitlines() if value.strip()), "")
    line = re.sub(r"\[R\d+\]", "", line).strip(" 。")
    if needs_confirmation:
        return "确认缺少的信息后，我会重新生成对应的套价方案。"
    if line:
        return line + "。"
    return "已基于本地清单与定额候选完成复核。"


def _reason_rows(result: dict[str, Any], question: dict[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(label: str, value: Any, status: str = "confirmed") -> None:
        cleaned = str(value or "").strip()
        key = (label, cleaned)
        if not cleaned or key in seen:
            return
        seen.add(key)
        rows.append({"label": label, "value": cleaned, "status": status})

    for item in result.get("work_items") or []:
        if not isinstance(item, dict):
            continue
        add("使用部位", item.get("location"))
        add("材料类型", item.get("material"))
        for attribute in item.get("attributes") or []:
            if not isinstance(attribute, dict):
                continue
            label = _ATTRIBUTE_LABELS.get(str(attribute.get("key") or ""))
            if label:
                add(label, attribute.get("source") or attribute.get("value"))
    conditions = result.get("conditions") or {}
    add("施工方式", conditions.get("method"))
    if question:
        add(_question_label(question), "尚未确认", "missing")
    return rows[:6]


def _recommendation_headline(
    result: dict[str, Any],
    *,
    fallback_name: str,
    needs_confirmation: bool,
    question: dict[str, Any] | None,
) -> str:
    item = next((value for value in result.get("work_items") or [] if isinstance(value, dict)), {})
    location = str(item.get("location") or "").strip()
    object_name = str(item.get("object") or "").strip()
    material = str(item.get("material") or "").strip()
    attributes = [value for value in item.get("attributes") or [] if isinstance(value, dict)]
    thickness = next(
        (str(value.get("source") or value.get("value") or "").strip() for value in attributes if value.get("key") == "thickness"),
        "",
    )
    method = str((result.get("conditions") or {}).get("method") or "").strip()
    if not method:
        method = next(
            (
                str(value.get("source") or "").strip()
                for value in attributes
                if value.get("key") in {"method", "pump", "cast_in_place", "hot_melt", "self_adhesive"}
            ),
            "",
        )
    if method == "热熔":
        method = "热熔法"
    elif method == "自粘":
        method = "自粘法"

    material_phrase = " ".join(value for value in (thickness, material) if value)
    if not location and object_name and object_name not in material_phrase:
        material_phrase = f"{material_phrase}{object_name}" if material_phrase else object_name
    if location and material_phrase:
        recommendation = f"推荐{location}采用 {material_phrase}"
    elif material_phrase:
        recommendation = f"推荐采用 {material_phrase}"
    elif location:
        recommendation = f"已找到{location}对应的“{fallback_name}”候选"
    else:
        recommendation = f"已找到“{fallback_name}”候选"

    if needs_confirmation:
        return f"{recommendation}；还需要确认{_question_label(question)}。"
    if method:
        return f"{recommendation}，按{method}施工。"
    return recommendation + "。"


def build_ai_suggestion_view_model(text: str, result: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(result or {})
    proposals = [value for value in payload.get("proposals") or [] if isinstance(value, dict)]
    questions = [value for value in payload.get("clarification_questions") or [] if isinstance(value, dict)]
    proposal = proposals[0] if proposals else {}
    question = questions[0] if questions else None
    quota_lines = [value for value in proposal.get("quota_lines") or [] if isinstance(value, dict)]
    review_candidates = [value for value in proposal.get("review_candidates") or [] if isinstance(value, dict)]
    quotas = quota_lines or review_candidates[:3]
    status = str(proposal.get("status") or payload.get("decision_status") or "")
    needs_confirmation = bool(question) or status == "needs_clarification"
    bill_title = _text(proposal.get("bill_title"))
    quota_title = _text((quotas[0] if quotas else {}).get("title"))

    if needs_confirmation:
        state = "needs_confirmation"
        state_label = f"还需要确认 1 项信息" if question else "还需要补充信息"
        headline = _recommendation_headline(
            payload,
            fallback_name=bill_title,
            needs_confirmation=True,
            question=question,
        )
    elif status in {"ready_for_review", "multiple_valid_options"} or quota_lines:
        state = "ready"
        state_label = "方案已生成"
        headline = _recommendation_headline(
            payload,
            fallback_name=bill_title,
            needs_confirmation=False,
            question=None,
        )
    elif proposal.get("bill_title"):
        state = "partial"
        state_label = "已找到清单，定额待确认"
        headline = f"已找到清单“{bill_title}”，但暂未确定对应定额。"
    else:
        state = "empty"
        state_label = "暂时无法生成建议"
        headline = "当前描述中还缺少可用于确定套价方案的信息。"

    options = [option_presentation(value) for value in (question or {}).get("options") or []]
    bill = {
        "name": bill_title,
        "code": _text(proposal.get("bill_code")),
        "unit": _text(proposal.get("bill_unit")),
        "sources": "、".join(str(value) for value in proposal.get("evidence_refs") or []) or "未获取到",
    }
    quota_items = [
        {
            "name": _text(value.get("title")),
            "code": _text(value.get("code")),
            "unit": _text(value.get("unit")),
            "sources": "、".join(str(ref) for ref in value.get("evidence_refs") or []) or "未获取到",
            "is_candidate": not bool(quota_lines),
        }
        for value in quotas
    ]
    return {
        "state": state,
        "state_label": state_label,
        "headline": headline,
        "note": _ai_note(text, needs_confirmation=needs_confirmation),
        "reasons": _reason_rows(payload, question),
        "question": {
            "id": str((question or {}).get("id") or ""),
            "label": _question_label(question),
            "prompt": str((question or {}).get("question") or ""),
            "options": options,
        }
        if question
        else None,
        "bill": bill,
        "quotas": quota_items,
        "has_details": bool(proposal),
    }
