from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.work_items import segment_description


def evaluate(dataset: Path) -> dict:
    cases = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    count_correct = 0
    term_total = 0
    term_correct = 0
    attribute_total = 0
    attribute_correct = 0
    negative_total = 0
    negative_correct = 0
    failures: list[dict] = []
    for case in cases:
        items = segment_description(case["description"], discipline=case.get("discipline"))
        count_ok = len(items) == int(case["expected_items"])
        count_correct += int(count_ok)
        case_errors: list[str] = []
        if not count_ok:
            case_errors.append(f"事项数 expected={case['expected_items']} actual={len(items)}")
        for index, expected_terms in enumerate(case.get("expected_terms") or []):
            for term in expected_terms:
                term_total += 1
                ok = index < len(items) and term in items[index].source_span
                term_correct += int(ok)
                if not ok:
                    case_errors.append(f"W{index + 1} 缺少原文片段 {term}")
        item_by_id = {value.id: value for value in items}
        for item_id, expected in (case.get("expected_attributes") or {}).items():
            actual = {value.key: value.value for value in item_by_id.get(item_id, type("Empty", (), {"attributes": ()})()).attributes}
            for key, value in expected.items():
                attribute_total += 1
                ok = actual.get(key) == value
                attribute_correct += int(ok)
                if not ok:
                    case_errors.append(f"{item_id}.{key} expected={value!r} actual={actual.get(key)!r}")
        actual_negative = {value.key for item in items for value in item.negative_constraints}
        for key in case.get("expected_negative") or []:
            negative_total += 1
            ok = key in actual_negative
            negative_correct += int(ok)
            if not ok:
                case_errors.append(f"缺少否定条件 {key}")
        if case_errors:
            failures.append({"id": case["id"], "errors": case_errors})
    return {
        "dataset": dataset.name,
        "case_count": len(cases),
        "synthetic_only": True,
        "scope_note": "仅验证合成描述的事项边界、原文保留和确定性属性，不代表真实套价准确率。",
        "metrics": {
            "item_count_accuracy": count_correct / len(cases) if cases else 0,
            "source_term_recall": term_correct / term_total if term_total else 0,
            "typed_attribute_accuracy": attribute_correct / attribute_total if attribute_total else 0,
            "negative_constraint_recall": negative_correct / negative_total if negative_total else 0,
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation" / "datasets" / "synthetic_v1.jsonl")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.dataset)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
