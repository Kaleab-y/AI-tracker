"""
Pricing lookup for LLM models.

Prices are stored as USD per 1 million tokens for both input and output.
This table can be extended as new models or providers are added.
Last updated: 2026-05-02
"""

from typing import Optional

# ──────────────────────────────────────────────────────────────────────
# Model pricing table
# Format: "model_name": (input_price_per_1M_tokens, output_price_per_1M_tokens)
# ──────────────────────────────────────────────────────────────────────

MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI — GPT-4o family
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o-2024-11-20": (2.50, 10.00),
    "gpt-4o-2024-08-06": (2.50, 10.00),
    "gpt-4o-2024-05-13": (5.00, 15.00),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    # OpenAI — GPT-4.1 family
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    # OpenAI — GPT-4 Turbo & GPT-4
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4-turbo-2024-04-09": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-4-32k": (60.00, 120.00),
    # OpenAI — GPT-3.5 Turbo
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-3.5-turbo-0125": (0.50, 1.50),
    "gpt-3.5-turbo-1106": (1.00, 2.00),
    # OpenAI — o-series (reasoning)
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
    "o1-preview": (15.00, 60.00),
    "o3": (10.00, 40.00),
    "o3-mini": (1.10, 4.40),
    "o4-mini": (1.10, 4.40),
}


def get_model_pricing(model_name: str) -> Optional[tuple[float, float]]:
    """
    Look up the (input, output) price per 1M tokens for a given model.

    Returns None if the model is not found in the pricing table.
    """
    return MODEL_PRICING.get(model_name)


def calculate_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> Optional[float]:
    """
    Calculate the total USD cost for a request based on token counts.

    Returns None if the model has no known pricing.
    """
    pricing = get_model_pricing(model_name)
    if pricing is None:
        return None

    input_price_per_token, output_price_per_token = pricing

    input_cost = (prompt_tokens / 1_000_000) * input_price_per_token
    output_cost = (completion_tokens / 1_000_000) * output_price_per_token

    return round(input_cost + output_cost, 8)
