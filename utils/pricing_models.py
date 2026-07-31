from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


VALID_QUOTA_ROLES = {
    "main",
    "supplement",
    "adjustment",
    "transport",
    "conversion",
    "alternative",
}
VALID_PROPOSAL_STATUSES = {
    "ready_for_review",
    "needs_clarification",
    "multiple_valid_options",
    "no_reliable_match",
}


@dataclass(frozen=True)
class TypedAttribute:
    key: str
    value: Any
    unit: str | None = None
    source: str = ""
    confidence_level: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NegativeConstraint:
    key: str
    value: Any = False
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkItem:
    id: str
    source_span: str
    discipline: str | None = None
    action: str = ""
    object: str = ""
    location: str = ""
    material: str = ""
    attributes: tuple[TypedAttribute, ...] = field(default_factory=tuple)
    negative_constraints: tuple[NegativeConstraint, ...] = field(default_factory=tuple)
    unknown_critical_fields: tuple[str, ...] = field(default_factory=tuple)
    confidence_level: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_span": self.source_span,
            "discipline": self.discipline,
            "action": self.action,
            "object": self.object,
            "location": self.location,
            "material": self.material,
            "attributes": [value.to_dict() for value in self.attributes],
            "negative_constraints": [value.to_dict() for value in self.negative_constraints],
            "unknown_critical_fields": list(self.unknown_critical_fields),
            "confidence_level": self.confidence_level,
        }

    def search_text(self) -> str:
        # Long location phrases can dominate lexical retrieval (for example,
        # "地下室外墙" must not turn a waterproofing query into wall concrete).
        # Keep the original source span for evidence, but use the estimating
        # category name that appears in bill titles for retrieval.
        if "防水" in self.object and "墙" in self.location:
            attributes = " ".join(value.source for value in self.attributes if value.source)
            return f"墙面 {self.material} {self.object} {attributes}".strip()
        if self.location and self.location not in self.source_span:
            canonical_location = "墙面" if "墙" in self.location else self.location
            return f"{canonical_location} {self.source_span}".strip()
        return self.source_span


@dataclass(frozen=True)
class ClarificationQuestion:
    id: str
    work_item_id: str
    field: str
    question: str
    options: tuple[str, ...]
    reason: str
    impact: str = "changes_top_candidate"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["options"] = list(self.options)
        return data


@dataclass(frozen=True)
class QuotaSelection:
    record_id: str
    code: str
    title: str
    unit: str
    role: str
    factor: float | None
    reason: str
    evidence_refs: tuple[str, ...]
    source_link_record_id: str | None = None
    data_basis: str = "structured_catalog"
    source_status: str = "structured_only"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_refs"] = list(self.evidence_refs)
        return data


@dataclass(frozen=True)
class PricingProposal:
    work_item_id: str
    bill_record_id: str | None
    bill_code: str = ""
    bill_title: str = ""
    bill_unit: str = ""
    quota_lines: tuple[QuotaSelection, ...] = field(default_factory=tuple)
    review_candidates: tuple[QuotaSelection, ...] = field(default_factory=tuple)
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    hard_conflicts: tuple[str, ...] = field(default_factory=tuple)
    unresolved_question_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    evidence_pages: tuple[str, ...] = field(default_factory=tuple)
    evidence_located: bool = False
    data_basis: str = ""
    source_review_required: bool = False
    source_review_reasons: tuple[str, ...] = field(default_factory=tuple)
    match_level: str = "low"
    status: str = "no_reliable_match"
    confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_item_id": self.work_item_id,
            "bill_record_id": self.bill_record_id,
            "bill_code": self.bill_code,
            "bill_title": self.bill_title,
            "bill_unit": self.bill_unit,
            "quota_lines": [value.to_dict() for value in self.quota_lines],
            "review_candidates": [value.to_dict() for value in self.review_candidates],
            "assumptions": list(self.assumptions),
            "hard_conflicts": list(self.hard_conflicts),
            "unresolved_question_ids": list(self.unresolved_question_ids),
            "evidence_refs": list(self.evidence_refs),
            "evidence_pages": list(self.evidence_pages),
            "evidence_located": self.evidence_located,
            "data_basis": self.data_basis,
            "source_review_required": self.source_review_required,
            "source_review_reasons": list(self.source_review_reasons),
            "match_level": self.match_level,
            "status": self.status,
            "confirmed": self.confirmed,
        }
