"""Conservative, deterministic hygiene for model-generated text.

This module intentionally does not attempt authorship detection, statistical
watermark removal, paraphrasing, homoglyph replacement, NFKC normalisation, or
metadata stripping. It removes only a narrow set of non-rendering carrier
characters and reports potentially legitimate directional/joining controls.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Tuple

OUTPUT_HYGIENE_MODES = frozenset({"off", "report", "clean_safe"})

# Characters that do not carry visible user content and are safe to remove from
# normal prose output. ZWJ/ZWNJ, variation selectors, bidi controls, and exotic
# spaces are deliberately excluded because they can be legitimate.
SAFE_REMOVALS = {
    "\u00ad": "soft hyphen",
    "\u200b": "zero width space",
    "\u2060": "word joiner",
    "\u2061": "function application",
    "\u2062": "invisible times",
    "\u2063": "invisible separator",
    "\u2064": "invisible plus",
    "\ufeff": "zero width no-break space / BOM",
}

# These are findings only. Removing them without knowing the language or
# content type could damage Arabic/Persian scripts, bidirectional text, emoji,
# or source code.
REPORT_ONLY = {
    "\u200c": "zero width non-joiner",
    "\u200d": "zero width joiner",
    "\u061c": "Arabic letter mark",
    "\u200e": "left-to-right mark",
    "\u200f": "right-to-left mark",
    "\u202a": "left-to-right embedding",
    "\u202b": "right-to-left embedding",
    "\u202c": "pop directional formatting",
    "\u202d": "left-to-right override",
    "\u202e": "right-to-left override",
    "\u2066": "left-to-right isolate",
    "\u2067": "right-to-left isolate",
    "\u2068": "first strong isolate",
    "\u2069": "pop directional isolate",
}


def _is_tag_character(character: str) -> bool:
    codepoint = ord(character)
    return codepoint == 0xE0001 or 0xE0020 <= codepoint <= 0xE007F


def _finding(kind: str, label: str, codepoint: int, count: int, action: str) -> dict:
    return {
        "kind": kind,
        "label": label,
        "codepoint": f"U+{codepoint:04X}",
        "count": count,
        "action": action,
    }


def inspect_output_text(text: str) -> Dict[str, Any]:
    """Return bounded aggregate findings without retaining the supplied text."""

    safe_counts: Counter[tuple[str, int]] = Counter()
    report_counts: Counter[tuple[str, int]] = Counter()
    tag_count = 0

    for character in text or "":
        if character in SAFE_REMOVALS:
            safe_counts[(SAFE_REMOVALS[character], ord(character))] += 1
        elif character in REPORT_ONLY:
            report_counts[(REPORT_ONLY[character], ord(character))] += 1
        elif _is_tag_character(character):
            tag_count += 1

    findings = [
        _finding("invisible", label, codepoint, count, "safe_remove")
        for (label, codepoint), count in sorted(safe_counts.items())
    ]
    if tag_count:
        findings.append(
            _finding("tag", "Unicode tag character", 0xE0000, tag_count, "report_only")
        )
    findings.extend(
        _finding("directional_or_joining", label, codepoint, count, "report_only")
        for (label, codepoint), count in sorted(report_counts.items())
    )

    return {
        "input_characters": len(text or ""),
        "actionable_count": sum(safe_counts.values()),
        "reported_only_count": sum(report_counts.values()) + tag_count,
        "findings": findings,
    }


def apply_output_hygiene(text: str, mode: str = "clean_safe") -> Tuple[str, Dict[str, Any]]:
    """Inspect text and optionally remove only the conservative safe set."""

    normalized_mode = (mode or "clean_safe").strip().lower()
    if normalized_mode not in OUTPUT_HYGIENE_MODES:
        raise ValueError(f"Unknown output hygiene mode: {mode}")

    report = inspect_output_text(text) if normalized_mode != "off" else {
        "input_characters": len(text or ""),
        "actionable_count": 0,
        "reported_only_count": 0,
        "findings": [],
    }
    cleaned = text or ""
    if normalized_mode == "clean_safe":
        cleaned = "".join(
            character
            for character in cleaned
            if character not in SAFE_REMOVALS
        )

    removed_count = len(text or "") - len(cleaned)
    report.update({
        "mode": normalized_mode,
        "changed": cleaned != (text or ""),
        "removed_count": removed_count,
        "output_characters": len(cleaned),
    })
    return cleaned, report


def apply_hygiene_to_value(value: Any, mode: str = "clean_safe") -> Tuple[Any, Dict[str, Any]]:
    """Recursively sanitise strings in JSON-like output and aggregate findings."""

    aggregate = {
        "mode": mode,
        "changed": False,
        "removed_count": 0,
        "actionable_count": 0,
        "reported_only_count": 0,
        "findings": [],
    }
    finding_counts: Counter[tuple[str, str, str, str]] = Counter()

    def visit(item: Any) -> Any:
        if isinstance(item, str):
            cleaned, report = apply_output_hygiene(item, mode)
            aggregate["changed"] = aggregate["changed"] or report["changed"]
            aggregate["removed_count"] += report["removed_count"]
            aggregate["actionable_count"] += report["actionable_count"]
            aggregate["reported_only_count"] += report["reported_only_count"]
            for finding in report["findings"]:
                key = (
                    finding["kind"],
                    finding["label"],
                    finding["codepoint"],
                    finding["action"],
                )
                finding_counts[key] += finding["count"]
            return cleaned
        if isinstance(item, list):
            return [visit(child) for child in item]
        if isinstance(item, dict):
            return {key: visit(child) for key, child in item.items()}
        return item

    cleaned_value = visit(value)
    aggregate["findings"] = [
        {
            "kind": kind,
            "label": label,
            "codepoint": codepoint,
            "count": count,
            "action": action,
        }
        for (kind, label, codepoint, action), count in sorted(finding_counts.items())
    ]
    return cleaned_value, aggregate
