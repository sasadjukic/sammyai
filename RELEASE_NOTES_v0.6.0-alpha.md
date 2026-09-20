# v0.6.0-alpha — Inline diff review

Implementation branch: `codex/inline-diff-review`. Version metadata: `0.6.0a0`.
Interactive Windows acceptance and maintainer merge are pending. No tag has been created.

Validation: 210 supported automated tests pass (16 model/external tests excluded).
The wheel builds and passes an isolated offline core/asset installation check.

## Changes

- AI proposals and manual comparisons open in the affected editor tabs.
- Stable structured hunks support Accept/Reject Hunk, Accept/Reject All per file,
  Previous/Next, explicit application, and proposal-wide cancellation.
- Context, additions, deletions, current hunk, and decision states use theme tokens
  and text labels. Find and Copy operate on the read-only review surface.
- Multi-file decisions synthesize one change set using original snapshots and
  hashes, preserving SafeFileTools validation, atomic writes, rollback, and history.
- Clean project DBE proposals use file-tool history; unsaved/out-of-project drafts
  retain one-step editor undo and an explicit Save afterward.
- Buffer revisions, file contents, project identity, and originating document/chat
  identity protect against stale and wrong-target application.
- Saves, replacements, file operations, tab closure, and project switching respect
  pending reviews. Creating/deleting empty files requires explicit review too.
- Unified patch import/export now preserves final newlines and no-newline markers,
  handles zero-context insertions, and validates hunk line counts.
- Large repetitive passages use bounded matching heuristics to avoid long review
  startup stalls; those passages may appear as a larger review hunk.

## Compatibility and scope

No database or saved-document migration is needed. Existing text, conversation,
and project data remain compatible. Review state is intentionally transient;
unapplied proposals never write diff markers into source documents.

File creation/deletion is indivisible. Existing file updates support partial
acceptance. Persistent review recovery, editing proposals inside the review,
automatic conflict rebasing, and later roadmap features are outside this release.

`SAMMYAI_POPUP_REVIEW=1` retains the previous popup as a documented temporary
fallback. It is not used by default.

See the [acceptance record](documentation/7_NEXT_STEPS/5_Inline_Diff_Review_Acceptance.md)
and [user guide](documentation/3_USER_GUIDE/5_Diff_Edits_Menu_Options.md).
