import uuid

import pytest

from backend import storage
from backend.council import (
    ChairmanFinding,
    ChairmanReport,
    _report_to_markdown,
    calculate_aggregate_rankings,
    get_model_recommendations,
    parse_ranking_from_text,
)
from backend.review_profiles import get_review_profile, list_review_profiles


@pytest.fixture
def isolated_storage(tmp_path):
    database_path = tmp_path / "council.db"
    legacy_path = tmp_path / "legacy"
    legacy_path.mkdir()
    storage.configure_database(str(database_path), str(legacy_path))
    return database_path, legacy_path


async def _seed_reviewed_conversation(
    question: str,
    review_profile: str,
    best_model: str,
    other_model: str,
) -> None:
    conversation_id = str(uuid.uuid4())
    await storage.create_conversation(conversation_id)
    await storage.add_user_message(conversation_id, question)
    await storage.add_assistant_message(
        conversation_id,
        [{"model": best_model, "response": "..."}, {"model": other_model, "response": "..."}],
        [],
        {"model": best_model, "response": "Report", "success": True},
        {
            "review_profile": review_profile,
            "aggregate_rankings": [
                {"model": best_model, "average_rank": 1.0, "rankings_count": 2},
                {"model": other_model, "average_rank": 2.0, "rankings_count": 2},
            ],
        },
    )


def test_review_profiles_cover_architecture_and_code() -> None:
    profile_ids = {profile["id"] for profile in list_review_profiles()}

    assert {"general", "hld", "lld", "code", "security"} <= profile_ids
    assert "scalability" in get_review_profile("hld").objective.lower()


def test_ranking_parser_prefers_structured_json() -> None:
    ranking = parse_ranking_from_text(
        '```json\n{"ranking": ["Response B", "Response A"]}\n```'
    )

    assert ranking == ["Response B", "Response A"]


def test_aggregate_rankings_ignores_unknown_labels() -> None:
    aggregate = calculate_aggregate_rankings(
        [
            {"parsed_ranking": ["Response B", "Response A"]},
            {"parsed_ranking": ["Response A", "Response Z"]},
        ],
        {"Response A": "model-a", "Response B": "model-b"},
    )

    assert aggregate[0]["model"] == "model-b"
    assert aggregate[0]["average_rank"] == 1.0


def test_aggregate_rankings_respects_invalidated_rankings() -> None:
    """A ranking stage2_collect_rankings already rejected (ranking_valid is
    False, parsed_ranking deliberately []) must stay excluded, not get
    silently re-derived from the raw text via the legacy-data fallback."""

    label_to_model = {"Response A": "model-a", "Response B": "model-b"}
    rejected_ranking = {
        "model": "reviewer",
        # A model that hallucinated a duplicate label - this is exactly
        # what stage2_collect_rankings' validator rejects.
        "ranking": '{"ranking": ["Response A", "Response A", "Response B"]}',
        "parsed_ranking": [],
        "ranking_valid": False,
    }

    aggregate = calculate_aggregate_rankings([rejected_ranking], label_to_model)

    assert aggregate == []


def test_aggregate_rankings_still_parses_legacy_entries() -> None:
    """Entries from before the parsed_ranking field existed should still
    fall back to a raw-text re-parse."""

    label_to_model = {"Response A": "model-a", "Response B": "model-b"}
    legacy_ranking = {
        "model": "reviewer",
        "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
    }

    aggregate = calculate_aggregate_rankings([legacy_ranking], label_to_model)

    assert aggregate[0]["model"] == "model-b"
    assert aggregate[0]["average_rank"] == 1.0


def test_chairman_report_renders_prioritised_markdown() -> None:
    report = ChairmanReport(
        executive_summary="One high-risk issue requires action.",
        findings=[ChairmanFinding(
            severity="high",
            category="Security",
            title="Missing trust boundary",
            evidence="The design does not identify the public API boundary.",
            impact="Authorisation controls may be applied inconsistently.",
            recommendation="Document the boundary and its controls.",
        )],
        assumptions=[],
        dependencies=["Identity provider"],
        open_questions=["Who owns the API gateway?"],
        conclusion="Address before detailed design approval.",
    )

    markdown = _report_to_markdown(report)

    assert "[HIGH] Missing trust boundary" in markdown
    assert "## Dependencies" in markdown
    assert "Identity provider" in markdown


@pytest.mark.asyncio
async def test_recommendations_prefer_same_review_profile(isolated_storage) -> None:
    """A code-topic question reviewed under different profiles should get
    different recommendations depending on which profile is asked for -
    a code review and a security review of similar-sounding questions can
    favor different models."""

    await _seed_reviewed_conversation(
        "Review this python function for bugs",
        "code",
        best_model="model-code-specialist",
        other_model="model-generalist",
    )
    await _seed_reviewed_conversation(
        "Review this python function for vulnerabilities",
        "security",
        best_model="model-security-specialist",
        other_model="model-generalist",
    )

    code_result = await get_model_recommendations(
        "debug this python function", review_profile="code",
    )
    security_result = await get_model_recommendations(
        "debug this python function", review_profile="security",
    )

    assert code_result["category"] == "code"
    assert code_result["review_profile"] == "code"
    assert code_result["recommended"][0] == "model-code-specialist"

    assert security_result["review_profile"] == "security"
    assert security_result["recommended"][0] == "model-security-specialist"


@pytest.mark.asyncio
async def test_recommendations_fall_back_to_topic_when_profile_has_no_history(
    isolated_storage,
) -> None:
    """A profile combination with no history yet should fall back to the
    topic-only match instead of going silent."""

    await _seed_reviewed_conversation(
        "Review this python function for bugs",
        "code",
        best_model="model-code-specialist",
        other_model="model-generalist",
    )

    result = await get_model_recommendations(
        "debug this python function", review_profile="hld",
    )

    assert result["category"] == "code"
    assert result["review_profile"] is None  # fell back to topic-only
    assert result["recommended"][0] == "model-code-specialist"
    assert result["based_on_conversations"] == 1


@pytest.mark.asyncio
async def test_recommendations_empty_with_no_history_at_all(isolated_storage) -> None:
    result = await get_model_recommendations(
        "write a poem about the sea", review_profile="general",
    )

    assert result["recommended"] == []
    assert result["review_profile"] is None
