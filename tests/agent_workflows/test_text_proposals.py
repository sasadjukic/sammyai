"""Literal writing transport and exact replacements through real file tools."""
import json

import pytest

from test_file_additions import environment
from sammyai_core.agent_workflows import AgentWorkflowService
from sammyai_core.file_edit_context import FileEditSnapshot
from sammyai_core.file_tools import ChangeConflictError
from sammyai_core.proposal_protocol import (
    ANCHOR, CONTENT, END, REPLACEMENT, SEARCH, TEXT_OUTPUT_PROMPT, ProposalFormatError,
)


def block(marker, text, closing=END):
    return f"{marker}\n{text}\n{closing}\n"


def proposal(body, *, prefix="Ready for review.\n", suffix=""):
    return prefix + '<sammyai_edits>\nsummary: Revise requested passages\n' + body + '</sammyai_edits>\n' + suffix


def replacements(pairs, path="chapter.md"):
    return f"file: {path}\noperation: replace\n" + "".join(
        block(SEARCH, old, REPLACEMENT) + new + f"\n{END}\n" for old, new in pairs
    )


def run(env, source, *, snapshots=None, agent="editor", metadata=None, complete=None):
    context = env.engine.build_context("Revise @chapter.md")
    return env.agents.run(agent, user_request="Revise @chapter.md", messages=[],
                          file_snapshots=context.file_snapshots if snapshots is None else snapshots,
                          complete=complete or (lambda *_: source), response_metadata=lambda: metadata or {})


@pytest.mark.parametrize("text", [
    '  "Quoted" dialogue.\nLiteral escapes: \\n \\" C:\\drafts\\story\n\n',
    'Unicode: café — 你好.\u2028Still the same control line.\n',
    '<sammyai_changes>\n{"content":"not a directive"}\n</sammyai_changes>',
    'file: this is prose\noperation: also prose\n```json\n{"x":1}\n```',
    '', '\n', 'Leading and trailing spaces  ',
])
def test_raw_file_content_round_trips_without_escaping(text):
    source = proposal('file: chapter.md\noperation: write\n' + block(CONTENT, text), suffix="Please review.")
    visible, directive = AgentWorkflowService._extract_change_directive(source)
    assert visible == "Ready for review.\nPlease review."
    assert directive["files"] == [{"path": "chapter.md", "operation": "write", "content": text}]


def test_windows_transport_framing_preserves_literal_content():
    source = proposal('file: chapter.md\noperation: write\n' + block(CONTENT, "Line one\nLine two\n")).replace('\n', '\r\n')
    _, directive = AgentWorkflowService._extract_change_directive(source)
    assert directive["files"][0]["content"] == "Line one\r\nLine two\r\n"


@pytest.mark.parametrize("source", [
    '<sammyai_edits>\nsummary: Missing files\n</sammyai_edits>',
    '<sammyai_edits>\nsummary: Missing envelope end\nfile: c.md\noperation: delete',
    '<SAMMYAI_EDITS>PRIVATE',
    '</sammyai_edits>PRIVATE',
    '< sammyai_edits>PRIVATE',
    proposal('file: c.md\noperation: unknown\n'),
    proposal('file: c.md\noperation: replace\n'),
    proposal('file: c.md\noperation: write\n<<<SAMMYAI_CONTENT>>>\nPRIVATE\n'),
    proposal('file: c.md\noperation: replace\n' + block(SEARCH, 'PRIVATE', END)),
    proposal('file: c.md\noperation: write\n' + block(CONTENT, 'PRIVATE\n<<<SAMMYAI_SEARCH>>>')),
    proposal('file: c.md\noperation: delete\nunexpected: PRIVATE\n'),
])
def test_malformed_blocks_rejected_without_leaking_content(source):
    result = AgentWorkflowService(None).run("editor", user_request="Edit", messages=[], complete=lambda *_: source)
    assert result.change_set is None and result.outcome == "proposal_rejected"
    assert "PRIVATE" not in result.response + " ".join(result.notices)


@pytest.mark.parametrize("other", [
    '<sammyai_changes>{"files":[]}</sammyai_changes>',
    proposal('file: c.md\noperation: delete\n'),
    '<sammyai_edits>',
])
@pytest.mark.parametrize("before", [False, True])
def test_multiple_or_mixed_protocols_fail_closed(other, before):
    source = proposal('file: c.md\noperation: delete\n')
    with pytest.raises((ValueError, ProposalFormatError)):
        AgentWorkflowService._extract_change_directive(other + '\n' + source if before else source + '\n' + other)


def test_legacy_json_can_contain_a_literal_new_tag():
    directive = {"files": [{"path": "c.md", "operation": "write", "content": '<sammyai_edits>'}]}
    source = '<sammyai_changes>' + json.dumps(directive) + '</sammyai_changes>'
    assert AgentWorkflowService._extract_change_directive(source)[1] == directive


def test_four_replacements_preserve_untouched_windows_text_and_history(environment):
    env = environment
    path = env.root / 'chapter.md'
    passages = [f'## Part {i}\r\nOld "role" {i}.\r\n' for i in range(1, 5)]
    gap = '\r\nUnchanged background.\r\n' * 8
    original = 'Unchanged opening.\r\n' + gap.join(passages) + 'Unchanged ending.\r\n'
    path.write_bytes(original.encode())
    pairs = [(old.replace('\r\n', '\n'), old.replace('Old "role"', 'New "role"').replace('\r\n', '\n')) for old in passages]
    result = run(env, proposal(replacements(pairs)))
    assert result.outcome == "pending_review", result.notices
    assert len(result.change_set.changes) == 1 and len(result.change_preview.files) == 1
    expected = original.replace('Old "role"', 'New "role"')
    assert result.change_set.changes[0].after_content == expected
    assert result.model_calls == 1
    assert path.read_bytes() == original.encode()
    env.tools.apply(result.change_set)
    assert path.read_bytes() == expected.encode()
    env.tools.undo_last()
    assert path.read_bytes() == original.encode()
    env.tools.redo_last()
    assert path.read_bytes() == expected.encode()


@pytest.mark.parametrize("original,pairs,reason", [
    ('One repeated. Two repeated.', [('repeated', 'new')], 'ambiguous'),
    ('ababa', [('aba', 'new')], 'ambiguous'),
    ('Unique passage', [('unique passage', 'new')], 'not found'),
    ('Unique  passage', [('Unique passage', 'new')], 'not found'),
    ('Unique passage', [('', 'new')], 'nonempty'),
    ('Unique passage', [('Unique', 'new'), ('Unique passage', 'other')], 'overlap'),
    ('Original', [('Original', 'New'), ('New', 'Newer')], 'not found'),
])
def test_invalid_searches_reject_the_whole_proposal(environment, original, pairs, reason):
    env = environment
    path = env.root / 'chapter.md'
    path.write_bytes(original.encode())
    result = run(env, proposal(replacements(pairs)))
    assert result.outcome == 'proposal_rejected'
    assert result.change_set is None and reason in result.notices[0]
    assert path.read_bytes() == original.encode()


def test_partial_context_only_allows_fully_visible_replacements(environment):
    env = environment
    original = 'Hidden beginning.\r\nVisible old passage.\r\nHidden ending.'
    (env.root / 'chapter.md').write_bytes(original.encode())
    start = original.index('Visible')
    end = original.index('Hidden ending')
    snapshot = FileEditSnapshot(env.project.id, 'chapter.md', original, ((start, end),), False)
    allowed = run(env, proposal(replacements([('Visible old passage.', 'Visible new passage.')])), snapshots=(snapshot,))
    assert allowed.change_set.changes[0].after_content == original.replace('old', 'new')
    blocked = run(env, proposal(replacements([('Hidden ending.', 'Wrong')])), snapshots=(snapshot,))
    assert blocked.change_set is None and 'outside supplied file context' in blocked.notices[0]
    for operation in ('write', 'delete'):
        source = proposal(f'file: chapter.md\noperation: {operation}\n' + (block(CONTENT, 'Wrong') if operation == 'write' else ''))
        assert run(env, source, snapshots=(snapshot,)).change_set is None


@pytest.mark.parametrize("agent,metadata,snapshots", [
    ('critic', {}, None), ('general', {}, None),
    ('editor', {'finish_reason': 'length'}, None), ('editor', {}, ()),
])
def test_new_transport_cannot_bypass_readonly_truncation_or_context(environment, agent, metadata, snapshots):
    env = environment
    (env.root / 'chapter.md').write_bytes(b'Old')
    result = run(env, proposal(replacements([('Old', 'New')])), agent=agent, metadata=metadata, snapshots=snapshots)
    assert result.change_set is None
    assert (env.root / 'chapter.md').read_bytes() == b'Old'


def test_replacement_detects_stale_source_before_review_and_apply(environment):
    env = environment
    path = env.root / 'chapter.md'
    path.write_bytes(b'Old')
    source = proposal(replacements([('Old', 'New')]))
    result = run(env, source)
    path.write_bytes(b'External change')
    with pytest.raises(ChangeConflictError):
        env.tools.apply(result.change_set)
    snapshot = FileEditSnapshot(env.project.id, 'chapter.md', 'Old', (), True)
    blocked = run(env, source, snapshots=(snapshot,))
    assert blocked.change_set is None and 'changed since' in blocked.notices[0]
    assert path.read_bytes() == b'External change'


def test_large_whole_file_rewrite_does_not_require_json_escaping(environment):
    env = environment
    path = env.root / 'chapter.md'
    path.write_bytes(b'Complete original file.\n')
    content = ''.join(f'## Scene {i}\n"Dialogue," she said. Path: C:\\drafts. Literal: \\n.\n\n' for i in range(180))
    assert len(content) > 10_000
    result = run(env, proposal('file: chapter.md\noperation: write\n' + block(CONTENT, content)))
    assert result.outcome == 'pending_review', result.notices
    assert result.change_set.changes[0].after_content == content
    assert path.read_bytes() == b'Complete original file.\n'


def test_plain_text_cannot_escape_project_or_target_another_project(environment, tmp_path):
    env = environment
    (env.root / 'chapter.md').write_bytes(b'Original')
    unsafe = run(env, proposal('file: ../outside.md\noperation: write\n' + block(CONTENT, 'Wrong')))
    assert unsafe.change_set is None and not (env.root.parent / 'outside.md').exists()
    snapshot = FileEditSnapshot(env.project.id, 'chapter.md', 'Original', (), True)
    other = tmp_path / 'other-project'
    other.mkdir()
    (other / 'chapter.md').write_bytes(b'Original')
    env.projects.open_project(other)
    blocked = run(env, proposal(replacements([('Original', 'Wrong')])), snapshots=(snapshot,))
    assert blocked.change_set is None and 'project changed' in blocked.notices[0]
    assert (other / 'chapter.md').read_bytes() == b'Original'


def test_empty_replacement_can_remove_one_exact_passage(environment):
    env = environment
    (env.root / 'chapter.md').write_bytes(b'Keep. Remove this. Keep too.')
    result = run(env, proposal(replacements([(' Remove this.', '')])))
    assert result.change_set.changes[0].after_content == 'Keep. Keep too.'


def test_legacy_json_replacements_use_the_same_validation(environment):
    env = environment
    (env.root / 'chapter.md').write_bytes(b'Old')
    directive = {'summary': 'Revise', 'files': [{'path': 'chapter.md', 'operation': 'replace',
        'replacements': [{'old_text': 'Old', 'new_text': 'New'}]}]}
    source = '<sammyai_changes>' + json.dumps(directive) + '</sammyai_changes>'
    assert run(env, source).change_set.changes[0].after_content == 'New'


def test_failed_preview_cannot_return_an_actionable_change_set(environment, monkeypatch):
    env = environment
    (env.root / 'chapter.md').write_bytes(b'Old')
    def fail_preview(*_):
        raise ValueError('Preview failed')
    monkeypatch.setattr(env.tools, 'preview', fail_preview)
    result = run(env, proposal(replacements([('Old', 'New')])))
    assert result.outcome == 'proposal_rejected'
    assert result.change_set is None and result.change_preview is None
    assert (env.root / 'chapter.md').read_bytes() == b'Old'


@pytest.mark.parametrize("operation,body", [
    ('append', block(CONTENT, 'New ending.\n')),
    ('insert_before', block(ANCHOR, 'Old', CONTENT) + 'Before.\n' + END + '\n'),
    ('insert_after', block(ANCHOR, 'Old', CONTENT) + 'After.\n' + END + '\n'),
    ('write', block(CONTENT, 'New whole file "with quotes".\n')),
    ('delete', ''),
])
def test_existing_operations_use_raw_text_and_still_wait_for_approval(environment, operation, body):
    env = environment
    path = env.root / 'chapter.md'
    path.write_bytes(b'Old\n')
    result = run(env, proposal(f'file: chapter.md\noperation: {operation}\n' + body))
    assert result.outcome == 'pending_review', result.notices
    assert path.read_bytes() == b'Old\n'


def test_writer_revision_targets_original_source_in_plain_text(environment):
    env = environment
    (env.root / 'chapter.md').write_bytes(b'Original')
    prompts = []
    replies = iter([proposal(replacements([('Original', 'Draft')])), 'Improve the draft.', proposal(replacements([('Original', 'Final')]))])
    def complete(messages, prompt):
        prompts.append(prompt)
        return next(replies)
    result = run(env, '', agent='writer', complete=complete)
    assert result.model_calls == 3 and result.change_set.changes[0].after_content == 'Final'
    assert '<sammyai_edits>' in prompts[0] and '<sammyai_edits>' in prompts[2]
    assert 'original supplied' in prompts[2]


def test_prompt_examples_parse_and_have_distinct_purposes():
    import re
    examples = re.findall(r'<sammyai_edits>\n.*?</sammyai_edits>', TEXT_OUTPUT_PROMPT, re.DOTALL)
    parsed = [AgentWorkflowService._extract_change_directive(text)[1] for text in examples]
    assert [item['files'][0]['operation'] for item in parsed] == ['replace', 'write']
    assert len(parsed[0]['files'][0]['replacements']) == 2
