"""Writer revisions must deliver the requested operation against the saved source."""

import json

import pytest

from test_agent_workflows import workflow_service
from sammyai_core.agent_workflows import AgentType


def proposal(operation, *, path="draft.md", content="Scene 1\nNew scene.\n", **fields):
    item = {"path": path, "operation": operation}
    if operation not in {"replace", "delete"}:
        item["content"] = content
    item.update(fields)
    return "Prepared.\n<sammyai_changes>" + json.dumps({
        "summary": "Write the scene", "files": [item],
    }) + "</sammyai_changes>"


def run_writer(service, request, draft, final, *, files=("draft.md",)):
    replies = iter((draft, "Improve the last sentence. Nothing has been saved.", final))
    calls = []

    def complete(messages, prompt):
        calls.append((messages, prompt))
        return next(replies)

    result = service.run(
        AgentType.WRITER, user_request=request,
        messages=[{"role": "user", "content": request}],
        authorized_files=files, complete=complete,
    )
    return result, calls


@pytest.mark.parametrize("original", ["", "Existing scene.\n"])
def test_append_delivers_complete_revised_material_without_applying(workflow_service, original):
    root, service = workflow_service
    path = root / "draft.md"
    path.write_bytes(original.encode("utf-8"))
    result, calls = run_writer(service, "Write Scene 1 and append it to @draft.md",
                               proposal("append", content="First draft."), proposal("append"))
    assert result.outcome == "pending_review"
    assert result.change_set.changes[0].after_content == original + "Scene 1\nNew scene.\n"
    assert path.read_text(encoding="utf-8") == original
    assert len(calls) == 3
    for _messages, prompt in calls:
        assert "Writer file request" in prompt
        assert "draft.md" in prompt and "append" in prompt
        assert "not been saved" in prompt
    assert "Do not emit" in calls[1][1]


@pytest.mark.parametrize("wrong_operation", ["replace", "write", "delete"])
def test_revision_cannot_change_append_into_another_valid_operation(workflow_service, wrong_operation):
    root, service = workflow_service
    (root / "draft.md").write_text("Existing scene.", encoding="utf-8")
    wrong = proposal(wrong_operation, replacements=[{"old_text": "Existing scene.", "new_text": "Changed."}]) if wrong_operation == "replace" else proposal(wrong_operation)
    result, _ = run_writer(service, "Append a scene to @draft.md", proposal("append"), wrong)
    assert result.outcome == "proposal_rejected"
    assert result.change_set is None and result.change_preview is None
    assert "append" in " ".join(result.notices)
    assert result.response.startswith("Writer could not prepare the requested file change.")
    assert "No files were changed." in result.response
    assert (root / "draft.md").read_text(encoding="utf-8") == "Existing scene."


@pytest.mark.parametrize("draft", ["First draft without a directive.", proposal("append")])
def test_missing_final_proposal_is_a_failure_even_when_response_claims_success(workflow_service, draft):
    root, service = workflow_service
    (root / "draft.md").write_text("", encoding="utf-8")
    result, _ = run_writer(service, "Append Scene 1 to @draft.md", draft, "Done, I saved the scene.")
    assert result.outcome == "proposal_rejected"
    assert result.change_set is None
    assert "did not return a file-change proposal" in " ".join(result.notices)
    assert result.response.startswith("Writer could not prepare the requested file change.")


def test_shelf_life_request_does_not_authorize_changes_to_reference_material(workflow_service):
    root, service = workflow_service
    for name in ("bible.md", "outline.md", "breakdowns.md", "draft.md"):
        (root / name).write_text("", encoding="utf-8")
    request = ("Use @bible.md and @outline.md to help you write Scene 1 as outlined in @breakdowns.md. "
               "All your drafts should be stored in @draft.md so feel free to append your drafts to that document.")
    result, _ = run_writer(service, request, proposal("append"), proposal("append", path="bible.md"),
                           files=("bible.md", "outline.md", "breakdowns.md", "draft.md"))
    assert result.outcome == "proposal_rejected"
    assert result.change_set is None
    assert "target" in " ".join(result.notices).lower()


def test_invalid_draft_operation_does_not_prevent_a_correct_final_append(workflow_service):
    root, service = workflow_service
    (root / "draft.md").write_text("", encoding="utf-8")
    result, _ = run_writer(service, "Append a scene to @draft.md", proposal("write"), proposal("append"))
    assert result.outcome == "pending_review"


@pytest.mark.parametrize("user_request", [
    "Use @draft.md to help you write a scene in chat.",
    "Read @draft.md and suggest improvements.",
    "Do not append anything to @draft.md. Explain the ending.",
    "Explain how to append text to @draft.md.",
    "Write a scene inspired by @draft.md.",
])
def test_read_only_references_do_not_require_a_file_change(workflow_service, user_request):
    root, service = workflow_service
    (root / "draft.md").write_text("Source material.", encoding="utf-8")
    result, _ = run_writer(service, user_request, "Draft advice.", "Final advice.")
    assert result.outcome == "responded"
    assert result.response == "Final advice."


@pytest.mark.parametrize("user_request,operation,fields", [
    ("Write the scene to @draft.md", "write", {}),
    ("Insert a scene before the Ending line in @draft.md", "insert_before", {"anchor": "Ending", "content": "Scene\n"}),
    ("Insert a scene after the Ending line in @draft.md", "insert_after", {"anchor": "Ending", "content": "Scene\n"}),
    ("Replace the Ending line in @draft.md", "replace", {"replacements": [{"old_text": "Ending", "new_text": "Finale"}]}),
])
def test_other_explicit_operations_survive_revision(workflow_service, user_request, operation, fields):
    root, service = workflow_service
    (root / "draft.md").write_text("Ending\n", encoding="utf-8")
    result, _ = run_writer(service, user_request, proposal(operation, **fields), proposal(operation, **fields))
    assert result.outcome == "pending_review"
    wrong, _ = run_writer(service, user_request, proposal(operation, **fields), proposal("append"))
    assert wrong.outcome == "proposal_rejected"


def test_valid_draft_establishes_operation_when_user_only_names_storage(workflow_service):
    root, service = workflow_service
    (root / "draft.md").write_bytes(b"Existing material.")
    result, calls = run_writer(service, "Store the new scene in @draft.md", proposal("append"), proposal("write"))
    assert result.outcome == "proposal_rejected"
    assert "draft.md: append\n" in calls[1][1] and "draft.md: append\n" in calls[2][1]


def test_all_requested_destinations_must_be_present(workflow_service):
    root, service = workflow_service
    for name in ("draft.md", "other.md"):
        (root / name).write_bytes(b"")
    result, _ = run_writer(service, "Append a scene to @draft.md and @other.md", "Draft", proposal("append"), files=("draft.md", "other.md"))
    assert result.outcome == "proposal_rejected"
    assert "target" in result.notices[0]


def test_mixed_operations_are_bound_to_their_own_destinations(workflow_service):
    root, service = workflow_service
    (root / "draft.md").write_bytes(b"Keep this.\n")
    (root / "notes.md").write_bytes(b"Old notes.")
    directive = {"summary": "Scene and notes", "files": [
        {"path": "draft.md", "operation": "append", "content": "New scene."},
        {"path": "notes.md", "operation": "write", "content": "New notes."},
    ]}
    response = "<sammyai_changes>" + json.dumps(directive) + "</sammyai_changes>"
    result, _ = run_writer(service, "Append a scene to @draft.md and rewrite @notes.md", response, response, files=("draft.md", "notes.md"))
    assert result.outcome == "pending_review"
    assert [c.after_content for c in result.change_set.changes] == ["Keep this.\nNew scene.", "New notes."]


def test_empty_final_revision_cannot_fall_back_to_an_unreviewed_draft_proposal(workflow_service):
    root, service = workflow_service
    (root / "draft.md").write_bytes(b"")
    result, _ = run_writer(service, "Append a scene to @draft.md", proposal("append"), "")
    assert result.outcome == "incomplete_response"
    assert result.change_set is None
    assert "No files were changed." in result.response
    assert result.events[-1].stage == "failed"


def test_october_28_revision_cannot_replace_its_own_unsaved_draft(workflow_service):
    root, service = workflow_service
    (root / "draft.md").write_bytes(b"")
    final = '''I will improve the scene's last sentence.
<sammyai_edits>
summary: Refine the scene
file: draft.md
operation: replace
<<<SAMMYAI_SEARCH>>>
First draft sentence that was never saved.
<<<SAMMYAI_REPLACEMENT>>>
Improved sentence.
<<<SAMMYAI_END>>>
</sammyai_edits>'''
    result, _ = run_writer(service, "Append Scene 1 to @draft.md", "First draft sentence that was never saved.", final)
    assert result.outcome == "proposal_rejected"
    assert result.change_set is None
    assert result.events[-1].stage == "failed"
    assert "append" in result.notices[0]
    assert (root / "draft.md").read_bytes() == b""


@pytest.mark.parametrize("user_request", [
    "In @draft.md, append Scene 1.",
    "@draft.md: append Scene 1.",
    "Save the new scene in @draft.md. Append it to that document.",
    "Store the scene in @draft.md. Append it to it.",
])
def test_explicit_destination_wording_still_requires_append(workflow_service, user_request):
    root, service = workflow_service
    (root / "draft.md").write_bytes(b"")
    result, _ = run_writer(service, user_request, "Draft", "Final prose without a proposal.")
    assert result.outcome == "proposal_rejected"
    wrong, _ = run_writer(service, user_request, "Draft", proposal("write"))
    assert wrong.outcome == "proposal_rejected"


@pytest.mark.parametrize("reference,path", [
    ("@draft.md", "chapters/draft.md"),
    ("@./draft.md", "draft.md"),
    ('@"draft one.md"', "draft one.md"),
])
def test_destination_uses_resolved_snapshot_identity(workflow_service, reference, path):
    root, service = workflow_service
    destination = root / path
    destination.parent.mkdir(exist_ok=True)
    destination.write_bytes(b"")
    response = proposal("append", path=path)
    result, _ = run_writer(service, f"Append a scene to {reference}", response, response, files=(path,))
    assert result.outcome == "pending_review"
    assert result.change_set.changes[0].relative_path == path
