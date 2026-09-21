# Inline diff review acceptance — 2026-09-20

Branch: `codex/inline-diff-review`. Target version: `0.6.0a0`.
The maintainer confirmed that testing passed and that inline diff review was
merged into `main`. Acceptance recorded on 2026-09-20. The checklist below is
retained for repeat testing; individual checklist results were not supplied.

## Scope

Inline read-only review in each affected tab, per-hunk decisions for updates,
whole-file creation/deletion decisions, explicit multi-file apply, shared DBE
and agent routing, conflict protection, cancellation, existing undo/redo, theme
tokens, and a temporary popup fallback. No review persistence or automatic rebasing.

## Automated and visual validation

- Baseline editing/workspace tests: 48 passed before behavior changes.
- Added buffer characterization tests: 2 passed before behavior changes.
- Core review tests cover exact LF/CRLF/EOF/Unicode content, stable IDs, mixed
  decisions, line-count changes, immutable snapshots, and empty-file operations.
- UI/service tests cover tab/chat identity, dirty background tabs, buffer and disk
  conflicts, project changes, rollback, cancellation, guarded file operations,
  search/decorations, draft undo, and project change-set undo/redo.
- The actual Windows Qt widgets were rendered offscreen with Segoe UI/Consolas
  and visually inspected. [Screenshot](../3_USER_GUIDE/pictures/Inline_Review.png).
- Final full supported suite: `.\Scripts\python.exe -m pytest -q` — **210 passed,
  16 deselected**, 2 existing dependency deprecation warnings, 44.77 seconds on
  Windows / Python 3.14.6. Model/external tests were not run.
- The focused inline UI and legacy diff compatibility run passed 59 tests. Patch
  round trips cover LF/CRLF, final newline changes, standard no-newline markers,
  empty documents, and zero-context insertions.
- `.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation -w dist/inline-review`
  built `sammyai-0.6.0a0-py3-none-any.whl` with the new model/controller/widgets and theme.
- `.\Scripts\python.exe tests\change_sets\check_packaged_review.py dist\inline-review\sammyai-0.6.0a0-py3-none-any.whl`
  passed in a fresh temporary virtual environment using only the local wheel,
  `--no-index --no-deps`, isolated Python imports, and blocked network connections.
  It verifies review synthesis, CRLF, safe apply/undo/redo, and installed theme assets.
  This is an isolated core/package check, not a full clean GUI installation.
- A 10,000-paragraph repetitive-text probe improved from 36.754 seconds to 0.005
  seconds for hunk construction. Large repeated regions may become a single hunk;
  acceptance/rejection still reproduces the exact proposed/original content.
- Narrow review with chat open was also rendered and visually inspected using
  `--with-chat --width 1000 --height 700`. Qt honors the combined panels' minimum
  width; panels can be collapsed to leave more room for the editor.
- `git diff --check` passed before handoff. The maintainer subsequently merged the branch.

## Repeatable interactive demo

From the repository environment, run:

```powershell
.\Scripts\python.exe tests\editor_workspace\preview_inline_review.py
```

This creates a temporary project, settings, and sample chapters without a model
request. It starts with one accepted, one rejected, and one pending hunk. The
temporary project is removed when the demo exits.

To reproduce the documentation screenshot without opening a desktop window:

```powershell
.\Scripts\python.exe tests\editor_workspace\preview_inline_review.py --capture documentation\3_USER_GUIDE\pictures\Inline_Review.png
```

## Windows interactive acceptance checklist

- [ ] Start the application with ten tabs and a long chapter. Request an Editor
  proposal. Confirm readable context, additions/deletions, hunk states and controls.
- [ ] Accept/reject nonadjacent hunks, including a change that inserts lines before
  another. Reverse a decision, navigate with keyboard/mouse, then apply.
- [ ] Review multiple files, including create/delete and an empty file. Confirm
  Apply stays disabled until all files have decisions; verify file history undo/redo.
- [ ] Switch tabs and conversations while an AI response is running. Confirm its
  review remains attached to its original target and origin metadata.
- [ ] Try an unsaved background tab, an external edit/delete, and a second proposal
  for a reviewed tab. Confirm there is no overwrite and conflict recovery is clear.
- [ ] Try Save, Save As, Replace, rename/delete, tab close, quit, and project switch
  while reviewing. Cancel prompts should preserve the pending review.
- [ ] Try DBE in a clean project file, an unsaved draft, and an untitled tab. Check
  the Apply destination label, project history or draft Undo/Redo as appropriate.
- [ ] Exercise Compare with File, Clipboard, and Patch. Find and Copy inside review;
  return to editing and confirm spelling/search still work without diff markers.
- [ ] Cancel and restart. No proposal text or hunk markers should have been saved.
- [ ] Check a narrow editor with chat open, high DPI, keyboard focus, long wrapped
  lines, Unicode, and CRLF/trailing-newline changes on the actual Windows desktop.
- [ ] Install/run the complete wheel with provisioned dependencies in a clean
  Windows environment. Repeat a real Editor request and review/apply/history flow.
- [ ] Optionally verify `SAMMYAI_POPUP_REVIEW=1`, then remove the variable. Record
  acceptance, mark Release 4 completed, and merge only through the maintainer workflow.
