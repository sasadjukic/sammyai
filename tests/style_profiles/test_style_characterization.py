"""No-profile fingerprints captured from the accepted v0.6.2 baseline."""

import hashlib
import json
from pathlib import Path

from sammyai_core.agent_workflows import AgentType, AgentWorkflowService
from sammyai_core.selection_actions import SelectionAction, SelectionActionRequest, SelectionSnapshot


def prompt_fingerprints():
    fingerprints = {}
    for agent in AgentType:
        prompts = []
        AgentWorkflowService(None).run(
            agent, user_request="Write a paragraph.",
            messages=[{"role": "user", "content": "Write a paragraph."}],
            complete=lambda messages, prompt: prompts.append(prompt) or "Sample prose.",
        )
        fingerprints[agent.value] = [hashlib.sha256(p.encode()).hexdigest() for p in prompts]
    snapshot = SelectionSnapshot("document", None, "Untitled", "hash", "A passage.", 1, None, 0, 10, "text")
    for action in SelectionAction:
        request = SelectionActionRequest(snapshot, action, "chat", None, "playful")
        payload = json.dumps([request.system_prompt(), request.messages()], sort_keys=True)
        fingerprints["selection_" + action.value] = hashlib.sha256(payload.encode()).hexdigest()
    return fingerprints


def test_no_profile_prompts_match_accepted_baseline():
    expected = json.loads(Path(__file__).with_name("baseline_prompts.json").read_text())
    assert prompt_fingerprints() == expected
