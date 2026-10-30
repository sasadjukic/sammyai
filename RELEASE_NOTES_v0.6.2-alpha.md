# v0.6.2-alpha — Story-focused selection actions

Implemented on `codex/story-selection-actions` and merged into `main`. Python
package version: `0.6.2a0`. Maintainer Windows acceptance was confirmed on
2026-10-28. Release tagging remains pending.

- Editor right-click actions: Rewrite Selection, Tighten Prose, Expand Description,
  Improve Dialogue, Change Tone, Critique Selection, and Continue From Here.
- Automatic filename/line-range references keep the selected prose out of the
  composer. Add Selection to Chat pins a reference across tab switches; × removes it.
- A message with a reference uses the Selection workflow and current model.
  Questions produce feedback; requested edits produce an inline review.
- Context menus support separate contributions for each application surface,
  preserving Qt clipboard actions and spelling suggestions.
- Immutable document, path, range, revision, and disk snapshots protect asynchronous
  results. Changed/closed sources, malformed or truncated results and provider
  errors cannot apply an edit. Cancel ignores late responses.
- Selection requests link model calls, validation, conversation metadata and
  review outcomes to persistent diagnostics. Existing safe file apply and draft
  undo behavior remain in use.

No database migration or new dependency is required. See the
[user guide](documentation/3_USER_GUIDE/11_Selection_Actions.md) for context limits
and the [acceptance record](documentation/7_NEXT_STEPS/10_Selection_Actions.md)
for verification and the manual checklist.

## Unreleased maintenance — Writer file operations

Implemented and accepted by the maintainer on 2026-10-29 on
`codex/writer-file-operation`. Car Show testing covered workflow mechanics and
execution; writing quality was not evaluated. The saved traces confirm both
empty-file and populated-file appends through review and application. GitHub
push/merge and tagging remain maintainer actions; the package version remains
`0.6.2a0` until a maintenance release is assigned.

- Writer carries explicit file destinations and operations through its three
  stages. Drafts are explicitly unsaved, and an append must return the complete
  revised new material, including when the destination is empty.
- Final proposals that change the requested operation/target or omit the file
  change fail visibly. The saved assistant reply states that no files changed;
  diagnostics retain the reason and existing opt-in content capture behavior.
- Existing source validation, inline review, apply and undo remain required.
  There are no new dependencies, migrations, automatic retries or model calls.

See the [maintenance acceptance record](documentation/7_NEXT_STEPS/11_Writer_File_Operations.md).
