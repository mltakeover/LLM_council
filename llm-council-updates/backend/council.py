"""3-stage LLM Council orchestration."""

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    CHAIRMAN_MODEL,
    COUNCIL_MODELS,
    TITLE_MODEL,
    TITLE_TIMEOUT,
)
from .providers import query_model, query_models_parallel


def _active_models(models: Optional[List[str]]) -> List[str]:
    """Use request-selected models or fall back to configured defaults."""

    return list(models) if models else list(COUNCIL_MODELS)


async def stage1_collect_responses(
    user_query: str,
    models: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Collect independent responses from the selected council models."""

    council_models = _active_models(models)
    messages = [{"role": "user", "content": user_query}]
    responses = await query_models_parallel(council_models, messages)

    stage1_results = []
    for model, response in responses.items():
        if response is not None:
            stage1_results.append({
                "model": model,
                "response": response.get("content", ""),
                "elapsed_seconds": response.get("elapsed_seconds"),
            })

    return stage1_results


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    models: Optional[List[str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Ask the selected models to rank anonymized Stage 1 responses."""

    council_models = _active_models(models)
    labels = [chr(65 + i) for i in range(len(stage1_results))]

    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }

    responses_text = "\n\n".join([
        f"Response {label}:\n{result['response']}"
        for label, result in zip(labels, stage1_results)
    ])

    ranking_prompt = f"""You are evaluating different responses to the following question:

Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, explain what it does well and what it does poorly.
2. Then, at the very end of your response, provide a final ranking.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Do not add any other text or explanations in the ranking section

Example of the correct format for your ENTIRE response:

Response A provides good detail on X but misses Y...
Response B is accurate but lacks depth on Z...
Response C offers the most comprehensive answer...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""

    messages = [{"role": "user", "content": ranking_prompt}]
    responses = await query_models_parallel(council_models, messages)

    stage2_results = []
    for model, response in responses.items():
        if response is not None:
            full_text = response.get("content", "")
            stage2_results.append({
                "model": model,
                "ranking": full_text,
                "parsed_ranking": parse_ranking_from_text(full_text),
                "elapsed_seconds": response.get("elapsed_seconds"),
            })

    return stage2_results, label_to_model


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    chairman_model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the selected chairman to synthesize the council output."""

    active_chairman = chairman_model or CHAIRMAN_MODEL
    stage1_text = "\n\n".join([
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    ])

    stage2_text = "\n\n".join([
        f"Model: {result['model']}\nRanking: {result['ranking']}"
        for result in stage2_results
    ])

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question, and then ranked each other's responses.

Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}

STAGE 2 - Peer Rankings:
{stage2_text}

Your task as Chairman is to synthesize all of this information into a single, comprehensive, accurate answer to the user's original question. Consider:
- The individual responses and their insights
- The peer rankings and what they reveal about response quality
- Any patterns of agreement or disagreement

Provide a clear, well-reasoned final answer that represents the council's collective wisdom:"""

    messages = [{"role": "user", "content": chairman_prompt}]
    response = await query_model(active_chairman, messages)

    if response is None:
        return {
            "model": active_chairman,
            "response": "Error: Unable to generate final synthesis.",
        }

    return {
        "model": active_chairman,
        "response": response.get("content", ""),
        "elapsed_seconds": response.get("elapsed_seconds"),
    }


def parse_ranking_from_text(ranking_text: str) -> List[str]:
    """Parse the FINAL RANKING section from a model response."""

    if "FINAL RANKING:" in ranking_text:
        parts = ranking_text.split("FINAL RANKING:")
        if len(parts) >= 2:
            ranking_section = parts[1]
            numbered_matches = re.findall(
                r"\d+\.\s*Response [A-Z]",
                ranking_section,
            )
            if numbered_matches:
                return [
                    re.search(r"Response [A-Z]", match).group()
                    for match in numbered_matches
                ]

            return re.findall(r"Response [A-Z]", ranking_section)

    return re.findall(r"Response [A-Z]", ranking_text)


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Calculate average rank position across all peer evaluations."""

    model_positions = defaultdict(list)

    for ranking in stage2_results:
        parsed_ranking = parse_ranking_from_text(ranking["ranking"])

        for position, label in enumerate(parsed_ranking, start=1):
            if label in label_to_model:
                model_name = label_to_model[label]
                model_positions[model_name].append(position)

    aggregate = []
    for model, positions in model_positions.items():
        if positions:
            average_rank = sum(positions) / len(positions)
            aggregate.append({
                "model": model,
                "average_rank": round(average_rank, 2),
                "rankings_count": len(positions),
            })

    aggregate.sort(key=lambda item: item["average_rank"])
    return aggregate


async def generate_conversation_title(user_query: str) -> str:
    """Generate a short title using the configured title model."""

    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]
    response = await query_model(
        TITLE_MODEL,
        messages,
        timeout=TITLE_TIMEOUT,
    )

    if response is None:
        return "New Conversation"

    title = response.get("content", "New Conversation").strip()
    title = title.strip("\"'")

    if len(title) > 50:
        title = title[:47] + "..."

    return title


async def run_full_council(
    user_query: str,
    models: Optional[List[str]] = None,
    chairman_model: Optional[str] = None,
) -> Tuple[List, List, Dict, Dict]:
    """Run all council stages using request-selected or default models."""

    council_models = _active_models(models)
    active_chairman = chairman_model or CHAIRMAN_MODEL

    stage1_results = await stage1_collect_responses(
        user_query,
        council_models,
    )

    if not stage1_results:
        return [], [], {
            "model": "error",
            "response": "All models failed to respond. Please try again.",
        }, {
            "models": council_models,
            "chairman_model": active_chairman,
        }

    stage2_results, label_to_model = await stage2_collect_rankings(
        user_query,
        stage1_results,
        council_models,
    )

    aggregate_rankings = calculate_aggregate_rankings(
        stage2_results,
        label_to_model,
    )

    stage3_result = await stage3_synthesize_final(
        user_query,
        stage1_results,
        stage2_results,
        active_chairman,
    )

    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "models": council_models,
        "chairman_model": active_chairman,
    }

    return stage1_results, stage2_results, stage3_result, metadata

