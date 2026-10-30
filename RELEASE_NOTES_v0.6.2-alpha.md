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
empty-file and populated-file appends through review and application. The fix
was merged into `main` in PR #32. Tagging remains a maintainer action; the package
version remains `0.6.2a0` until a maintenance release is assigned.

- Writer carries explicit file destinations and operations through its three
  stages. Drafts are explicitly unsaved, and an append must return the complete
  revised new material, including when the destination is empty.
- Final proposals that change the requested operation/target or omit the file
  change fail visibly. The saved assistant reply states that no files changed;
  diagnostics retain the reason and existing opt-in content capture behavior.
- Existing source validation, inline review, apply and undo remain required.
  There are no new dependencies, migrations, automatic retries or model calls.

See the [maintenance acceptance record](documentation/7_NEXT_STEPS/11_Writer_File_Operations.md).

## Unreleased maintenance — Close and switch project file tabs

Implemented on `codex/close-project-tabs` on 2026-10-30. The maintainer passed
the Close Project checklist using Car Show. Direct project switching was then
added after testing exposed retained Car Show tabs when opening Shelf Life;
Windows acceptance of this extension is pending. Package version remains `0.6.2a0`.

- Close Project removes all open file tabs inside the project's folder,
  including nested files. Untitled drafts and standalone files stay open.
- Open Project, Open Recent Project, New Project and Locate Moved Folder share
  the outgoing-project tab cleanup. Each project's saved workspace is retained.
  Failed destination opens preserve the current project and buffers; selecting
  the already-open project leaves its current work alone.
- Modified project files prompt for Save, Discard, or Cancel before tabs close.
  Cancel or a failed save keeps the project open. Pending reviews retain their
  explicit discard/cancel prompt.
- Reopening restores the project's saved file tabs and active file. Closing
  clears references to closed files, including a pinned selection, and cancels a running
  selection request so a late response cannot open a review.

No database migration or new dependency is required. See the
[project guide](documentation/3_USER_GUIDE/7_Projects.md#close-a-project) and
[maintenance acceptance checklist](documentation/7_NEXT_STEPS/12_Project_Close_Tabs.md).
