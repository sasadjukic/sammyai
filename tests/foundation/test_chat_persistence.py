import json
from pathlib import Path

from llm.chat_manager import ChatManager, MessageRole


def test_autosave_persists_each_session_mutation(tmp_path: Path):
    manager = ChatManager(storage_dir=str(tmp_path), autosave=True)
    session = manager.create_session("chapter-planning")
    manager.add_message(MessageRole.USER, "Outline the midpoint reversal.")
    manager.add_message(MessageRole.ASSISTANT, "Here are three approaches.")
    manager.set_session_metadata("agent_type", "brainstormer")

    session_file = tmp_path / "chapter-planning.json"
    data = json.loads(session_file.read_text(encoding="utf-8"))

    assert data["session_id"] == session.session_id
    assert [message["role"] for message in data["messages"]] == [
        "user",
        "assistant",
    ]

    reloaded = ChatManager(storage_dir=str(tmp_path))
    assert reloaded.load_all_sessions() == 1
    assert reloaded.get_session(session.session_id).messages[0].content == (
        "Outline the midpoint reversal."
    )
    assert (
        reloaded.get_session_metadata(
            "agent_type",
            session_id=session.session_id,
        )
        == "brainstormer"
    )


def test_clear_and_delete_update_persisted_state(tmp_path: Path):
    manager = ChatManager(storage_dir=str(tmp_path), autosave=True)
    manager.create_session("temporary")
    manager.add_message(MessageRole.USER, "Temporary thought")

    assert manager.clear_session("temporary") is True
    saved = json.loads((tmp_path / "temporary.json").read_text(encoding="utf-8"))
    assert saved["messages"] == []

    assert manager.delete_session("temporary") is True
    assert not (tmp_path / "temporary.json").exists()


def test_delete_project_data_removes_scoped_sessions_and_tagged_messages(tmp_path):
    manager = ChatManager(storage_dir=str(tmp_path), autosave=True)
    manager.create_session("project-chat", metadata={"project_id": "project-1"})
    manager.add_message(
        MessageRole.USER,
        "Project-only message",
        metadata={"project_id": "project-1"},
    )
    manager.create_session("mixed-chat")
    manager.add_message(
        MessageRole.USER,
        "Keep this",
        session_id="mixed-chat",
        metadata={"project_id": "project-2"},
    )
    manager.add_message(
        MessageRole.ASSISTANT,
        "Remove this",
        session_id="mixed-chat",
        metadata={"project_id": "project-1"},
    )
    manager.create_session(
        "switched-project-chat",
        metadata={"project_id": "project-1"},
    )
    manager.add_message(
        MessageRole.USER,
        "Old project message",
        session_id="switched-project-chat",
        metadata={"project_id": "project-1"},
    )
    manager.add_message(
        MessageRole.USER,
        "New project message",
        session_id="switched-project-chat",
        metadata={"project_id": "project-2"},
    )

    deleted_sessions, removed_messages = manager.delete_project_data("project-1")

    assert deleted_sessions == ("project-chat",)
    assert removed_messages == 3
    assert manager.get_session("project-chat") is None
    assert not (tmp_path / "project-chat.json").exists()
    assert [
        message.content for message in manager.get_session("mixed-chat").messages
    ] == ["Keep this"]
    switched = manager.get_session("switched-project-chat")
    assert [message.content for message in switched.messages] == [
        "New project message"
    ]
    assert switched.metadata["project_id"] == "project-2"
