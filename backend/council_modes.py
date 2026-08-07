"""General-purpose council modes and deterministic task routing."""

from dataclasses import asdict, dataclass
from typing import Dict, List, Mapping, Optional

from .review_profiles import ReviewProfile


@dataclass(frozen=True)
class CouncilMode:
    id: str
    name: str
    description: str
    objective: str
    evaluation_criteria: List[str]
    default_roles: List[str]
    chairman_focus: str


MODES: Dict[str, CouncilMode] = {
    "auto": CouncilMode(
        id="auto",
        name="Auto",
        description="Choose the most suitable council approach from the request.",
        objective="Identify the user's goal and apply the most useful council mode.",
        evaluation_criteria=["Goal fit", "Accuracy", "Usefulness", "Clarity"],
        default_roles=[
            "Independent evidence analyst",
            "Practical problem solver",
            "Critical challenger",
            "Clarity and user-value advocate",
        ],
        chairman_focus="Resolve the task type, then deliver the most useful synthesis.",
    ),
    "ask": CouncilMode(
        id="ask",
        name="Ask",
        description="Answer and explain a general question from multiple perspectives.",
        objective=(
            "Answer the request directly, accurately and clearly. Distinguish facts, "
            "reasoned judgement and uncertainty."
        ),
        evaluation_criteria=["Accuracy", "Relevance", "Clarity", "Practical usefulness"],
        default_roles=[
            "Evidence and accuracy analyst",
            "Plain-language explainer",
            "Critical assumptions challenger",
            "Practical application adviser",
        ],
        chairman_focus=(
            "Lead with a direct answer, reconcile material differences and expose uncertainty."
        ),
    ),
    "review": CouncilMode(
        id="review",
        name="Review",
        description="Critique content using a selected general or specialist profile.",
        objective=(
            "Assess the supplied subject against the selected review objective, with "
            "evidence, impact, recommendations and open questions."
        ),
        evaluation_criteria=[
            "Evidence",
            "Correctness",
            "Completeness",
            "Risk coverage",
            "Actionability",
        ],
        default_roles=[
            "Accuracy and evidence reviewer",
            "Risk and edge-case reviewer",
            "Completeness reviewer",
            "Practical improvement adviser",
        ],
        chairman_focus=(
            "Prioritise evidence-backed findings and give an explicit review verdict."
        ),
    ),
    "debate": CouncilMode(
        id="debate",
        name="Debate",
        description="Develop opposing positions and a balanced assessment.",
        objective=(
            "Present the strongest competing arguments fairly, test assumptions and "
            "identify what evidence would change the conclusion."
        ),
        evaluation_criteria=[
            "Argument strength",
            "Evidence",
            "Fairness",
            "Counterargument coverage",
        ],
        default_roles=[
            "Proposition advocate",
            "Sceptical challenger",
            "Neutral evidence arbiter",
            "Consequences and stakeholder analyst",
        ],
        chairman_focus=(
            "Steelman competing positions before giving a balanced conclusion."
        ),
    ),
    "decide": CouncilMode(
        id="decide",
        name="Decide",
        description="Evaluate options and recommend a decision.",
        objective=(
            "Compare realistic options against explicit criteria, trade-offs, risks and "
            "constraints, then recommend a conditional course of action."
        ),
        evaluation_criteria=[
            "Criteria fit",
            "Trade-off quality",
            "Risk awareness",
            "Feasibility",
            "Decision clarity",
        ],
        default_roles=[
            "Options and criteria analyst",
            "Risk and downside challenger",
            "Value and outcomes adviser",
            "Implementation feasibility adviser",
        ],
        chairman_focus=(
            "Compare options transparently and state a recommendation with conditions."
        ),
    ),
    "brainstorm": CouncilMode(
        id="brainstorm",
        name="Brainstorm",
        description="Generate, combine and prioritise diverse ideas.",
        objective=(
            "Produce varied, relevant ideas before converging on the most promising "
            "directions. Avoid superficial duplicates."
        ),
        evaluation_criteria=["Originality", "Relevance", "Variety", "Usefulness"],
        default_roles=[
            "Divergent ideas generator",
            "Constraint-breaking innovator",
            "Audience and value critic",
            "Feasibility and synthesis adviser",
        ],
        chairman_focus=(
            "Cluster distinct ideas, identify the strongest candidates and propose next steps."
        ),
    ),
    "compare": CouncilMode(
        id="compare",
        name="Compare",
        description="Compare alternatives consistently against useful criteria.",
        objective=(
            "Define fair criteria, compare like with like, expose trade-offs and explain "
            "which alternative fits which circumstances."
        ),
        evaluation_criteria=[
            "Criteria consistency",
            "Factual accuracy",
            "Trade-off coverage",
            "User fit",
        ],
        default_roles=[
            "Comparison criteria analyst",
            "Strengths and opportunities analyst",
            "Weaknesses and trade-offs analyst",
            "Context and user-fit adviser",
        ],
        chairman_focus=(
            "Return a consistent comparison and avoid a universal winner when fit "
            "depends on context."
        ),
    ),
    "plan": CouncilMode(
        id="plan",
        name="Plan",
        description="Turn a goal into sequenced, actionable steps.",
        objective=(
            "Create a realistic plan with outcomes, sequencing, dependencies, risks and "
            "clear next actions."
        ),
        evaluation_criteria=[
            "Goal alignment",
            "Sequencing",
            "Feasibility",
            "Risk coverage",
            "Actionability",
        ],
        default_roles=[
            "Strategy and outcomes planner",
            "Sequencing and dependencies planner",
            "Risk and resource challenger",
            "Delivery and execution adviser",
        ],
        chairman_focus=(
            "Produce a sequenced plan whose steps have explicit actions and outcomes."
        ),
    ),
    "summarize": CouncilMode(
        id="summarize",
        name="Summarise",
        description="Consolidate content while retaining important nuance and gaps.",
        objective=(
            "Extract the essential meaning, themes, decisions and unresolved points without "
            "adding unsupported content."
        ),
        evaluation_criteria=["Faithfulness", "Coverage", "Clarity", "Conciseness"],
        default_roles=[
            "Key-points extractor",
            "Context and nuance analyst",
            "Contradiction and omission checker",
            "Plain-language editor",
        ],
        chairman_focus=(
            "Provide a faithful synthesis, key points, themes and source gaps."
        ),
    ),
    "fact_check": CouncilMode(
        id="fact_check",
        name="Fact-check",
        description="Assess claims and make uncertainty explicit.",
        objective=(
            "Separate checkable claims from opinion, assess only the evidence available and "
            "mark claims unverified when authoritative support is absent."
        ),
        evaluation_criteria=[
            "Claim identification",
            "Evidence quality",
            "Calibration",
            "Source limitations",
        ],
        default_roles=[
            "Claim verification analyst",
            "Evidence and source-quality critic",
            "Uncertainty and calibration reviewer",
            "Misinterpretation and misinformation analyst",
        ],
        chairman_focus=(
            "Give a verdict per claim and never convert missing evidence into confirmation."
        ),
    ),
}


_MODE_KEYWORDS = (
    (
        "fact_check",
        ("fact check", "fact-check", "verify this claim", "is it true", "validate this claim"),
    ),
    ("summarize", ("summarize", "summarise", "summary of", "key points from", "condense")),
    ("debate", ("debate", "argue for and against", "case for and against", "opposing views")),
    ("brainstorm", ("brainstorm", "generate ideas", "idea for", "ideas for", "creative options")),
    ("compare", ("compare", "comparison", " versus ", " vs ", "differences between")),
    (
        "decide",
        ("help me decide", "which should", "choose between", "recommend between", "best option"),
    ),
    ("plan", ("create a plan", "make a plan", "roadmap", "step by step", "action plan")),
    ("review", ("review", "critique", "assess", "audit", "evaluate this", "check this")),
)


def is_valid_council_mode(mode_id: str) -> bool:
    return mode_id.strip().lower() in MODES


def get_council_mode(mode_id: str | None) -> CouncilMode:
    return MODES.get((mode_id or "auto").strip().lower(), MODES["auto"])


def list_council_modes() -> List[dict]:
    return [asdict(mode) for mode in MODES.values()]


def resolve_council_mode(
    requested_mode: str | None,
    user_query: str,
    *,
    review_profile: str = "general",
) -> CouncilMode:
    normalized = (requested_mode or "auto").strip().lower()
    if normalized != "auto":
        return get_council_mode(normalized)

    lowered = f" {(user_query or '').lower()} "
    for mode_id, keywords in _MODE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return MODES[mode_id]

    if (review_profile or "general").strip().lower() != "general":
        return MODES["review"]
    return MODES["ask"]


def default_roles_for_mode(
    mode: CouncilMode,
    review_profile: ReviewProfile,
) -> List[str]:
    if mode.id == "review":
        return list(review_profile.reviewer_roles)
    return list(mode.default_roles)


def resolve_role_assignments(
    models: List[str],
    mode: CouncilMode,
    review_profile: ReviewProfile,
    custom_roles: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    defaults = default_roles_for_mode(mode, review_profile)
    requested = custom_roles or {}
    assignments: Dict[str, str] = {}
    for index, model in enumerate(models):
        custom = str(requested.get(model, "")).strip()
        assignments[model] = custom or defaults[index % len(defaults)]
    return assignments
