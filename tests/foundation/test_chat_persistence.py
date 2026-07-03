import json
from pathlib import Path

from llm.chat_manager import ChatManager, MessageRole


def test_autosave_persists_each_session_mutation(tmp_path: Path):
    manager = ChatManager(storage_dir=str(tmp_path), autosave=True)
    session = manager.create_session("chapter-planning")
    manager.add_message(MessageRole.USER, "Outline the midpoint reversal.")
    manager.add_message(MessageRole.ASSISTANT, "Here are three approaches.")

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


def test_clear_and_delete_update_persisted_state(tmp_path: Path):
    manager = ChatManager(storage_dir=str(tmp_path), autosave=True)
    manager.create_session("temporary")
    manager.add_message(MessageRole.USER, "Temporary thought")

    assert manager.clear_session("temporary") is True
    saved = json.loads((tmp_path / "temporary.json").read_text(encoding="utf-8"))
    assert saved["messages"] == []

    assert manager.delete_session("temporary") is True
    assert not (tmp_path / "temporary.json").exists()
