from __future__ import annotations

from dataclasses import replace
import re

from .pricing_models import NegativeConstraint, TypedAttribute, WorkItem
from .query_parse import normalize_trade_description


_ACTION_TERMS = (
    "铺贴", "铺设", "安装", "敷设", "浇筑", "砌筑", "抹灰", "回填", "夯实", "开挖",
    "拆除", "修复", "新建", "涂刷", "喷涂", "绑扎", "栽植", "运输", "保护", "找平",
)
_OBJECT_TERMS = (
    "防水层", "防水", "涂料", "抹灰", "管道保温", "风管保温", "保温层", "保温",
    "保护层", "找平层", "垫层", "基层", "面层", "回填土", "灰土", "沟槽土方",
    "基坑土方", "土方", "脚手架", "模板", "配管", "电缆", "风管", "管道", "混凝土", "砖墙",
    "乔木", "灌木", "路面", "钢筋", "墙", "柱", "梁", "板",
)
_LOCATIONS = (
    "地下室外墙外侧", "地下室外墙", "地下室", "屋面", "楼地面", "基础", "墙面", "外墙", "内墙",
    "室外", "室内", "吊顶内", "管井内", "埋地", "架空", "墙内", "板内", "外侧", "内侧",
)
_MATERIALS = (
    "SBS改性沥青防水卷材", "水泥稳定碎石", "SBS防水卷材", "商品混凝土", "水泥砂浆", "三七灰土",
    "混合砂浆", "防水卷材", "改性沥青", "镀锌钢板", "橡塑", "挤塑板", "实心砖",
    "JDG", "KBG", "聚氨酯", "聚乙烯", "PVC", "PPR", "钢导管", "钢管", "涂料", "混凝土", "碎石", "砂浆", "灰土", "SBS",
)
_CONDITION_ONLY_RE = re.compile(
    r"^(?:一二三四类土|[一二三四]类土|普通土|坚土|砂砾坚土|人工|机械|机械开挖|人工开挖|"
    r"深(?:度)?\s*\d|槽深\s*\d|坑深\s*\d|运距\s*\d|DN\s*\d|直径\s*\d|(?:墙厚|板厚|壁厚|厚度|厚)\s*\d|"
    r"\d+(?:\.\d+)?\s*(?:m|米|mm|毫米|cm|厘米|km|公里))(?:.*)$",
    re.I,
)
_CONTINUATION_RE = re.compile(r"^(?:人工|机械|泵送|现浇|商品|现场|热熔|自粘|湿铺|干铺)?(?:夯实|压实|振捣)$")


def _first_term(text: str, terms: tuple[str, ...]) -> str:
    return next((value for value in terms if value.lower() in text.lower()), "")


def _number_source(text: str, pattern: str) -> tuple[float, str, str] | None:
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    groups = match.groupdict()
    raw_value = groups.get("value") or groups.get("value2")
    if raw_value is None:
        return None
    value = float(raw_value)
    unit = (groups.get("unit") or groups.get("unit2") or "mm").lower()
    normalized_unit = unit
    if unit in {"毫米", "厚"}:
        normalized_unit = "mm"
    elif unit in {"厘米"}:
        normalized_unit = "cm"
    elif unit in {"米"}:
        normalized_unit = "m"
    elif unit in {"公里", "千米"}:
        normalized_unit = "km"
    return value, normalized_unit, match.group(0)


def _add_attribute(target: list[TypedAttribute], key: str, value, unit: str | None, source: str) -> None:
    if any(item.key == key for item in target):
        return
    target.append(TypedAttribute(key=key, value=value, unit=unit, source=source))


def extract_work_item(source_span: str, *, item_id: str, discipline: str | None = None) -> WorkItem:
    text = re.sub(r"\s+", " ", str(source_span or "")).strip(" ，,；;。\n\t")
    analysis_text = normalize_trade_description(text)
    attributes: list[TypedAttribute] = []

    thickness = _number_source(
        analysis_text,
        r"(?:(?:厚度|板厚|壁厚|厚)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|m|米)?|"
        r"(?P<value2>\d+(?:\.\d+)?)\s*(?P<unit2>mm|毫米|cm|厘米|m|米|厚)(?=\s*(?:SBS|防水|水泥|砂浆|混凝土|灰土|保温|保护|基层|面层)))",
    )
    if thickness is None:
        fallback = re.search(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|m|米)(?=\s*(?:SBS|防水|水泥|砂浆|混凝土|灰土|保温|保护|基层|面层))", analysis_text, re.I)
        if fallback:
            thickness = _number_source(fallback.group(0), r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米|m|米)")
    if thickness:
        value, unit, source = thickness
        if unit == "cm":
            value, unit = value * 10, "mm"
        elif unit == "m":
            value, unit = value * 1000, "mm"
        _add_attribute(attributes, "thickness", value, unit, source)

    diameter = _number_source(analysis_text, r"(?:DN|土球(?:直径)?|直径|管径|公称直径|外径|JDG|KBG|SC|PVC)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米)?")
    if diameter:
        diameter_value, diameter_unit, diameter_source = diameter
        if diameter_unit == "cm":
            diameter_value *= 10
        elif diameter_unit == "m":
            diameter_value *= 1000
        _add_attribute(attributes, "diameter", diameter_value, "mm", diameter_source)

    strength = re.search(r"(?<![A-Za-z])(?:C\s*\d{2,3}|M\s*\d{1,3}|HRB\s*\d{3})(?!\d)", analysis_text, re.I)
    if strength:
        _add_attribute(attributes, "strength_grade", re.sub(r"\s+", "", strength.group(0)).upper(), None, strength.group(0))

    layer = re.search(r"(?P<count>\d+|[一二两三四五六七八九十]+)\s*(?:道|层|遍)", analysis_text)
    if layer:
        chinese = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        raw = layer.group("count")
        count = int(raw) if raw.isdigit() else chinese.get(raw, 2)
        _add_attribute(attributes, "layers", count, "layer", layer.group(0))

    for key, pattern, unit in (
        ("depth", r"(?:深度|挖深|槽深|坑深|开挖深度|深)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>m|米|cm|厘米|mm|毫米)", "m"),
        ("distance", r"(?:运距|运输距离|弃土运距|取土运距)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>km|公里|千米|m|米)", "m"),
    ):
        measured = _number_source(analysis_text, pattern)
        if not measured:
            continue
        value, source_unit, source = measured
        if key == "depth" and source_unit == "cm":
            value /= 100
        elif key == "depth" and source_unit == "mm":
            value /= 1000
        elif key == "distance" and source_unit == "km":
            value *= 1000
        _add_attribute(attributes, key, value, unit, source)

    for value, label in (("manual", "人工"), ("mechanical", "机械"), ("pump", "泵送"), ("cast_in_place", "现浇"), ("commercial", "商品混凝土"), ("hot_melt", "热熔"), ("self_adhesive", "自粘")):
        if label in analysis_text:
            _add_attribute(attributes, "method" if value in {"manual", "mechanical"} else value, value, None, label)

    soil_match = re.search(r"(?:一二类土|[一二三四]类土|普通土|坚土|砂砾坚土)", analysis_text)
    if soil_match:
        _add_attribute(attributes, "soil_type", soil_match.group(0), None, soil_match.group(0))

    negative_constraints: list[NegativeConstraint] = []
    for key, label_pattern in (
        ("transport", r"外运|运输|运土"),
        ("protection_layer", r"保护层"),
        ("scaffold", r"脚手架"),
        ("formwork", r"模板"),
        ("loading", r"装卸"),
    ):
        match = re.search(rf"(?:不含|不做|不计|无需|已有)\s*(?:[^，,；;。]{{0,8}})?(?:{label_pattern})", analysis_text)
        if match:
            negative_constraints.append(NegativeConstraint(key=key, source=match.group(0)))

    return WorkItem(
        id=item_id,
        source_span=text,
        discipline=discipline,
        action=_first_term(analysis_text, _ACTION_TERMS),
        object=_first_term(analysis_text, _OBJECT_TERMS),
        location=_first_term(analysis_text, _LOCATIONS),
        material=_first_term(analysis_text, _MATERIALS),
        attributes=tuple(attributes),
        negative_constraints=tuple(negative_constraints),
        confidence_level="high" if (_first_term(analysis_text, _OBJECT_TERMS) and (_first_term(analysis_text, _ACTION_TERMS) or _first_term(analysis_text, _MATERIALS))) else "medium",
    )


def _starts_new_item(fragment: str) -> bool:
    compact = re.sub(r"\s+", "", fragment)
    if not compact or _CONDITION_ONLY_RE.match(compact) or _CONTINUATION_RE.match(compact):
        return False
    objects = sum(term in compact for term in _OBJECT_TERMS)
    actions = sum(term in compact for term in _ACTION_TERMS)
    materials = sum(term.lower() in compact.lower() for term in _MATERIALS)
    return bool(objects and (actions or materials or re.search(r"\d+(?:\.\d+)?(?:mm|毫米|cm|厘米|厚)", compact)))


def segment_description(description: str, *, discipline: str | None = None) -> list[WorkItem]:
    text = re.sub(r"\r\n?", "\n", str(description or "")).strip()
    if not text:
        return []
    tokens = [value for value in re.split(r"([，,；;。\n])", text) if value]
    spans: list[str] = []
    current = ""
    previous_separator = ""
    for token in tokens:
        if re.fullmatch(r"[，,；;。\n]", token):
            previous_separator = token
            continue
        fragment = token.strip()
        if not fragment:
            continue
        strong_boundary = previous_separator in {"；", ";", "。", "\n"}
        if current and (strong_boundary or _starts_new_item(fragment)):
            spans.append(current.strip(" ，,"))
            current = fragment
        else:
            current = f"{current}，{fragment}" if current else fragment
        previous_separator = ""
    if current:
        spans.append(current.strip(" ，,"))
    if not spans:
        spans = [text]

    items: list[WorkItem] = []
    inherited_location = ""
    for index, span in enumerate(spans[:8], start=1):
        item = extract_work_item(span, item_id=f"W{index}", discipline=discipline)
        if item.location:
            inherited_location = item.location
        elif inherited_location:
            item = replace(item, location=inherited_location)
        items.append(item)
    return items
