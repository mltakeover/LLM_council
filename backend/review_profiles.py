"""Built-in review profiles for architecture, design and code councils."""

from dataclasses import asdict, dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ReviewProfile:
    id: str
    name: str
    description: str
    objective: str
    reviewer_roles: List[str]
    finding_categories: List[str]


PROFILES: Dict[str, ReviewProfile] = {
    "general": ReviewProfile(
        id="general",
        name="General review",
        description="Balanced review for questions and technical decisions.",
        objective=(
            "Assess correctness, evidence, risks, missing information and "
            "practical next steps. Separate confirmed findings from assumptions."
        ),
        reviewer_roles=[
            "Accuracy and evidence reviewer",
            "Risk and edge-case reviewer",
            "Clarity and usability reviewer",
            "Implementation feasibility reviewer",
        ],
        finding_categories=[
            "Correctness",
            "Risk",
            "Completeness",
            "Delivery",
        ],
    ),
    "hld": ReviewProfile(
        id="hld",
        name="HLD review",
        description="Technical-design-authority review of a high-level design.",
        objective=(
            "Review architecture boundaries, security, scalability, resilience, "
            "integration, data, operations, cost, delivery and non-functional "
            "requirements. Identify assumptions, dependencies and open questions."
        ),
        reviewer_roles=[
            "Enterprise and solution architecture reviewer",
            "Security, privacy and compliance reviewer",
            "Scalability, resilience and performance reviewer",
            "Operations, observability and support reviewer",
            "Cost, delivery and dependency reviewer",
        ],
        finding_categories=[
            "Architecture",
            "Security",
            "Scalability",
            "Resilience",
            "Integration",
            "Data",
            "Operations",
            "Cost and delivery",
        ],
    ),
    "lld": ReviewProfile(
        id="lld",
        name="LLD review",
        description="Detailed design review focused on buildability and support.",
        objective=(
            "Review component responsibilities, interfaces, data contracts, "
            "failure handling, concurrency, security, deployment, configuration, "
            "testing, observability and operational support."
        ),
        reviewer_roles=[
            "Component and interface design reviewer",
            "Data and integration contract reviewer",
            "Security and failure-mode reviewer",
            "Testing and maintainability reviewer",
            "Deployment and operations reviewer",
        ],
        finding_categories=[
            "Components",
            "Interfaces",
            "Data contracts",
            "Failure handling",
            "Security",
            "Testing",
            "Deployment",
            "Operations",
        ],
    ),
    "code": ReviewProfile(
        id="code",
        name="Code review",
        description="Evidence-based review of source code and tests.",
        objective=(
            "Find functional defects, security weaknesses, concurrency risks, "
            "error-handling gaps, performance issues, maintainability problems "
            "and missing tests. Do not claim a defect without code evidence."
        ),
        reviewer_roles=[
            "Correctness and edge-case reviewer",
            "Application security reviewer",
            "Concurrency and performance reviewer",
            "Maintainability and API-design reviewer",
            "Testing and operations reviewer",
        ],
        finding_categories=[
            "Correctness",
            "Security",
            "Concurrency",
            "Performance",
            "Maintainability",
            "Testing",
            "Operations",
        ],
    ),
    "security": ReviewProfile(
        id="security",
        name="Security review",
        description="Threat-focused review of a design or implementation.",
        objective=(
            "Assess trust boundaries, authentication, authorisation, secrets, "
            "input handling, data protection, dependencies, logging, abuse cases, "
            "supply-chain risk and incident response."
        ),
        reviewer_roles=[
            "Threat-modelling reviewer",
            "Identity and access-control reviewer",
            "Data-protection and privacy reviewer",
            "Application and dependency security reviewer",
            "Detection and incident-response reviewer",
        ],
        finding_categories=[
            "Threats",
            "Identity",
            "Data protection",
            "Application security",
            "Dependencies",
            "Detection and response",
        ],
    ),
}


def get_review_profile(profile_id: str | None) -> ReviewProfile:
    return PROFILES.get((profile_id or "general").strip().lower(), PROFILES["general"])


def is_valid_review_profile(profile_id: str) -> bool:
    return profile_id.strip().lower() in PROFILES


def list_review_profiles() -> List[dict]:
    return [asdict(profile) for profile in PROFILES.values()]
