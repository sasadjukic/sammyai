from llm.prompt_layers import (
    PromptComposer,
    PromptLayer,
    PromptLayerOrder,
)


def test_prompt_layers_are_composed_in_policy_order():
    prompt = PromptComposer().compose(
        (
            PromptLayer("Output", "output rules", PromptLayerOrder.OUTPUT),
            PromptLayer("Core", "core rules", PromptLayerOrder.CORE),
            PromptLayer("Agent", "agent role", PromptLayerOrder.AGENT),
        )
    )

    assert prompt.index("## Core") < prompt.index("## Agent")
    assert prompt.index("## Agent") < prompt.index("## Output")
