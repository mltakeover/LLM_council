"""Collaboration strategies for council, workforce, and hybrid runs."""

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class OrchestrationStrategy:
    id: str
    name: str
    description: str
    manager_planning: bool
    peer_review: str
    recommended: bool = False


STRATEGIES: Dict[str, OrchestrationStrategy] = {
    "council": OrchestrationStrategy(
        id="council",
        name="Council",
        description=(
            "Every member answers independently, every available member peer-reviews, "
            "and the Chairman synthesises the result."
        ),
        manager_planning=False,
        peer_review="all",
    ),
    "workforce": OrchestrationStrategy(
        id="workforce",
        name="Workforce",
        description=(
            "A Manager decomposes the request into accountable specialist assignments; "
            "workers deliver their parts and the Master integrates them."
        ),
        manager_planning=True,
        peer_review="none",
    ),
    "hybrid": OrchestrationStrategy(
        id="hybrid",
        name="Hybrid",
        description=(
            "A Manager assigns specialist work, a small targeted QA group challenges the "
            "combined output, and the Master produces the accountable synthesis."
        ),
        manager_planning=True,
        peer_review="targeted",
        recommended=True,
    ),
}


def is_valid_orchestration_strategy(strategy_id: str) -> bool:
    return strategy_id.strip().lower() in STRATEGIES


def get_orchestration_strategy(strategy_id: str | None) -> OrchestrationStrategy:
    return STRATEGIES.get(
        (strategy_id or "hybrid").strip().lower(),
        STRATEGIES["hybrid"],
    )


def list_orchestration_strategies() -> List[dict]:
    return [asdict(strategy) for strategy in STRATEGIES.values()]
