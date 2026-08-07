from backend.council import (
    ChairmanFinding,
    ChairmanReport,
    _report_to_markdown,
    calculate_aggregate_rankings,
    parse_ranking_from_text,
)
from backend.review_profiles import get_review_profile, list_review_profiles


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
