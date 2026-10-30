"""Project transitions preserve unsaved work and keep each saved workspace separate."""

import pytest
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from test_close_project import open_file
from test_inline_review import review_window, start
from test_selection_actions import prepare
from sammyai_core.projects import ACTIVE_PROJECT_KEY
from sammyai_core.selection_actions import SelectionAction


ROUTES = ("folder", "recent", "create", "relocate")


def destination(window, parent, route, monkeypatch):
    target = parent / "shelf-life"
    service = window.project_service
    project = None
    if route != "create":
        target.mkdir()
        registered_root = target
        if route == "relocate":
            registered_root = parent / "old-shelf-life"
            registered_root.mkdir()
        project = service.repository.create("Shelf Life", registered_root)
        if route == "relocate":
            registered_root.rmdir()
    if route == "folder":
        switch = lambda: window._open_project_path(target)
    elif route == "recent":
        switch = lambda: window._open_registered_project(project.id)
    elif route == "create":
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(parent))
        monkeypatch.setattr(QInputDialog, "getText", lambda *a: (target.name, True))
        switch = window._create_project
    else:
        monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: str(target))
        switch = lambda: window._locate_moved_project(project.id)
    return target, project, switch


@pytest.mark.parametrize("route", ROUTES)
def test_switch_closes_outgoing_tabs_and_preserves_both_workspaces(review_window, tmp_path, monkeypatch, route):
    window, root = review_window
    workspace = window.editor_workspace
    service = window.project_service
    outgoing = service.active_project
    target, incoming, switch = destination(window, tmp_path, route, monkeypatch)
    if incoming:
        (target / "one.md").write_bytes(b"Other project's first file")
        (target / "two.md").write_bytes(b"Other project's second file")
        service.set_project_setting(incoming.id, "editor_open_paths", ["one.md", "two.md"])
        service.set_project_setting(incoming.id, "editor_active_path", "two.md")
    scratch = workspace.active_session()
    window.editor.insertPlainText("Unsaved scratch")
    outside = open_file(window, tmp_path / "notes.md")
    window.editor.insertPlainText("Unsaved outside ")
    first = open_file(window, root / "one.md")
    second = open_file(window, root / "chapters" / "two.md")
    workspace.activate_document(first.session_id)

    switch()

    assert service.active_project.root_path == target
    assert window.project_explorer.project.id == service.active_project.id
    assert service.repository.get_application_state(ACTIVE_PROJECT_KEY) == service.active_project.id
    assert workspace.session(first.session_id) is None
    assert workspace.session(second.session_id) is None
    assert scratch.is_modified and scratch.content == "Unsaved scratch"
    assert outside.is_modified and outside.content == "Unsaved outside Original"
    assert service.get_project_setting(outgoing.id, "editor_open_paths") == ["one.md", "chapters/two.md"]
    assert service.get_project_setting(outgoing.id, "editor_active_path") == "one.md"
    if incoming:
        assert window.current_file == str(target / "two.md")
        assert window.editor.toPlainText() == "Other project's second file"
        assert service.get_project_setting(incoming.id, "editor_open_paths") == ["one.md", "two.md"]
        assert service.get_project_setting(incoming.id, "editor_active_path") == "two.md"

    window._open_registered_project(outgoing.id)

    assert window.current_file == str(first.path)
    assert {s.path for s in workspace.sessions() if s.path} == {first.path, second.path, outside.path}
    assert (root / "one.md").read_bytes() == b"Original"


@pytest.mark.parametrize("route", ROUTES)
def test_cancel_switch_keeps_all_tabs_and_unsaved_buffers(review_window, tmp_path, monkeypatch, route):
    window, root = review_window
    project = window.project_service.active_project
    target, _, switch = destination(window, tmp_path, route, monkeypatch)
    first = open_file(window, root / "one.md")
    window.editor.insertPlainText("One ")
    second = open_file(window, root / "two.md")
    window.editor.insertPlainText("Two ")
    sessions = window.editor_workspace.sessions()
    choices = iter([QMessageBox.Discard, QMessageBox.Cancel])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: next(choices))

    switch()

    assert window.project_service.active_project.id == project.id
    assert window.project_explorer.project.id == project.id
    assert window.project_service.repository.get_application_state(ACTIVE_PROJECT_KEY) == project.id
    assert window.editor_workspace.sessions() == sessions
    assert first.content == "One Original" and first.is_modified
    assert second.content == "Two Original" and second.is_modified
    if route == "create":
        assert not target.exists()


@pytest.mark.parametrize("choice,expected", [(QMessageBox.Save, b"Changed Original"), (QMessageBox.Discard, b"Original")])
def test_switch_resolves_dirty_background_file(review_window, tmp_path, monkeypatch, choice, expected):
    window, root = review_window
    target, _, switch = destination(window, tmp_path, "folder", monkeypatch)
    dirty = open_file(window, root / "one.md")
    window.editor.insertPlainText("Changed ")
    open_file(window, root / "active.md")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: choice)

    switch()

    assert window.project_service.active_project.root_path == target
    assert window.editor_workspace.session(dirty.session_id) is None
    assert dirty.path.read_bytes() == expected


def test_failed_save_aborts_switch(review_window, tmp_path, monkeypatch):
    window, root = review_window
    _, _, switch = destination(window, tmp_path, "folder", monkeypatch)
    dirty = open_file(window, root / "one.md")
    window.editor.insertPlainText("Unsaved ")
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Save)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a[2]))

    def fail(*args):
        raise OSError("Cannot save outgoing file")

    monkeypatch.setattr(window.document_service, "write_text", fail)
    switch()

    assert window.project_service.active_project.root_path == root
    assert window.editor_workspace.session(dirty.session_id) is dirty
    assert dirty.is_modified
    assert errors == ["Cannot save outgoing file"]


@pytest.mark.parametrize("route", ROUTES)
def test_destination_failure_keeps_current_project_and_discarded_buffer(review_window, tmp_path, monkeypatch, route):
    window, root = review_window
    project = window.project_service.active_project
    target, _, switch = destination(window, tmp_path, route, monkeypatch)
    if route == "create":
        target.mkdir()  # creation must fail without replacing the existing directory
    else:
        target.rmdir()  # open/relocate must fail on a missing destination
    dirty = open_file(window, root / "one.md")
    window.editor.insertPlainText("Unsaved ")
    sessions = window.editor_workspace.sessions()
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Discard)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: errors.append(a[2]))

    switch()

    assert errors
    assert window.project_service.active_project.id == project.id
    assert window.project_explorer.project.id == project.id
    assert window.project_service.repository.get_application_state(ACTIVE_PROJECT_KEY) == project.id
    assert window.editor_workspace.sessions() == sessions
    assert dirty.content == "Unsaved Original" and dirty.is_modified
    assert dirty.path.read_bytes() == b"Original"


@pytest.mark.parametrize("route", ["folder", "recent"])
def test_reopening_current_project_keeps_buffers_and_review_without_prompt(review_window, monkeypatch, route):
    window, root = review_window
    batch = start(window, root)
    dirty = open_file(window, root / "dirty.md")
    window.editor.insertPlainText("Unsaved ")
    sessions = window.editor_workspace.sessions()

    def unexpected_prompt(*args, **kwargs):
        pytest.fail("Reopening the current project must not ask to discard its work")

    monkeypatch.setattr(QMessageBox, "warning", unexpected_prompt)
    if route == "folder":
        window._open_project_path(root / "subfolder" / "..")
    else:
        window._open_registered_project(window.project_service.active_project.id)

    assert window.editor_workspace.sessions() == sessions
    assert window.editor_workspace.active_session() is dirty
    assert window.review_controller.batches[batch.id] is batch


def test_switch_discards_review_without_persisting_unapplied_create(review_window, tmp_path, monkeypatch):
    window, root = review_window
    project = window.project_service.active_project
    target, _, switch = destination(window, tmp_path, "folder", monkeypatch)
    start(window, root, {"one.md": ("Original", "Proposal"), "new.md": (None, "New proposal")})
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Discard)

    switch()

    assert window.project_service.active_project.root_path == target
    assert not window.review_controller.batches
    assert all(s.path is None for s in window.editor_workspace.sessions())
    assert (root / "one.md").read_bytes() == b"Original"
    assert not (root / "new.md").exists()
    assert window.project_service.get_project_setting(project.id, "editor_open_paths") == ["one.md"]


def test_switch_cancels_pending_selection_and_clears_pinned_source(review_window, tmp_path, monkeypatch):
    window, root = review_window
    target, _, switch = destination(window, tmp_path, "folder", monkeypatch)
    tab = open_file(window, root / "one.md", "Before.\nOld passage.\nAfter.")
    snapshot, _, workers = prepare(window, monkeypatch, '{"kind":"replacement","text":"New passage."}', deferred=True)
    window.selection_actions.start(snapshot, SelectionAction.REWRITE)
    pending = window.selection_actions.pending
    window.chat_panel.set_selection_reference(snapshot, pinned=True)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.Discard)

    switch()
    workers.pop()()

    assert window.project_service.active_project.root_path == target
    assert window.editor_workspace.session(tab.session_id) is None
    assert pending.canceled.is_set()
    assert window.selection_actions.pending is None
    assert window.chat_panel.selection_reference is None
    assert not window.review_controller.batches
    assert window.trace_service.detail(pending.identity.request_id)["request"]["outcome"] == "canceled"


def test_canceled_new_project_picker_leaves_review_untouched(review_window, monkeypatch):
    window, root = review_window
    batch = start(window, root)
    prompts = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a: "")
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: prompts.append(a[2]) or QMessageBox.Discard)

    window._create_project()

    assert not prompts
    assert window.review_controller.batches[batch.id] is batch
