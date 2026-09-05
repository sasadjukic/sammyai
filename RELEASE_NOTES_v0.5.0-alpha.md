# SammyAI v0.5.0-alpha

## Multi-file editor workspace

This release introduces a tabbed document workspace for Markdown and plain-text files. Open documents retain independent contents, cursor and scroll positions, selections, and undo history. Reopening the same normalized path focuses its existing tab, while new untitled documents receive unique names.

Tabs show file icons, full filenames, close controls, and unsaved-change markers. The active tab now drives Save, Save As, search and replace, edit actions, word count, line and column status, manual indexing, legacy DBE context, and the RAG active-file boost.

## Document safety

- Closing a dirty tab or quitting with dirty tabs prompts to save, discard, or cancel.
- Rename and delete operations account for matching open tabs.
- Dirty background tabs block conflicting reviewed change sets.
- Clean background tabs refresh after approved external file changes.
- Legacy asynchronous DBE results retain the originating document ID and cannot be applied to a different active tab.

## Project continuity

Open project-relative file paths and the active file are stored in project settings and restored on the next project open. Missing, moved, unsupported, and out-of-project paths are ignored safely.

## Validation

The automated non-external, non-model suite passes with 137 tests. Final packaged-Windows manual acceptance remains required before tagging the release.
