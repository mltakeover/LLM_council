import json

import pytest

from backend import council
from backend.orchestration import (
    get_orchestration_strategy,
    list_orchestration_strategies,
)


def test_hybrid_is_recommended_and_uses_targeted_review() -> None:
    strategies = list_orchestration_strategies()

    hybrid = get_orchestration_strategy("hybrid")

    assert hybrid.manager_planning is True
    assert hybrid.peer_review == "targeted"
    assert next(item for item in strategies if item["id"] == "hybrid")["recommended"] is True


@pytest.mark.asyncio
async def test_manager_plan_assigns_every_model_and_preserves_custom_role(monkeypatch) -> None:
    payload = {
        "objective": "Produce a governed HLD",
        "assignments": [
            {
                "model": "ollama:a",
                "role": "Generated role",
                "deliverable": "Business scope",
                "success_criteria": ["Bounded scope"],
                "dependencies": [],
            },
            {
                "model": "ollama:b",
                "role": "Security architect",
                "deliverable": "Security controls",
                "success_criteria": ["Threat coverage"],
                "dependencies": ["Business scope"],
            },
        ],
        "qa_reviewers": ["unselected:model", "ollama:b", "ollama:a"],
        "integration_notes": ["Preserve disagreements"],
    }

    async def query(*_args, **_kwargs):
        return {"ok": True, "content": json.dumps(payload)}

    monkeypatch.setattr(council, "query_model", query)
    plan = await council.create_workforce_plan(
        "Create an HLD",
        ["ollama:a", "ollama:b"],
        "ollama:a",
        role_assignments={"ollama:a": "Business analyst"},
        orchestration_strategy="hybrid",
    )

    assert plan["source"] == "manager"
    assert [item["model"] for item in plan["assignments"]] == [
        "ollama:a",
        "ollama:b",
    ]
    assert plan["assignments"][0]["role"] == "Business analyst"
    assert plan["qa_reviewers"] == ["ollama:b", "ollama:a"]


@pytest.mark.asyncio
async def test_invalid_manager_plan_falls_back_without_stopping_run(monkeypatch) -> None:
    async def query(*_args, **_kwargs):
        return {"ok": True, "content": '{"objective": "missing assignments"}'}

    monkeypatch.setattr(council, "query_model", query)
    plan = await council.create_workforce_plan(
        "Review the design",
        ["ollama:a", "ollama:b"],
        "ollama:a",
        orchestration_strategy="hybrid",
    )

    assert plan["source"] == "deterministic_fallback"
    assert plan["manager_error"]["code"] == "invalid_manager_plan"
    assert len(plan["assignments"]) == 2
    assert plan["qa_reviewers"] == ["ollama:a", "ollama:b"]


@pytest.mark.asyncio
async def test_workforce_worker_output_is_structured_and_hygienic(monkeypatch) -> None:
    worker_payload = {
        "executive_summary": "Evidence\u200b summary",
        "deliverables": ["Architecture"],
        "claims": [{
            "claim": "A control is required",
            "evidence": "Policy",
            "confidence": "high",
            "source": "document.pdf",
            "assumptions": [],
        }],
        "risks": [],
        "recommendations": ["Add the control"],
        "open_questions": [],
    }

    async def query_parallel(models, _messages, **_kwargs):
        return {
            model: {
                "ok": True,
                "content": json.dumps(worker_payload),
                "elapsed_seconds": 0.1,
                "attempts": 1,
                "usage": None,
            }
            for model in models
        }

    monkeypatch.setattr(council, "query_models_parallel", query_parallel)
    plan = {
        "assignments": [{
            "model": "ollama:a",
            "role": "Solution architect",
            "deliverable": "Architecture",
            "success_criteria": ["Complete"],
            "dependencies": [],
        }]
    }
    results = await council.stage1_collect_responses(
        "Create an architecture",
        models=["ollama:a"],
        orchestration_strategy="workforce",
        workforce_plan=plan,
        output_hygiene="clean_safe",
    )

    assert results[0]["structured_output_valid"] is True
    assert results[0]["worker_output"]["executive_summary"] == "Evidence summary"
    assert "## Claims and evidence" in results[0]["response"]
    assert results[0]["output_hygiene"]["nested"]["removed_count"] == 1


@pytest.mark.asyncio
async def test_hybrid_qa_uses_only_targeted_reviewers_and_does_not_rank_roles(
    monkeypatch,
) -> None:
    captured = {}

    async def query_parallel(models, messages, **_kwargs):
        captured["models"] = models
        captured["prompt"] = messages[-1]["content"]
        return {
            model: {
                "ok": True,
                "content": json.dumps({
                    "evaluations": [],
                    "unsupported_claims": [],
                    "conflicts": [],
                    "integration_gaps": [],
                    "recommended_resolutions": [],
                }),
            }
            for model in models
        }

    monkeypatch.setattr(council, "query_models_parallel", query_parallel)
    results, _ = await council.stage2_collect_rankings(
        "Create an HLD",
        [
            {"model": "ollama:a", "response": "Business scope"},
            {"model": "ollama:b", "response": "Security controls"},
        ],
        models=["ollama:a", "ollama:b"],
        reviewer_models=["ollama:b"],
        orchestration_strategy="hybrid",
    )

    assert captured["models"] == ["ollama:b"]
    assert "do not rank different specialist" in captured["prompt"].lower()
    assert results[0]["qa_review"] is True
    assert results[0]["ranking_valid"] is False
    assert results[0]["parsed_ranking"] == []


@pytest.mark.asyncio
async def test_hybrid_master_preserves_contribution_ledger_and_cleans_output(
    monkeypatch,
) -> None:
    payload = {
        "mode": "review",
        "executive_summary": "Governed\u200b answer",
        "contribution_ledger": [{
            "worker_model": "ollama:a",
            "role": "Security architect",
            "decision": "used",
            "reason": "The control recommendation was evidence-backed.",
            "evidence": ["Policy requirement"],
        }],
        "conclusion": "Implement the control.",
    }

    async def query(*_args, **_kwargs):
        return {
            "ok": True,
            "content": json.dumps(payload),
            "elapsed_seconds": 0.2,
            "attempts": 1,
            "usage": None,
        }

    monkeypatch.setattr(council, "query_model", query)
    result = await council.stage3_synthesize_final(
        "Review the design",
        [{
            "model": "ollama:a",
            "role": "Security architect",
            "assignment": {"deliverable": "Security controls"},
            "response": "Add the control",
        }],
        [],
        chairman_model="ollama:a",
        council_mode="review",
        orchestration_strategy="hybrid",
        workforce_plan={"objective": "Governed design"},
    )

    assert result["structured_output_valid"] is True
    assert result["structured_report"]["executive_summary"] == "Governed answer"
    assert result["structured_report"]["contribution_ledger"][0]["decision"] == "used"
    assert "## Contribution ledger" in result["response"]
    assert result["output_hygiene"]["structured_values"]["removed_count"] == 1
