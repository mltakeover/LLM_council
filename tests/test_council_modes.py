import json

import pytest

from backend import council
from backend.council import ChairmanReport
from backend.council_modes import (
    MODES,
    resolve_council_mode,
    resolve_role_assignments,
)
from backend.evaluations import EVALUATION_CASES, evaluate_report_shape
from backend.review_profiles import get_review_profile


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Explain compound interest simply", "ask"),
        ("Review this contract for risks", "review"),
        ("Debate the case for and against remote work", "debate"),
        ("Help me decide which option to choose", "decide"),
        ("Brainstorm ideas for a birthday party", "brainstorm"),
        ("Compare electric cars versus hybrids", "compare"),
        ("Create a plan to learn French", "plan"),
        ("Summarise these notes", "summarize"),
        ("Fact-check this claim", "fact_check"),
    ],
)
def test_auto_mode_routes_general_purpose_requests(prompt: str, expected: str) -> None:
    assert resolve_council_mode("auto", prompt).id == expected


def test_explicit_mode_is_not_reclassified() -> None:
    assert resolve_council_mode("brainstorm", "Review this idea").id == "brainstorm"


def test_specialist_profile_routes_auto_to_review() -> None:
    assert resolve_council_mode(
        "auto",
        "Consider the attached material",
        review_profile="security",
    ).id == "review"


def test_custom_roles_override_mode_defaults_per_model() -> None:
    models = ["ollama:one", "ollama:two"]
    roles = resolve_role_assignments(
        models,
        MODES["debate"],
        get_review_profile("general"),
        {"ollama:one": "Ethics advocate", "unselected:model": "Ignored"},
    )

    assert roles["ollama:one"] == "Ethics advocate"
    assert roles["ollama:two"] == "Sceptical challenger"
    assert "unselected:model" not in roles


@pytest.mark.asyncio
async def test_stage1_uses_mode_specific_and_custom_role_prompts(monkeypatch) -> None:
    captured = {}

    async def query_parallel(models, _messages, **kwargs):
        captured.update(kwargs["messages_by_model"])
        return {
            model: {
                "ok": True,
                "content": f"answer from {model}",
                "elapsed_seconds": 0.1,
                "attempts": 1,
                "usage": None,
            }
            for model in models
        }

    monkeypatch.setattr(council, "query_models_parallel", query_parallel)
    results = await council.stage1_collect_responses(
        "Debate this policy",
        models=["ollama:a", "ollama:b"],
        council_mode="debate",
        role_assignments={"ollama:a": "Public-interest advocate"},
    )

    assert results[0]["role"] == "Public-interest advocate"
    assert results[0]["reviewer_role"] == "Public-interest advocate"
    assert results[0]["council_mode"] == "debate"
    assert "Council mode: Debate" in captured["ollama:a"][0]["content"]
    assert "Public-interest advocate" in captured["ollama:a"][0]["content"]


@pytest.mark.asyncio
async def test_stage2_uses_mode_specific_evaluation_criteria(monkeypatch) -> None:
    captured = {}

    async def query_parallel(models, messages, **_kwargs):
        captured["messages"] = messages
        return {
            model: {
                "ok": True,
                "content": json.dumps({
                    "evaluations": [],
                    "ranking": ["Response A", "Response B"],
                }),
            }
            for model in models
        }

    monkeypatch.setattr(council, "query_models_parallel", query_parallel)
    rankings, _ = await council.stage2_collect_rankings(
        "Generate ideas",
        [
            {"model": "ollama:a", "response": "A"},
            {"model": "ollama:b", "response": "B"},
        ],
        models=["ollama:a", "ollama:b"],
        council_mode="brainstorm",
    )

    assert all(ranking["ranking_valid"] for ranking in rankings)
    assert "Originality, Relevance, Variety, Usefulness" in captured["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_chairman_validates_decision_output(monkeypatch) -> None:
    payload = {
        "mode": "decide",
        "executive_summary": "Option A is the better fit under the stated constraint.",
        "options": [{
            "name": "Option A",
            "summary": "Lower initial cost.",
            "benefits": ["Affordable"],
            "drawbacks": ["Less control"],
            "risks": ["Price changes"],
            "best_for": "A short time horizon",
        }],
        "recommendation": "Choose Option A if the two-year horizon is firm.",
        "conclusion": "Reassess if the time horizon changes.",
    }

    async def query(_model, _messages, **_kwargs):
        return {
            "ok": True,
            "content": json.dumps(payload),
            "elapsed_seconds": 0.2,
            "attempts": 1,
            "usage": None,
        }

    monkeypatch.setattr(council, "query_model", query)
    result = await council.stage3_synthesize_final(
        "Which option should I choose?",
        [{"model": "ollama:a", "reviewer_role": "Analyst", "response": "A"}],
        [],
        chairman_model="ollama:a",
        council_mode="decide",
    )

    assert result["structured_output_valid"] is True
    assert result["structured_report"]["mode"] == "decide"
    assert "## Options" in result["response"]
    assert "#### Benefits" in result["response"]
    assert "## Recommendation" in result["response"]


def test_evaluation_catalog_covers_every_non_auto_mode() -> None:
    covered = {case.expected_mode for case in EVALUATION_CASES}
    assert set(MODES) - {"auto"} == covered


def test_evaluation_shape_reports_missing_fields() -> None:
    case = next(case for case in EVALUATION_CASES if case.expected_mode == "plan")
    result = evaluate_report_shape(
        ChairmanReport(
            mode="plan",
            executive_summary="Plan summary",
            conclusion="Start now",
        ).model_dump(),
        case,
    )

    assert result["passed"] is False
    assert "plan_steps" in result["missing_fields"]
