# v0.6.0-alpha — Inline diff review

Inline diff review was tested and merged into `main` by the maintainer.
Version metadata: `0.6.0a0`.

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
- Clean project comparisons use file-tool history; unsaved/out-of-project drafts
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

## Accepted follow-up — Manual indexing retirement

- Removed the Legacy Manual Indexing menu and its indexing/management handlers.
- Project Context now offers **Import Reference File...**, which preserves the
  external source and copies it into the project's `References` folder for normal
  automatic synchronization. Name collisions never overwrite existing files.
- **Indexed Files...** provides read-only inspection of project and unassigned
  legacy entries, including source paths and chunk counts.
- Existing index entries are preserved. No automatic migration or purge occurs.
  The global reset confirmation now explains its effect on legacy entries.
- Legacy DBE remained available at this stage.

The maintainer confirmed manual testing and merged `codex/retire-manual-indexing`
into `main`; acceptance recorded on 2026-09-21.
See the [validation and acceptance guide](documentation/7_NEXT_STEPS/6_Manual_Indexing_Retirement.md).

## Merged follow-up — Legacy DBE retirement

- Removed **Enable Legacy DBE Mode** and the separate DBE request, context, prompt,
  and response-splicing code. Advanced now contains Persistent Memory and Project Context.
- Chat requests use the selected agent. For AI file edits, save the file in the
  project, choose Editor, and reference the file explicitly in the request.
- Inline review, manual file/clipboard/patch comparisons, safe application,
  conflict protection, and undo/redo remain available.
- Existing documents, projects, and conversations need no migration. Selecting
  editor text no longer supplies implicit context through a separate DBE mode;
  story-focused selection actions remain on the roadmap.

The maintainer reported merging `codex/retire-legacy-dbe` into `main`;
merge recorded on 2026-10-06.
See the [validation and acceptance guide](documentation/7_NEXT_STEPS/7_Legacy_DBE_Retirement.md).

## Unreleased follow-up — Scoped file additions

- Brainstormer, Writer, and Editor can append or insert new material into an
  explicitly referenced `.md`/`.txt` file without generating its entire contents.
- Large-file context supplies headings, query-relevant excerpts, and the ending.
  Insertion requires a unique complete source line supplied in that context.
- Immutable request snapshots preserve unchanged text and catch source changes
  during generation, including all Writer stages. Normal review/apply conflict
  checks, atomic writes, and undo/redo remain in force.
- Context selection and new-text limits are independent policies, with optional
  per-run addition limits for future model/workflow integrations. Default additions
  share a 4,000 estimated-token allowance for new text across the proposal.
- Whole-file replacement/deletion still requires complete context. Partial-file
  replacement and selection actions remain future work. Existing data needs no migration.

Branch: `codex/scoped-file-additions`; maintainer testing and merge are pending.
See the [implementation and acceptance guide](documentation/7_NEXT_STEPS/8_Scoped_File_Additions.md).
