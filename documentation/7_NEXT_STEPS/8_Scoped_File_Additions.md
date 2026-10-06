# Scoped file additions — 2026-10-06

Branch: `codex/scoped-file-additions`, created from accepted `main` at `109bd18`.
Maintainer desktop testing and merge are pending. Package version remains
`0.6.0a0`; this extends the existing review workflow before selection actions.

## Problem and supported behavior

Previously, adding one scene required the model to receive and regenerate the
entire destination file. A valid reference exceeding the 4,000 estimated-token
context allowance was truncated, then rejected as unauthorized.

Brainstormer, Writer, and Editor now support:

- **Append:** generate only new material at the captured end of a referenced file.
- **Insert before / after:** generate only new material adjacent to an exact,
  unique, complete source line that was supplied in the request context.
- **Existing whole-file operations:** create, replace, and delete remain available.
  Replacement and deletion require complete context for existing files.

Example requests:

- `Add Scene 20's breakdown to @scene_breakdown.md, keeping the earlier scenes.`
- `Insert an interlude before the Scene 10 heading in @scene_breakdown.md.`

For insertion after a whole scene, target the next scene's heading or append at
EOF. An `insert_after` anchor identifies a line, not an inferred section boundary.
Missing, repeated, or unseen anchors produce a rejection notice asking for a more
specific target. The addition's top-level headings and recognizable numbered
scenes/chapters/acts are checked for obvious duplicates within the same parent
section, including omitted source. Scene numbering may restart under a new act.
This cannot detect all semantic duplication; inline review remains necessary.

Additions preserve the existing source text. New text adopts its newline
convention, with a line break supplied where necessary to avoid joining two
lines. Intentional paragraph spacing belongs in the proposed addition.

## Context and authorization

For files that fit, the full source is supplied as before. Larger files receive
a bounded partial view containing the ending, query-relevant excerpts, headings,
and the beginning when space permits. Heading bodies or portions of long lines
may be omitted. The context and chat notices identify partial views explicitly.
Very small budgets that cannot carry a useful context contract grant no edit
authority.

`FileEditSnapshot` holds the exact UTF-8 source, project identity, relative path,
visible source ranges, and completeness flag. Its source hash is derived locally.
Only rendered source ranges authorize insertion anchors; append requires the
ending or complete context. The full snapshot stays local, outside model messages.
Snapshots are transient and do not require a database or saved-data migration.

`PreparedChatRequest` carries messages and their associated context together.
The main window passes that request's immutable snapshots to the workflow rather
than consulting mutable `ChatManager.last_context_result`. The compatibility
message-list API still updates that diagnostic field, but it no longer supplies
authorization to the main chat path.

`SafeFileTools` checks each request's expected source hash while preparing the
change set, catching edits during model generation. Existing review and apply
checks catch later changes. Project identity, path confinement, clean-buffer
requirements, atomic writes, rollback, and undo/redo remain in force. No model
output can choose arbitrary character offsets or replace text through an addition.

## Agent contract

An addition uses the existing directive envelope:

```json
{
  "summary": "Add Scene 20",
  "files": [
    {
      "path": "scene_breakdown.md",
      "operation": "append",
      "content": "\n\n## Scene 20\nNew breakdown.\n"
    }
  ]
}
```

Insertion uses `operation: "insert_before"` or `"insert_after"` and adds an
`anchor` field containing the exact source line, such as `## Scene 10`.
Only new text belongs in `content`. Unknown addition fields, empty additions,
invalid operations, unreferenced targets, or ambiguous anchors are rejected.
One operation per file per proposal remains the existing change-set constraint.

The Writer's draft, evaluation, and revision stages share the same file evidence.
Revision instructions retain the addition's scope instead of asking for a
complete replacement file. Assistant and Critic remain read-only.

## Accommodating future models and workflows

The limits serve separate purposes:

| Policy | Default | Controls |
| --- | --- | --- |
| `ProjectContextEngine.max_context_tokens` | 4,000 estimated tokens | Supplementary file, memory, attachment, and retrieval context |
| `FileContextPolicy` | 2,400-character excerpts, up to 80 outline entries and 3 query windows | Which source portions are rendered when full content does not fit |
| `AdditionPolicy.max_added_tokens` | 4,000 estimated tokens | Total new append/insert text across a proposal, excluding existing text |
| `AdditionPolicy.max_files` | 20 | Maximum files in one proposal |
| Local snapshot / file-tool resource limits | 10 MiB per file | Local memory/I/O bounds, independent of writing quality |

These are application service policies, not new UI settings or claims about a
provider's actual context window. Token estimates use roughly four characters
per token; conversation history and intermediate Writer drafts are outside the
supplementary context allowance.

Construct the context engine with a different `max_context_tokens` or
`file_context_policy` when integrating model capabilities. Construct
`AgentWorkflowService` with an `addition_policy`, or pass one to `run()` for a
specific request. Increasing a budget never relaxes target, source-hash, project,
or review checks.

Future planners, tool loops, and additional evaluation stages should carry the
request's evidence explicitly and obtain fresh evidence when the source changes.
Future section replacement can build on the existing `TextEdit` primitives with
separate complete-section evidence and authorization. This release adds no
selection-action UI, automatic rebasing, autonomous writes, or model-specific
capability guessing.

## Validation

- Baseline context/agent/file-tool/review subsystem run: **55 passed**.
- New automated coverage includes oversized-file append and middle insertion,
  source-byte and newline preservation, duplicate sections, ambiguous/unseen
  anchors, unreferenced files, project switches, malformed directives, aggregate
  addition budgets, configurable policies, and stale sources in all Writer stages.
- Real Qt integration tests run context assembly and the agent workflow through
  chat send, inline review, explicit application, undo, and redo.
- Final `Scripts/python.exe -m pytest -q`: **279 passed, 1 skipped, 16 deselected**
  in 31.15 seconds. The skip is the existing Windows symlink-permission test;
  external-service and model-loading tests are excluded by repository defaults.
  Two existing dependency deprecation warnings remain.
- `Scripts/python.exe -m pip wheel . --no-deps --no-build-isolation -w dist/scoped-file-additions`:
  **passed**, producing `sammyai-0.6.0a0-py3-none-any.whl`.
- `Scripts/python.exe tests/change_sets/check_packaged_review.py dist/scoped-file-additions/sammyai-0.6.0a0-py3-none-any.whl`:
  **passed** in a fresh virtual environment with network connections blocked.
  Verified packaged large-file append/review, exact CRLF preservation, safe apply,
  undo/redo, chat persistence, review assets, and absence of retired DBE code.
- `git diff --check`: **passed**.

## Desktop acceptance checklist

- [ ] Open a test project with a breakdown larger than the context allowance.
  Ask Editor to add a new scene using its exact `@file` reference. Confirm that
  partial context is reported and the proposal shows an addition for review.
- [ ] Accept and apply. Confirm earlier scenes remain intact. Verify undo/redo.
  Repeat with Writer to exercise its evaluation and revision stages.
- [ ] Ask to insert an interlude before a unique middle-scene heading. Confirm
  the proposed location and preservation of subsequent scenes.
- [ ] Try an existing scene number within the same act and an ambiguous heading.
  Confirm the app explains the rejection and leaves the file unchanged. Check
  that scene numbering can restart under a different Markdown act heading.
- [ ] Edit/save the source while a model request is running. Confirm the stale
  proposal is rejected; repeat with an external edit after review opens.
- [ ] Verify small-file rewrites and manual comparisons still work. Try an
  oversized whole-file rewrite and confirm the message explains the context
  limit rather than falsely claiming that no file reference was supplied.

No live provider/model call is required by the automated tests. Test with your
configured models before merging through the maintainer workflow.
