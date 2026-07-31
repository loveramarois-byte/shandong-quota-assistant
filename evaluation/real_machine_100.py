from __future__ import annotations

"""Repeatable Windows acceptance drill for the full local catalogue.

The suite deliberately mixes real catalogue searches with the non-network
states a first-time user reaches in the desktop app.  It is not an accuracy
certificate: exact pricing still depends on project conditions and review.
"""

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import ai_connection_state, centered_content_padding, initial_window_bounds
from components.message import logical_wrap_width
from components.result import proposal_decision_summary
from components.scrollable import normalized_wheel_pixels, pixel_scroll_fraction
from themes.tokens import DARK, LIGHT
from utils.ai_providers import provider_config
from utils.catalog import library_stats, warm_search
from utils.paths import APP_VERSION, catalog_manifest_path, database_path, resource_path
from utils.pricing_pipeline import analyze_pricing_description, proposal_plain_text
from utils.query_parse import parse_query_conditions
from utils.settings import sanitize_settings
from utils.work_items import segment_description


@dataclass(frozen=True)
class DrillCase:
    id: str
    category: str
    title: str
    runner: str
    data: dict[str, Any]


def _pricing_cases() -> list[DrillCase]:
    raw: list[tuple[str, str, str, str | None, str | None]] = [
        # 建筑：高频主体、装饰、防水与土方
        ("建筑", "屋面SBS改性沥青卷材防水3mm，两道，热熔", "building", "010902001-000", "9-2-10"),
        ("建筑", "地下室外墙SBS卷材防水4mm，热熔", "building", "010903001-000", None),
        ("建筑", "楼地面聚氨酯涂膜防水2mm", "building", "010904002-000", None),
        ("建筑", "基础C15混凝土垫层100mm厚", "building", "010501001-000", "2-1-28"),
        ("建筑", "楼地面C15细石混凝土垫层80mm厚", "building", None, None),
        ("建筑", "人工挖沟槽土方，三类土，深度2.5m", "building", None, None),
        ("建筑", "机械挖基坑土方，普通土，深度3m", "building", None, None),
        ("建筑", "土方回填，机械夯实", "building", None, None),
        ("建筑", "平整场地", "building", None, None),
        ("建筑", "M5混合砂浆砌筑240mm实心砖墙", "building", None, None),
        ("建筑", "现浇C30混凝土矩形柱", "building", None, None),
        ("建筑", "现浇C30混凝土有梁板", "building", None, None),
        ("建筑", "HRB400钢筋直径20mm绑扎", "building", None, None),
        ("建筑", "外墙20mm厚水泥砂浆抹灰", "building", None, None),
        ("建筑", "内墙乳胶漆两遍", "building", None, None),
        ("建筑", "外墙80mm挤塑板保温", "building", None, None),
        ("建筑", "屋面水泥砂浆找平层20mm", "building", None, None),
        ("建筑", "楼地面水泥砂浆面层20mm", "building", None, None),
        ("建筑", "现浇混凝土梁模板", "building", None, None),
        ("建筑", "外脚手架搭设", "building", None, None),
        ("建筑", "拆除240mm砖墙", "building", None, None),
        ("建筑", "基础三七灰土垫层300mm厚", "building", None, None),
        ("建筑", "散水C20混凝土100mm厚", "building", None, None),
        ("建筑", "预制混凝土过梁安装", "building", None, None),
        ("建筑", "010501001", "building", "010501001-000", None),
        # 安装：电气、给排水、消防、通风
        ("安装", "JDG20电气配管，砖混结构暗配", "installation", "030412001-000", "4-12-8"),
        ("安装", "KBG16电气配管，吊顶内明配", "installation", "030412001-000", None),
        ("安装", "PVC20电线管暗配", "installation", "030412001-000", None),
        ("安装", "BV2.5平方铜芯线管内穿线", "installation", None, None),
        ("安装", "YJV电力电缆5×16敷设", "installation", None, None),
        ("安装", "室内PPR给水管DN25热熔连接", "installation", None, None),
        ("安装", "室内PVC排水管DN110粘接", "installation", None, None),
        ("安装", "镀锌钢管DN100消防管道安装，沟槽连接", "installation", None, None),
        ("安装", "消火栓箱安装", "installation", None, None),
        ("安装", "自动喷淋喷头安装", "installation", None, None),
        ("安装", "桥架300×100安装", "installation", None, None),
        ("安装", "配电箱安装，暗装", "installation", None, None),
        ("安装", "矩形镀锌钢板风管安装", "installation", None, None),
        ("安装", "橡塑管道保温30mm厚", "installation", None, None),
        ("安装", "LED吸顶灯安装", "installation", None, None),
        # 市政：道路、排水、构筑物
        ("市政", "道路水泥稳定碎石基层18cm厚", "municipal", "040202014-000", "2-1-18"),
        ("市政", "沥青混凝土路面4cm厚", "municipal", None, None),
        ("市政", "级配碎石基层20cm厚", "municipal", None, None),
        ("市政", "道路混凝土侧石安装", "municipal", None, None),
        ("市政", "市政雨水管道DN600铺设", "municipal", None, None),
        ("市政", "砖砌圆形雨水检查井", "municipal", None, None),
        ("市政", "道路机械挖沟槽土方，三类土，深度3m", "municipal", None, None),
        ("市政", "人行道透水砖铺设", "municipal", None, None),
        ("市政", "路床整形碾压", "municipal", None, None),
        ("市政", "道路标线施工", "municipal", None, None),
        # 园林：苗木、地被、园路与养护
        ("园林", "栽植香樟，土球直径80cm", "landscape", "050103001-000", "1-2-32"),
        ("园林", "栽植乔木，裸根，胸径8cm", "landscape", "050103001-000", None),
        ("园林", "栽植灌木，冠幅1.2m", "landscape", None, None),
        ("园林", "铺种草坪", "landscape", None, None),
        ("园林", "栽植绿篱，高度80cm", "landscape", None, None),
        ("园林", "整理绿化用地", "landscape", None, None),
        ("园林", "园路透水砖铺装", "landscape", None, None),
        ("园林", "树木支撑，三脚桩", "landscape", None, None),
        ("园林", "乔木养护一年", "landscape", None, None),
        ("园林", "伐除胸径20cm乔木", "landscape", None, None),
        # 小白常见输入：口语、不完整条件、一次多个事项
        ("小白", "做防水", "building", None, None),
        ("小白", "屋顶防水，材料还没定", "building", None, None),
        ("小白", "垫层100厚", "building", None, None),
        ("小白", "基础下面浇一层C15素混凝土，10公分", "building", "010501001-000", "2-1-28"),
        ("小白", "砖墙", "building", None, None),
        ("小白", "挖沟槽，深2.5米，不知道土类", "building", None, None),
        ("小白", "电线管埋墙里，20的JDG", "installation", "030412001-000", "4-12-8"),
        ("小白", "卫生间排水管110PVC", "installation", None, None),
        ("小白", "道路基层18公分水稳", "municipal", "040202014-000", "2-1-18"),
        ("小白", "种一棵土球80公分的香樟", "landscape", "050103001-000", "1-2-32"),
        ("小白", "屋面防水；外墙保温80mm；内墙刷乳胶漆", "building", None, None),
        ("小白", "C30柱子和梁板一起浇", "building", None, None),
        ("小白", "只知道清单编码030412001", "installation", "030412001-000", None),
        ("小白", "不知道该选哪个专业的防水", "building", None, None),
        ("小白", "人工挖土，不外运", "building", None, None),
    ]
    cases: list[DrillCase] = []
    for index, (group, query, discipline, bill, quota) in enumerate(raw, start=1):
        data: dict[str, Any] = {
            "query": query,
            "discipline": discipline,
            "expected_bill": bill,
            "expected_quota": quota,
        }
        if query == "屋顶防水，材料还没定":
            data.update(expected_status="needs_clarification", expected_question_field="material")
        cases.append(DrillCase(
            id=f"P{index:03d}",
            category=f"实际检索/{group}",
            title=query,
            runner="pricing",
            data=data,
        ))
    return cases


def _state_cases() -> list[DrillCase]:
    checks: list[tuple[str, str, Callable[[], tuple[bool, str]]]] = [
        ("AI/未连接", "未配置 AI 时仍明确保留本地模式", lambda: (ai_connection_state({"ai_enabled": False})[0] is False, ai_connection_state({"ai_enabled": False})[1])),
        ("AI/DeepSeek", "DeepSeek 连接状态可读", lambda: (ai_connection_state({"ai_enabled": True, "ai_provider": "deepseek", "ai_model": "deepseek-chat"})[0], ai_connection_state({"ai_enabled": True, "ai_provider": "deepseek", "ai_model": "deepseek-chat"})[1])),
        ("AI/智谱", "智谱连接状态可读", lambda: ("智谱" in provider_config("zhipu").label, provider_config("zhipu").label)),
        ("AI/ccSwitch", "ccSwitch 连接状态可读", lambda: ("ccSwitch" in provider_config("ccswitch").label, provider_config("ccswitch").label)),
        ("设置/默认专业", "小白默认不会落入全部专业", lambda: (sanitize_settings({"discipline": "全部专业"})["discipline"] == "建筑", sanitize_settings({"discipline": "全部专业"})["discipline"])),
        ("设置/模型", "关闭 AI 时清理模型误导", lambda: (sanitize_settings({"ai_enabled": False, "ai_model": "x"})["ai_enabled"] is False, "AI 已关闭")),
        ("输入/DN", "DN25 可提取管径", lambda: (parse_query_conditions("给水管DN25").diameter_mm == 25, str(parse_query_conditions("给水管DN25").diameter_mm))),
        ("输入/厚度", "18cm 可提取为 180mm", lambda: (parse_query_conditions("基层厚度18cm").thickness_mm == 180, str(parse_query_conditions("基层厚度18cm").thickness_mm))),
        ("输入/分项", "三条口语事项可正确拆分", lambda: (len(segment_description("屋面防水；外墙保温；内墙刷漆", discipline="building")) == 3, str(len(segment_description("屋面防水；外墙保温；内墙刷漆", discipline="building"))))),
        ("输入/原文", "施工描述原文不被改写丢失", lambda: (segment_description("JDG20电气配管暗配", discipline="installation")[0].source_span == "JDG20电气配管暗配", segment_description("JDG20电气配管暗配", discipline="installation")[0].source_span)),
        ("结果/结论", "首屏结论优先给主清单与主定额", _check_result_summary),
        ("结果/导出", "本地方案可生成可复制文本", _check_plain_export),
        ("布局/窗口", "150% DPI 初始窗口不重复缩放", lambda: (initial_window_bounds(2560, 1440, 1.5)[:2] == (1360, 860), str(initial_window_bounds(2560, 1440, 1.5)[:2]))),
        ("布局/窄窗", "窄窗口保留最小内容边距", lambda: (centered_content_padding(980, LIGHT.sidebar_width, LIGHT.content_max_width) >= 20, str(centered_content_padding(980, LIGHT.sidebar_width, LIGHT.content_max_width)))),
        ("布局/长文", "长结果在高 DPI 下限制可读行宽", lambda: (logical_wrap_width(932, 1.5) == 600, str(logical_wrap_width(932, 1.5)))),
        ("滚动/标准滚轮", "标准滚轮步长稳定", lambda: (normalized_wheel_pixels(-120) > 0, str(normalized_wheel_pixels(-120)))),
        ("滚动/高精度滚轮", "高精度滚轮保留细粒度", lambda: (normalized_wheel_pixels(30) == -14, str(normalized_wheel_pixels(30)))),
        ("滚动/边缘", "滚动到边缘时停止并允许父容器接管", lambda: (pixel_scroll_fraction((0.0, 0.25), -56, 250) is None, str(pixel_scroll_fraction((0.0, 0.25), -56, 250)))),
        ("主题/浅色", "浅色主题不使用纯白页面背景", lambda: (LIGHT.colors.background.upper() != "#FFFFFF", LIGHT.colors.background)),
        ("主题/深色", "深色主题不使用纯黑页面背景", lambda: (DARK.colors.background.upper() != "#000000", DARK.colors.background)),
        ("主题/字号", "正文与辅助文字达到可读下限", lambda: (LIGHT.typography.body >= 14 and LIGHT.typography.caption >= 11, f"{LIGHT.typography.body}/{LIGHT.typography.caption}")),
        ("资源/字体", "Inter 四个字重随包提供", lambda: (all(resource_path("assets", "fonts", f"Inter-{weight}.ttf").exists() for weight in ("Regular", "Medium", "SemiBold", "Bold")), "Inter")),
        ("资源/图标", "核心操作使用 SVG 图标", lambda: (all(resource_path("assets", "icons", f"{name}.svg").exists() for name in ("send", "copy", "settings", "plus")), "SVG")),
        ("运行/数据库", "完整结构化资料库可读", lambda: (database_path().exists() and database_path().stat().st_size > 100_000_000, f"{database_path().stat().st_size}")),
        ("运行/清单", "资料库发布清单存在", lambda: (catalog_manifest_path() is not None, str(catalog_manifest_path()))),
    ]
    return [
        DrillCase(id=f"S{index:03d}", category=category, title=title, runner="state", data={"check": check})
        for index, (category, title, check) in enumerate(checks, start=1)
    ]


_LAST_PRICING_RESULT: dict[str, Any] | None = None


def _check_result_summary() -> tuple[bool, str]:
    result = {
        "clarification_questions": [],
        "proposals": [{
            "status": "ready_for_review",
            "bill_code": "010501001-000",
            "bill_title": "基础垫层",
            "quota_lines": [{"role": "main", "code": "2-1-28", "title": "混凝土垫层 无筋"}],
        }],
    }
    text = proposal_decision_summary(result)
    return "010501001-000" in text and "2-1-28" in text, text


def _check_plain_export() -> tuple[bool, str]:
    sample = _LAST_PRICING_RESULT
    if not sample:
        return False, "没有可用的实机检索结果"
    text = proposal_plain_text(sample)
    return bool(text.strip()) and "编码" in text, text.splitlines()[0] if text else ""


def all_cases() -> list[DrillCase]:
    cases = [*_pricing_cases(), *_state_cases()]
    if len(cases) != 100:
        raise AssertionError(f"acceptance drill must contain exactly 100 cases, got {len(cases)}")
    return cases


def _pricing_run(case: DrillCase) -> tuple[bool, list[str], dict[str, Any]]:
    global _LAST_PRICING_RESULT
    data = case.data
    started = time.perf_counter()
    result = analyze_pricing_description(
        data["query"],
        quota_edition="2025",
        standard_edition="2024",
        discipline=data["discipline"],
        limit=6,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if any(
        proposal.get("bill_code") or proposal.get("quota_lines")
        for proposal in result.get("proposals") or []
    ):
        _LAST_PRICING_RESULT = result
    errors: list[str] = []
    if not result.get("validation", {}).get("valid"):
        errors.append("结构化结果未通过本地校验")
    if not any(result.get(group) for group in ("bills", "quotas", "links")):
        errors.append("没有召回任何清单或定额")
    active_discipline = result.get("discipline")
    leaks = [
        f"{group}:{item.get('code')}:{item.get('discipline')}"
        for group in ("bills", "quotas", "links", "guidance")
        for item in result.get(group) or []
        if item.get("discipline") and item.get("discipline") != active_discipline
    ]
    if leaks:
        errors.append("跨专业结果：" + ", ".join(leaks[:3]))
    expected_bill = data.get("expected_bill")
    proposal_bills = {str(value.get("bill_code") or "") for value in result.get("proposals") or []}
    if expected_bill and expected_bill not in proposal_bills:
        errors.append(f"主方案清单不是 {expected_bill}")
    expected_quota = data.get("expected_quota")
    proposal_quotas = {
        str(line.get("code") or "")
        for proposal in result.get("proposals") or []
        for line in proposal.get("quota_lines") or []
        if line.get("role") == "main"
    }
    if expected_quota and expected_quota not in proposal_quotas:
        errors.append(f"主方案定额不是 {expected_quota}")
    expected_status = data.get("expected_status")
    if expected_status and result.get("decision_status") != expected_status:
        errors.append(f"方案状态不是 {expected_status}")
    expected_question_field = data.get("expected_question_field")
    question_fields = {
        str(value.get("field") or "")
        for value in result.get("clarification_questions") or []
    }
    if expected_question_field and expected_question_field not in question_fields:
        errors.append(f"未询问关键条件 {expected_question_field}")
    if elapsed_ms > 12_000:
        errors.append(f"热身后单次本地分析超过12秒：{elapsed_ms}ms")
    return not errors, errors, {
        "elapsed_ms": elapsed_ms,
        "decision_status": result.get("decision_status"),
        "bill_codes": sorted(proposal_bills),
        "main_quota_codes": sorted(proposal_quotas),
        "question_count": len(result.get("clarification_questions") or []),
        "question_fields": sorted(question_fields),
    }


def run(output: Path | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    warm_started = time.perf_counter()
    warm_search()
    warm_ms = round((time.perf_counter() - warm_started) * 1000, 1)
    results: list[dict[str, Any]] = []
    for case in all_cases():
        case_started = time.perf_counter()
        try:
            if case.runner == "pricing":
                passed, errors, details = _pricing_run(case)
            else:
                check = case.data["check"]
                passed, detail = check()
                errors = [] if passed else [str(detail)]
                details = {"detail": str(detail), "elapsed_ms": round((time.perf_counter() - case_started) * 1000, 1)}
        except Exception as exc:  # noqa: BLE001 - the report must retain all 100 outcomes
            passed, errors, details = False, [f"{type(exc).__name__}: {exc}"], {}
        results.append({
            "id": case.id,
            "category": case.category,
            "title": case.title,
            "passed": bool(passed),
            "errors": errors,
            "details": details,
        })
    failures = [value for value in results if not value["passed"]]
    report = {
        "schema_version": 1,
        "app_version": APP_VERSION,
        "platform": sys.platform,
        "catalogue": library_stats(),
        "warmup_ms": warm_ms,
        "case_count": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        "category_counts": dict(Counter(value["category"].split("/")[0] for value in results)),
        "scope_note": "100 次是在 Windows 实机和完整结构化山东资料库上执行的产品回归；它验证流程、召回、专业边界和关键样例，不等于工程计价准确率证明。",
        "results": results,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-error", action="store_true")
    args = parser.parse_args()
    report = run(args.output)
    summary = {key: report[key] for key in ("app_version", "case_count", "passed", "failed", "duration_ms", "warmup_ms")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for failure in (value for value in report["results"] if not value["passed"]):
        print(f"FAIL {failure['id']} {failure['title']}: {'；'.join(failure['errors'])}")
    return 1 if args.fail_on_error and report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
