from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any


@dataclass(frozen=True)
class QueryConditions:
    object_type: str | None = None
    soil_type: str | None = None
    depth_m: float | None = None
    distance_m: float | None = None
    method: str | None = None
    thickness_mm: float | None = None
    diameter_mm: float | None = None
    strength_grade: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_OBJECT_TERMS = ("沟槽", "管沟", "基坑", "地坑", "桩孔", "一般土方", "单独土方", "平整场地")


def _measurement(text: str, labels: str) -> float | None:
    match = re.search(rf"(?:{labels})\s*(?:为|约|约为|[:：=])?\s*(\d+(?:\.\d+)?)\s*(km|公里|千米|m|米|cm|厘米|mm|毫米)\b", text, re.I)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"km", "公里", "千米"}:
        return value * 1000
    if unit in {"cm", "厘米"}:
        return value / 100
    if unit in {"mm", "毫米"}:
        return value / 1000
    return value


def _measurement_mm(text: str, labels: str) -> float | None:
    value = _measurement(text, labels)
    return value * 1000 if value is not None else None


def parse_query_conditions(query: str) -> QueryConditions:
    text = re.sub(r"\s+", "", query or "")
    object_type = next((term for term in _OBJECT_TERMS if term in text), None)
    if re.search(r"(?:三类土|Ⅲ类土|坚土)", text, re.I):
        soil_type = "坚土"
    elif re.search(r"(?:四类土|Ⅳ类土|砂砾坚土)", text, re.I):
        soil_type = "砂砾坚土"
    elif re.search(r"(?:一类土|二类土|一二类土|Ⅰ类土|Ⅱ类土|普通土)", text, re.I):
        soil_type = "普通土"
    else:
        soil_type = None
    depth_m = _measurement(text, r"深度|挖深|槽深|坑深|开挖深度")
    distance_m = _measurement(text, r"运距|运输距离|弃土运距|取土运距")
    if "人工" in text:
        method = "人工"
    elif re.search(r"机械|挖掘机|装载机|推土机|铲运机|自卸车", text):
        method = "机械"
    else:
        method = None
    thickness_mm = _measurement_mm(text, r"厚度|板厚|壁厚|厚")
    diameter_mm = _measurement_mm(text, r"直径|管径|公称直径|外径")
    diameter_match = re.search(r"(?<![A-Za-z])DN\s*(\d+(?:\.\d+)?)", text, re.I)
    if diameter_mm is None and diameter_match:
        diameter_mm = float(diameter_match.group(1))
    strength_match = re.search(r"(?<![A-Za-z])((?:C\s*\d{2,3}|M\s*\d{1,3}|HRB\s*\d{3}))(?!\d)", text, re.I)
    strength_grade = re.sub(r"\s+", "", strength_match.group(1)).upper() if strength_match else None
    return QueryConditions(object_type=object_type, soil_type=soil_type, depth_m=depth_m, distance_m=distance_m, method=method, thickness_mm=thickness_mm, diameter_mm=diameter_mm, strength_grade=strength_grade)


def _distance_limit_m(title: str) -> float | None:
    match = re.search(r"运距\s*[≤<]\s*(\d+(?:\.\d+)?)\s*(km|公里|千米|m|米)(?![A-Za-z])", title, re.I)
    if not match:
        return None
    value = float(match.group(1))
    return value * 1000 if match.group(2).lower() in {"km", "公里", "千米"} else value


def _depth_limit_m(title: str) -> float | None:
    match = re.search(r"(?:槽深|坑深|深度|深)\s*[≤<]\s*(\d+(?:\.\d+)?)\s*(?:m|米)(?![A-Za-z])", title, re.I)
    return float(match.group(1)) if match else None


def _limit_mm(title: str, labels: str) -> float | None:
    match = re.search(rf"(?:{labels})[^\d]*(\d+(?:\.\d+)?)\s*(mm|毫米|cm|厘米|m|米)(?![A-Za-z])", title, re.I)
    if not match:
        return None
    value = float(match.group(1))
    return value * (10 if match.group(2).lower() in {"cm", "厘米"} else 1000 if match.group(2).lower() in {"m", "米"} else 1)


def rank_conditions(item: dict[str, Any], conditions: QueryConditions) -> tuple[float, list[str], list[str], list[str]]:
    title = str(item.get("title") or "")
    text = f"{title} {item.get('condition_text') or ''}"
    score = 0.0
    reasons: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []

    if conditions.object_type:
        if conditions.object_type in text:
            score += 28
            reasons.append(f"作业对象命中“{conditions.object_type}”")
        else:
            opposites = [term for term in _OBJECT_TERMS if term != conditions.object_type and term in title]
            if opposites:
                score -= 45
                conflicts.append(f"作业对象为“{opposites[0]}”，与“{conditions.object_type}”不一致")

    if conditions.soil_type:
        if conditions.soil_type in text:
            score += 26
            mapped = "（三类土映射）" if conditions.soil_type == "坚土" else ""
            reasons.append(f"土类命中“{conditions.soil_type}”{mapped}")
        elif conditions.soil_type == "坚土" and "普通土" in title:
            score -= 42
            conflicts.append("子目为普通土，用户条件为三类土/坚土")
        elif conditions.soil_type == "普通土" and ("坚土" in title or "砂砾坚土" in title):
            score -= 42
            conflicts.append(f"子目为{('砂砾坚土' if '砂砾坚土' in title else '坚土')}，用户条件为普通土")
    elif re.search(r"普通土|坚土|砂砾坚土", title):
        missing.append("未说明土类别")

    depth_limit = _depth_limit_m(title)
    if conditions.depth_m is not None:
        if depth_limit is not None:
            if conditions.depth_m <= depth_limit:
                score += 26 + max(0, 8 - (depth_limit - conditions.depth_m) * 2)
                reasons.append(f"深度 {conditions.depth_m:g}m 落在≤{depth_limit:g}m分档")
            else:
                score -= 55
                conflicts.append(f"深度 {conditions.depth_m:g}m 超过子目≤{depth_limit:g}m分档")
    elif depth_limit is not None:
        missing.append("未说明开挖深度")

    if conditions.method:
        is_mechanical = bool(re.search(r"机械|挖掘机|装载机|推土机|铲运机|自卸车", title))
        is_manual = "人工" in title
        if conditions.method == "人工" and is_manual:
            score += 18
            reasons.append("施工方法命中“人工”")
        elif conditions.method == "机械" and is_mechanical:
            score += 18
            reasons.append("施工方法命中“机械”")
        elif conditions.method == "人工" and is_mechanical:
            score -= 30
            conflicts.append("子目为机械施工，用户指定人工")
        elif conditions.method == "机械" and is_manual:
            score -= 30
            conflicts.append("子目为人工施工，用户指定机械")

    distance_limit = _distance_limit_m(title)
    if conditions.distance_m is not None and distance_limit is not None:
        if "每增运" in title:
            score += 14
            reasons.append("命中增运组合项，需与基础运距子目组合")
        elif conditions.distance_m <= distance_limit:
            score += 24
            reasons.append(f"运距 {conditions.distance_m:g}m 在≤{distance_limit:g}m范围内")
        else:
            score -= 46
            conflicts.append(f"运距 {conditions.distance_m:g}m 超过子目≤{distance_limit:g}m范围")
    elif conditions.distance_m is not None:
        if "挖" in title or conditions.object_type in title:
            score += 4
            missing.append(f"运距 {conditions.distance_m:g}m 需另行组合运输/增运子目")
    elif conditions.distance_m is None and distance_limit is not None:
        missing.append("未说明运输距离")

    if conditions.thickness_mm is not None:
        thickness_limit = _limit_mm(title, r"厚度|板厚|壁厚")
        if thickness_limit is not None:
            if abs(thickness_limit - conditions.thickness_mm) < 0.01:
                score += 24
                reasons.append(f"厚度 {conditions.thickness_mm:g}mm 命中")
            elif "每增减" in title:
                score += 12
                reasons.append("厚度为增减调整项，需与基础厚度子目组合")
        elif "厚度" in title:
            missing.append("需确认定额基础厚度分档")

    if conditions.diameter_mm is not None:
        diameter_limit = _limit_mm(title, r"直径|管径|公称直径|外径")
        if diameter_limit is not None:
            if conditions.diameter_mm <= diameter_limit:
                gap = diameter_limit - conditions.diameter_mm
                score += 18 + max(0, 12 - gap / 2)
                reasons.append(f"直径 {conditions.diameter_mm:g}mm 在≤{diameter_limit:g}mm范围内" + ("，精确命中分档" if gap == 0 else ""))
            else:
                score -= 32
                conflicts.append(f"直径 {conditions.diameter_mm:g}mm 超过子目≤{diameter_limit:g}mm范围")
        else:
            score -= 12
            missing.append(f"子目未标直径分档，需核对 DN{conditions.diameter_mm:g} 适用规格")
    elif _limit_mm(title, r"直径|管径|公称直径|外径") is not None:
        missing.append("未说明管径或直径分档")

    if conditions.strength_grade:
        title_grades = {re.sub(r"\s+", "", value).upper() for value in re.findall(r"(?:C\s*\d{2,3}|M\s*\d{1,3}|HRB\s*\d{3})", title, re.I)}
        if conditions.strength_grade in title_grades:
            score += 22
            reasons.append(f"强度等级命中“{conditions.strength_grade}”")
        elif title_grades:
            score -= 24
            conflicts.append(f"强度等级为{','.join(sorted(title_grades))}，与{conditions.strength_grade}不一致")
    return score, reasons, list(dict.fromkeys(missing)), list(dict.fromkeys(conflicts))
