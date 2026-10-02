"""Estimated USD costs from the installed LiteLLM pricing catalog."""

import math

import litellm


def calculate_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    usage_object=None,
    response=None,
) -> float | None:
    model = model_name
    if "/" not in model and model.startswith("gemini"):
        model = f"gemini/{model}"
    if "/" not in model and model.startswith("claude"):
        model = f"anthropic/{model}"
    try:
        costs = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            usage_object=usage_object,
            response=response,
        )
        total = float(sum(costs))
        return round(total, 10) if math.isfinite(total) and total >= 0 else None
    except Exception:
        # Unknown pricing must not be presented as a free request.
        return None
