"""Envelope validation must not hide errors in the JSON body."""
import json

import pytest

from sammyai_core.agent_workflows import AgentWorkflowService


@pytest.mark.parametrize("body", [
    # Synthetic reproduction of the October 7 malformed ending. No story data.
    '{"files":[\n  {"path":"chapter.md","operation":"write","content":"New text."' + r'\n]}"\n',
    '{"files":[]',
    '{"files":[]} extra',
    '```json\n{"files":[]}\n```',
    '',
])
def test_complete_envelope_reports_json_error_at_original_location(body):
    with pytest.raises(json.JSONDecodeError) as expected:
        json.loads(body)
    with pytest.raises(json.JSONDecodeError) as actual:
        AgentWorkflowService._extract_change_directive(
            '<sammyai_changes>' + body + '</sammyai_changes>'
        )
    assert (actual.value.msg, actual.value.pos, actual.value.lineno, actual.value.colno) == (
        expected.value.msg, expected.value.pos, expected.value.lineno, expected.value.colno
    )


@pytest.mark.parametrize("source", [
    '<sammyai_changes>{"files":[]}',
    '{"files":[]}</sammyai_changes>',
    '<SAMMYAI_CHANGES>{"files":[]}</SAMMYAI_CHANGES>',
    '<sammyai_changes>{"files":[]}</sammyai_changes><sammyai_changes>',
])
def test_incomplete_or_malformed_tags_remain_envelope_errors(source):
    with pytest.raises(ValueError, match="change directive envelope"):
        AgentWorkflowService._extract_change_directive(source)


def test_multiple_directives_rejected():
    source = '<sammyai_changes>{"files":[]}</sammyai_changes>' * 2
    with pytest.raises(ValueError, match="multiple change directives"):
        AgentWorkflowService._extract_change_directive(source)


@pytest.mark.parametrize("body", ['[]', '{"files":{}}', '{"summary":"No files"}'])
def test_valid_json_with_wrong_shape_is_schema_error(body):
    with pytest.raises(ValueError, match="object with a files list"):
        AgentWorkflowService._extract_change_directive(
            '<sammyai_changes>' + body + '</sammyai_changes>'
        )


def test_valid_multiline_content_round_trips_without_repair():
    directive = {"files": [{"path": "chapter.md", "operation": "write",
                            "content": 'First line.\n"Quoted text" and a backslash: \\'}]}
    source = 'Proposed edit.\n<sammyai_changes>\n' + json.dumps(directive) + '\n</sammyai_changes>\nPlease review.'
    visible, parsed = AgentWorkflowService._extract_change_directive(source)
    assert parsed == directive
    assert visible == 'Proposed edit.\n\nPlease review.'


def recover(source):
    with pytest.raises(json.JSONDecodeError) as error:
        AgentWorkflowService._extract_change_directive(source)
    return AgentWorkflowService._recover_missing_file_brace(source, error.value)


@pytest.mark.parametrize("file_count", [1, 2])
def test_missing_final_file_brace_recovery_inserts_only_one_character(file_count):
    directive = {"summary": "Update files", "files": [
        {"path": f"chapter-{i}.md", "operation": "write",
         "content": 'Unicode: café.\nBrackets: } ] } and "quotes". Backslash: \\'}
        for i in range(file_count)
    ]}
    body = json.dumps(directive, ensure_ascii=False)
    source = 'Before\n<sammyai_changes>\n' + body[:-3] + '\n]}\n</sammyai_changes>\nAfter'
    repaired = recover(source)
    position = source.rfind(']}')
    assert repaired == source[:position] + '}' + source[position:]
    visible, parsed = AgentWorkflowService._extract_change_directive(repaired)
    assert parsed == directive
    assert visible == 'Before\n\nAfter'


@pytest.mark.parametrize("body", [
    # Ambiguous or larger damage must remain a rejection.
    '{"files":[{"path":"c.md","operation":"write","content":"Text"' + r'\n]}"\n',
    '{"files":[{"path":"c.md","operation":"write","content":"Text}]}',
    '{"files":[{"path":"c.md","operation":"write","content":"Text"',
    '{"files":[{"path":"c.md","operation":"write","content":"Text",]}',
    '{"files":[{"path":"c.md","operation":"write","content":"a" "b"}]}',
    '{"files":[{"path":"c.md","operation":"write","content":"Text"],"summary":"Later"}',
    '{"files":[{"path":"c.md","operation":"write","content":"Text","extra":{]}',
    '{"files":[],"other":[{"path":"c.md","operation":"write","content":"Text"]}',
    '{"files":[{"content":"Missing path and operation"]}',
    '{"files":[{"path":"c.md","operation":"write","content":"Text"]} trailing',
])
def test_missing_brace_recovery_does_not_guess_at_other_damage(body):
    assert recover('<sammyai_changes>' + body + '</sammyai_changes>') is None
