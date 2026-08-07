"""Deterministic evaluation catalogue for general-purpose council behaviour."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    prompt: str
    requested_mode: str
    expected_mode: str
    required_report_fields: List[str]


EVALUATION_CASES = [
    EvaluationCase(
        id="general-answer",
        prompt="Explain why seasons occur in plain language.",
        requested_mode="ask",
        expected_mode="ask",
        required_report_fields=["direct_answer", "conclusion"],
    ),
    EvaluationCase(
        id="document-review",
        prompt="Review this proposal and identify material risks.",
        requested_mode="review",
        expected_mode="review",
        required_report_fields=["findings", "verdict", "conclusion"],
    ),
    EvaluationCase(
        id="balanced-debate",
        prompt="Debate the case for and against a four-day working week.",
        requested_mode="debate",
        expected_mode="debate",
        required_report_fields=["positions", "conclusion"],
    ),
    EvaluationCase(
        id="decision-support",
        prompt="Help me decide whether to rent or buy for a two-year stay.",
        requested_mode="decide",
        expected_mode="decide",
        required_report_fields=["options", "recommendation", "conclusion"],
    ),
    EvaluationCase(
        id="idea-generation",
        prompt="Brainstorm ideas for a low-cost community event.",
        requested_mode="brainstorm",
        expected_mode="brainstorm",
        required_report_fields=["ideas", "next_steps", "conclusion"],
    ),
    EvaluationCase(
        id="fair-comparison",
        prompt="Compare remote work versus office work for a new team.",
        requested_mode="compare",
        expected_mode="compare",
        required_report_fields=["comparison", "conclusion"],
    ),
    EvaluationCase(
        id="action-plan",
        prompt="Create a plan to learn conversational Spanish in six months.",
        requested_mode="plan",
        expected_mode="plan",
        required_report_fields=["plan_steps", "conclusion"],
    ),
    EvaluationCase(
        id="faithful-summary",
        prompt="Summarise the supplied meeting notes and list open questions.",
        requested_mode="summarize",
        expected_mode="summarize",
        required_report_fields=["key_points", "conclusion"],
    ),
    EvaluationCase(
        id="claim-check",
        prompt="Fact-check the claims in this text and expose uncertainty.",
        requested_mode="fact_check",
        expected_mode="fact_check",
        required_report_fields=["claims", "conclusion"],
    ),
]


def list_evaluation_cases() -> List[dict]:
    return [asdict(case) for case in EVALUATION_CASES]


def evaluate_report_shape(
    report: Dict[str, Any],
    case: EvaluationCase,
) -> Dict[str, Any]:
    missing = []
    for field in case.required_report_fields:
        value = report.get(field)
        if value is None or value == "" or value == []:
            missing.append(field)
    actual_mode = report.get("mode")
    return {
        "case_id": case.id,
        "passed": not missing and actual_mode == case.expected_mode,
        "expected_mode": case.expected_mode,
        "actual_mode": actual_mode,
        "missing_fields": missing,
    }
