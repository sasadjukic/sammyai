"""Generation parameters for SammyAI's OpenAI Chat Completions adapter."""

import re


# Match known families, including dated snapshots, without treating custom names
# such as "o10" or "gpt-60" as models whose capabilities we know.
_REASONING_FAMILY = re.compile(r"^(?:gpt-(?:5|6)(?:[.-]|$)|o[134](?:-|$))")


def openai_chat_parameters(
    model_name: str,
    *,
    max_tokens: int | None,
    temperature: float | None,
    top_p: float | None,
    seed: int | None,
) -> dict:
    """Return only generation settings that will actually be sent.

    GPT-5/6 and o1/o3/o4 use completion-token budgets, including reasoning.
    SammyAI currently leaves reasoning effort at the provider default, so these
    families also retain provider-managed sampling (no temperature/top_p/seed).
    Some support sampling at effort="none"; we must not disable reasoning merely
    to apply the application's sampling sliders.

    Older and unrecognized model names retain the legacy parameter convention.
    This is an explicit compatibility policy, not capability discovery for every
    model an account may list. New families can be added here independently of
    prompts, writing workflows, and other providers.
    """
    # Fine-tuned IDs have the form ft:<base model>:<organization>:<suffix>:<id>.
    base_model = model_name.split(":", 2)[1] if model_name.startswith("ft:") else model_name
    reasoning = bool(_REASONING_FAMILY.match(base_model))
    parameters = {}
    if max_tokens is not None:
        parameters["max_completion_tokens" if reasoning else "max_tokens"] = max_tokens
    if not reasoning:
        parameters.update({key: value for key, value in (
            ("temperature", temperature), ("top_p", top_p), ("seed", seed),
        ) if value is not None})
    return parameters
