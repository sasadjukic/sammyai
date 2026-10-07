"""Existing request boundaries that diagnostics must preserve."""
import json

import pytest

from llm.chat_manager import ChatSession, MessageRole
from sammyai_core.agent_workflows import AgentType, AgentWorkflowService


def test_caught_bad_json_returns_notice_without_a_change_set():
    result = AgentWorkflowService(None).run(
        AgentType.EDITOR, user_request="Edit", messages=[],
        complete=lambda *_: '<sammyai_changes>{"files": broken}</sammyai_changes>',
    )
    assert result.change_set is None
    assert result.notices[0].startswith("File proposal rejected:")


def test_provider_exception_is_not_converted_to_a_successful_response():
    def fail(*_):
        raise RuntimeError("provider unavailable")
    with pytest.raises(RuntimeError, match="provider unavailable"):
        AgentWorkflowService(None).run("general", user_request="Hello", messages=[], complete=fail)


def test_message_metadata_never_enters_provider_messages():
    session = ChatSession("origin")
    session.add_message(MessageRole.USER, "Hello", {"request_id": "request", "diagnostic": "private"})
    assert session.get_messages_for_llm() == [{"role": "user", "content": "Hello"}]
