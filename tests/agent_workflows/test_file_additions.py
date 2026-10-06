"""Large-file additions retain unseen source text and request-time preconditions."""

import json
from types import SimpleNamespace

import pytest

from llm.chat_manager import ChatManager, MessageRole
from sammyai_core.agent_workflows import AgentType, AgentWorkflowService
from sammyai_core.context_engine import ProjectContextEngine, ProjectFileRepository
from sammyai_core.database import ProjectDatabase
from sammyai_core.file_edit_context import AdditionPolicy, FileContextPolicy, FileEditSnapshot
from sammyai_core.file_tools import SafeFileTools
from sammyai_core.paths import AppPaths
from sammyai_core.projects import ProjectRepository, ProjectService


@pytest.fixture
def environment(tmp_path):
    paths = AppPaths(config_dir=tmp_path / "config", data_dir=tmp_path / "data", cache_dir=tmp_path / "cache", log_dir=tmp_path / "logs").ensure_created()
    database = ProjectDatabase(paths.project_database_path)
    database.migrate()
    projects = ProjectService(ProjectRepository(database), paths)
    root = tmp_path / "novel"
    root.mkdir()
    project = projects.open_project(root)
    tools = SafeFileTools(projects)
    engine = ProjectContextEngine(projects, ProjectFileRepository(database), None)
    yield SimpleNamespace(root=root, project=project, projects=projects, tools=tools, engine=engine, agents=AgentWorkflowService(tools))
    database.close()


def large_breakdown(env):
    source = "".join(f"## Scene {i}\r\n" + (f"Existing story material {i}. " * 70) + "\r\n\r\n" for i in range(1, 20))
    (env.root / "scene_breakdown.md").write_bytes(source.encode("utf-8"))
    return source


def response(files):
    return "Proposal ready.\n<sammyai_changes>" + json.dumps({"summary": "Add material", "files": files}) + "</sammyai_changes>"


def run(env, files, *, query="Add Scene 20 to @scene_breakdown.md", context=None, complete=None, agent=AgentType.EDITOR, policy=None):
    context = context or env.engine.build_context(query)
    return env.agents.run(
        agent, user_request=query,
        messages=[{"role": "system", "content": part} for part in context.system_messages] + [{"role": "user", "content": query}],
        file_snapshots=context.file_snapshots,
        addition_policy=policy,
        complete=complete or (lambda *_args: response(files)),
    )


def test_large_file_append_preserves_original_and_uses_safe_history(environment):
    env = environment
    source = large_breakdown(env)
    context = env.engine.build_context("Add Scene 20 to @scene_breakdown.md")
    assert context.complete_referenced_files == ()
    assert context.truncated and context.total_tokens <= 4_000
    assert "## Scene 19" in "\n".join(context.system_messages)
    result = run(env, [{"path": "scene_breakdown.md", "operation": "append", "content": "## Scene 20\nA new turning point.\n"}], context=context)
    assert result.change_set is not None, result.notices
    path = env.root / "scene_breakdown.md"
    assert path.read_bytes() == source.encode("utf-8")
    env.tools.apply(result.change_set)
    expected = (source + "## Scene 20\r\nA new turning point.\r\n").encode("utf-8")
    assert path.read_bytes() == expected
    env.tools.undo_last()
    assert path.read_bytes() == source.encode("utf-8")
    env.tools.redo_last()
    assert path.read_bytes() == expected


def test_insertion_before_middle_heading_keeps_unseen_scenes(environment):
    env = environment
    source = large_breakdown(env)
    result = run(env, [{"path": "scene_breakdown.md", "operation": "insert_before", "anchor": "## Scene 10", "content": "## Interlude\nA brief exchange.\n\n"}], query="Insert an interlude before Scene 10 in @scene_breakdown.md")
    assert result.change_set is not None, result.notices
    assert result.change_set.changes[0].after_content == source.replace("## Scene 10", "## Interlude\r\nA brief exchange.\r\n\r\n## Scene 10")


@pytest.mark.parametrize("operation", ["write", "delete"])
@pytest.mark.parametrize("path", ["scene_breakdown.md", "./scene_breakdown.md"])
def test_partial_context_cannot_escalate_to_whole_file_change(environment, operation, path):
    env = environment
    source = large_breakdown(env)
    result = run(env, [{"path": path, "operation": operation, "content": "Only a small fragment"}])
    assert result.change_set is None
    assert "partial context" in result.notices[0]
    assert (env.root / "scene_breakdown.md").read_bytes() == source.encode("utf-8")


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_writer_keeps_original_snapshot_through_all_model_stages(environment, stage):
    env = environment
    large_breakdown(env)
    calls = []
    proposal = [{"path": "scene_breakdown.md", "operation": "append", "content": "## Scene 20\nNew scene."}]
    def complete(messages, prompt):
        calls.append(prompt)
        if len(calls) == stage:
            (env.root / "scene_breakdown.md").write_bytes(b"Changed while generating")
        return "Improve the ending" if len(calls) == 2 else response(proposal)
    result = run(env, proposal, agent=AgentType.WRITER, complete=complete)
    assert len(calls) == 3
    assert result.change_set is None
    assert "changed since the request context" in result.notices[0]
    assert (env.root / "scene_breakdown.md").read_bytes() == b"Changed while generating"


def test_complete_file_rewrite_also_rejects_changes_during_generation(environment):
    env = environment
    path = env.root / "scene_breakdown.md"
    path.write_bytes(b"Original")
    def complete(*_args):
        path.write_bytes(b"External edit")
        return response([{"path": path.name, "operation": "write", "content": "Rewritten"}])
    result = run(env, [], complete=complete)
    assert result.change_set is None
    assert "changed since" in result.notices[0]


def test_same_file_name_in_another_project_cannot_receive_addition(environment, tmp_path):
    env = environment
    large_breakdown(env)
    context = env.engine.build_context("Append to @scene_breakdown.md")
    other = tmp_path / "other"
    other.mkdir()
    path = other / "scene_breakdown.md"
    path.write_bytes(b"Different project")
    env.projects.open_project(other)
    result = run(env, [{"path": path.name, "operation": "append", "content": "New"}], context=context)
    assert result.change_set is None
    assert "project changed" in result.notices[0]
    assert path.read_bytes() == b"Different project"


@pytest.mark.parametrize("agent", [AgentType.GENERAL, AgentType.CRITIC])
def test_read_only_agents_cannot_append(environment, agent):
    env = environment
    large_breakdown(env)
    result = run(env, [{"path": "scene_breakdown.md", "operation": "append", "content": "New"}], agent=agent)
    assert result.change_set is None
    assert "read-only" in result.notices[0]


def test_addition_budget_is_independent_of_file_size_and_can_evolve(environment):
    env = environment
    source = large_breakdown(env)
    proposal = [{"path": "scene_breakdown.md", "operation": "append", "content": "x" * 100}]
    blocked = run(env, proposal, policy=AdditionPolicy(max_added_tokens=20))
    assert blocked.change_set is None
    assert "addition budget" in blocked.notices[0]
    allowed = run(env, proposal, policy=AdditionPolicy(max_added_tokens=30))
    assert allowed.change_set.changes[0].after_content == source + "x" * 100


def test_addition_budget_is_aggregated_across_files(environment):
    env = environment
    for name in ("a.md", "b.md"):
        (env.root / name).write_bytes(b"Original\n")
    result = run(env, [{"path": name, "operation": "append", "content": "x" * 40} for name in ("a.md", "b.md")], query="Append to @a.md and @b.md", policy=AdditionPolicy(max_added_tokens=15))
    assert result.change_set is None
    assert "addition budget" in result.notices[0]
    assert (env.root / "a.md").read_bytes() == b"Original\n"


def test_new_chat_context_cannot_replace_request_evidence(environment):
    env = environment
    large_breakdown(env)
    (env.root / "other.md").write_bytes(b"Unrelated file")
    manager = ChatManager(context_engine=env.engine)
    manager.create_session("chat")
    manager.add_message(MessageRole.USER, "Append to @scene_breakdown.md")
    first = manager.prepare_request("Append to @scene_breakdown.md")
    manager.get_messages_for_llm_with_context("Read @other.md")
    assert first.context_result.file_snapshots[0].relative_path == "scene_breakdown.md"
    result = run(env, [{"path": "other.md", "operation": "append", "content": "Wrong target"}], context=first.context_result)
    assert result.change_set is None
    assert "current explicit @file context" in result.notices[0]


def test_context_policy_can_expand_without_changing_file_permissions(environment):
    env = environment
    large_breakdown(env)
    small = env.engine.build_context("Read @scene_breakdown.md")
    env.engine.max_context_tokens = 20_000
    large = env.engine.build_context("Read @scene_breakdown.md")
    assert not small.file_snapshots[0].complete
    assert large.file_snapshots[0].complete
    assert large.file_snapshots[0].source_hash == small.file_snapshots[0].source_hash


def test_resource_limit_or_invalid_utf8_never_grants_edit_evidence(environment):
    env = environment
    env.engine.file_context_policy = FileContextPolicy(max_snapshot_bytes=20)
    path = env.root / "scene_breakdown.md"
    path.write_bytes(b"x" * 21)
    context = env.engine.build_context("Read @scene_breakdown.md")
    assert not context.file_snapshots
    assert "resource limit" in context.notices[0]
    path.write_bytes(b"\xffinvalid")
    context = env.engine.build_context("Read @scene_breakdown.md")
    assert not context.file_snapshots
    assert "Unable to read" in context.notices[0]


@pytest.mark.parametrize("original,operation,anchor,addition,expected", [
    ("", "append", None, "New", "New"),
    ("Old", "append", None, "New", "Old\nNew"),
    ("Old\r\n", "append", None, "New\n", "Old\r\nNew\r\n"),
    ("Before\nAfter", "insert_after", "Before", "New", "Before\nNew\nAfter"),
    ("Before\r\nAfter", "insert_before", "After", "New\n", "Before\r\nNew\r\nAfter"),
    ("\ufeffRésumé 😀", "append", None, "New", "\ufeffRésumé 😀\nNew"),
])
def test_additions_preserve_source_bytes_and_newline_boundaries(original, operation, anchor, addition, expected):
    from editing.change_sets import apply_text_edits
    snapshot = FileEditSnapshot("p", "file.md", original, (), True)
    assert apply_text_edits(original, (snapshot.addition(operation, addition, anchor),)) == expected


@pytest.mark.parametrize("original,visible,anchor,message", [
    ("Repeated\nRepeated\n", ((0, 18),), "Repeated", "ambiguous"),
    ("Hidden\nShown\n", ((7, 13),), "Hidden", "not supplied"),
    ("Real line\n", ((0, 10),), "Invented", "missing"),
    ("Real line\n", ((0, 10),), "Real", "missing"),
])
def test_insertions_need_a_unique_complete_visible_line(original, visible, anchor, message):
    snapshot = FileEditSnapshot("p", "file.md", original, visible)
    with pytest.raises(ValueError, match=message):
        snapshot.addition("insert_before", "New", anchor)


def test_duplicate_numbered_scene_is_checked_against_unseen_content(environment):
    env = environment
    large_breakdown(env)
    result = run(env, [{"path": "scene_breakdown.md", "operation": "append", "content": "## Scene 2: Different title\nDuplicate"}])
    assert result.change_set is None
    assert "already exists" in result.notices[0]


def test_nested_headings_can_repeat_between_new_and_existing_scenes():
    snapshot = FileEditSnapshot("p", "file.md", "## Scene 1\n### Summary\nOld\n", (), True)
    assert snapshot.addition("append", "## Scene 2\n### Summary\nNew\n")


def test_scene_number_can_restart_under_a_different_act():
    snapshot = FileEditSnapshot("p", "file.md", "# Act I\n## Scene 1\nOld\n# Act II\n", (), True)
    assert snapshot.addition("append", "## Scene 1\nNew act's first scene\n")


def test_scene_duplicate_in_same_act_is_rejected_at_middle_insertion():
    snapshot = FileEditSnapshot("p", "file.md", "# Act I\n## Scene 1\nOld\n# Act II\n## Scene 1\nNew\n## Scene 2\nLater\n", (), True)
    with pytest.raises(ValueError, match="already exists"):
        snapshot.addition("insert_before", "## Scene 1\nDuplicate\n", "## Scene 2")


def test_multiple_references_do_not_truncate_a_complete_file_that_fits(environment):
    env = environment
    (env.root / "a.md").write_bytes(b"Text " * 2000)
    (env.root / "b.md").write_bytes(b"Short note")
    context = env.engine.build_context("Read @a.md and @b.md")
    assert context.complete_referenced_files == ("a.md", "b.md")


def test_long_final_paragraph_is_not_replaced_by_blank_tail_context(environment):
    env = environment
    path = env.root / "scene_breakdown.md"
    path.write_bytes(("## Scene 19\n" + "Long paragraph. " * 2000 + "The door closes.\n\n").encode("utf-8"))
    context = env.engine.build_context("Add Scene 20 to @scene_breakdown.md")
    assert "The door closes." in "\n".join(context.system_messages)


def test_addition_without_explicit_reference_has_no_authority(environment):
    env = environment
    large_breakdown(env)
    result = run(env, [{"path": "scene_breakdown.md", "operation": "append", "content": "New"}], query="Add a scene to the breakdown")
    assert result.change_set is None
    assert "explicit @file" in result.notices[0]


@pytest.mark.parametrize("operation", ["append", "insert_before"])
def test_additive_scope_cannot_delete_or_replace_existing_text(environment, operation):
    env = environment
    source = large_breakdown(env)
    item = {"path": "scene_breakdown.md", "operation": operation, "anchor": "## Scene 10", "content": "New", "start": 0, "end": len(source)}
    if operation == "append":
        item.pop("anchor")
    result = run(env, [item], query="Insert before Scene 10 in @scene_breakdown.md")
    assert result.change_set is None
    assert "Unsupported addition fields" in result.notices[0]
    assert (env.root / "scene_breakdown.md").read_bytes() == source.encode("utf-8")


def test_writer_success_keeps_addition_contract_and_all_three_stages(environment):
    env = environment
    source = large_breakdown(env)
    calls = []
    def complete(messages, prompt):
        calls.append((messages, prompt))
        if len(calls) == 2:
            return "Make the new scene more specific."
        content = "## Scene 20\nFirst draft" if len(calls) == 1 else "## Scene 20\nFinal scene"
        return response([{"path": "scene_breakdown.md", "operation": "append", "content": content}])
    result = run(env, [], agent=AgentType.WRITER, complete=complete)
    assert result.model_calls == 3
    assert result.change_set.changes[0].after_content == source + "## Scene 20\r\nFinal scene"
    assert "ONLY the final new material" in calls[2][1]
    assert all(any("Partial file context" in message["content"] for message in messages) for messages, _ in calls)


@pytest.mark.parametrize("operation", [[], {}, None])
def test_invalid_operation_type_is_a_rejection_notice(environment, operation):
    env = environment
    large_breakdown(env)
    result = run(env, [{"path": "scene_breakdown.md", "operation": operation, "content": "New"}])
    assert result.change_set is None
    assert "must be a string" in result.notices[0]
