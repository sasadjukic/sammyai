import json

import pytest

from sammyai_core.memory import (
    ConversationSummarizer,
    MemoryError,
    MemoryKind,
)


def test_summarizer_returns_reviewable_structured_draft():
    payload = {
        "title": "Mara's midpoint",
        "summary": "The user chose a forged-map reveal at the midpoint.",
        "memories": [
            {
                "kind": "decision",
                "title": "Forged map",
                "content": "The forged map is revealed at the midpoint.",
                "confidence": 0.95,
            },
            {
                "kind": "unknown-kind",
                "title": "Storm",
                "content": "A storm begins after the reveal.",
                "confidence": 4,
            },
        ],
    }
    calls = []

    draft = ConversationSummarizer().generate(
        project_id="project-1",
        session_id="session-1",
        messages=(
            {"role": "user", "content": "Use the forged map reveal."},
            {"role": "assistant", "content": "That works at the midpoint."},
        ),
        complete=lambda messages, prompt: (
            calls.append((messages, prompt)) or json.dumps(payload)
        ),
    )

    assert draft.title == "Mara's midpoint"
    assert draft.message_count == 2
    assert draft.suggested_memories[0].kind == MemoryKind.DECISION
    assert draft.suggested_memories[1].kind == MemoryKind.OTHER
    assert draft.suggested_memories[1].confidence == 1.0
    assert "Conversation Memory" in calls[0][1]


def test_summarizer_rejects_empty_chat_and_invalid_json():
    summarizer = ConversationSummarizer()
    with pytest.raises(MemoryError, match="no messages"):
        summarizer.generate(
            project_id="project",
            session_id="session",
            messages=[],
            complete=lambda _messages, _prompt: "{}",
        )

    with pytest.raises(MemoryError, match="Unable to parse"):
        summarizer.generate(
            project_id="project",
            session_id="session",
            messages=[{"role": "user", "content": "Remember this."}],
            complete=lambda _messages, _prompt: "not-json",
        )
