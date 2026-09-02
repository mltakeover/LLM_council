from backend.output_hygiene import apply_hygiene_to_value, apply_output_hygiene


def test_clean_safe_removes_only_conservative_invisible_carriers() -> None:
    source = "alpha\u200bbeta\u2060gamma\U000e0061"

    cleaned, report = apply_output_hygiene(source, "clean_safe")

    assert cleaned == "alphabetagamma\U000e0061"
    assert report["changed"] is True
    assert report["removed_count"] == 2
    assert report["actionable_count"] == 2
    assert report["reported_only_count"] == 1


def test_report_mode_does_not_change_actionable_characters() -> None:
    source = "alpha\u200bbeta"

    cleaned, report = apply_output_hygiene(source, "report")

    assert cleaned == source
    assert report["changed"] is False
    assert report["actionable_count"] == 1


def test_joiners_and_directional_controls_are_report_only() -> None:
    source = "Arabic\u200d text\u2067RTL\u2069"

    cleaned, report = apply_output_hygiene(source, "clean_safe")

    assert cleaned == source
    assert report["removed_count"] == 0
    assert report["reported_only_count"] == 3
    assert {finding["action"] for finding in report["findings"]} == {"report_only"}


def test_nested_structured_output_is_sanitised_without_retaining_content() -> None:
    cleaned, report = apply_hygiene_to_value(
        {"claim": "supported\u200b", "details": ["safe\u2060", 3]},
        "clean_safe",
    )

    assert cleaned == {"claim": "supported", "details": ["safe", 3]}
    assert report["removed_count"] == 2
    assert report["changed"] is True


def test_off_mode_skips_inspection_and_changes() -> None:
    source = "alpha\u200bbeta"

    cleaned, report = apply_output_hygiene(source, "off")

    assert cleaned == source
    assert report["findings"] == []
    assert report["actionable_count"] == 0
