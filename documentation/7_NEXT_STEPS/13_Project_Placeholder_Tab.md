# Automatic Untitled tab maintenance

**Status: IMPLEMENTED — awaiting maintainer Windows acceptance**

Branch: `codex/project-placeholder-tab`, based on accepted v0.6.2-alpha and the
merged project-close/switching fix (PR #33, baseline `aaa567f`). Implementation
date: 2026-10-30. Package version remains `0.6.2a0`; no release number is assigned.

## Problem and resulting behavior

The Shelf Life screenshot showed an extra Untitled tab alongside restored
project files. The workspace creates a blank editor before project restoration
and whenever its last document closes; that automatic tab was never replaced
when files opened.

The workspace now tracks which tab is an automatic placeholder. Once a file
opens successfully, an untouched, empty, unnamed placeholder without a pending
review is closed. This applies to startup restoration, Open Project, Open Recent,
direct switching, and opening a file manually. Saved tab order and active-file
restoration continue to use the existing project workspace settings.

New File creates an intentional draft, which is never marked as a placeholder.
An automatic blank becomes an ordinary draft on its first content change or
when it is assigned a filename. This distinction persists for the session even
if undo returns the content to empty, retaining its undo/redo history. Whitespace,
named empty files, modified buffers and pending reviews are also preserved.

A project with no restorable files retains a blank editor. Missing or unreadable
files do not cause the placeholder to close. Closing the final tab still creates
one blank editor, which can be replaced by the next successfully opened file.

This fix changes only in-memory workspace behavior. It does not alter project
documents, saved chats, database schemas, dependencies or package versions.
The remaining tab-width issue with agent chat open is outside this change.

## Verification

Characterization tests ran before the workspace change: **9 failed, 10 passed**.
Failures reproduced the extra tab on startup, project opening, switching, after
Close Project, and after closing the last document. Existing protections for
drafts, empty projects and pending reviews were characterized alongside them.

Coverage includes preserving explicitly created empty drafts, whitespace-only
drafts, drafts cleared back to empty, redo after undo to empty, clean nonempty
buffers, empty named files and active reviews. The startup restoration test now
checks the exact tab count as well as restored paths and active file.

- Editor/project subsystem suite: **185 passed, 1 skipped** in 51.94 seconds.
- Full supported suite: **538 passed, 1 skipped, 16 deselected** in 95.93 seconds.
  The skip is unavailable Windows symlink creation; external-service/model tests
  remain excluded. Two existing dependency deprecation warnings remain.
- Offline wheel build and isolated installed core/review check passed in a fresh
  virtual environment with network access blocked.
- Installed GUI regression check: **19 passed** in 4.49 seconds. The wheel was
  installed into a fresh temporary target; copied tests ran outside the checkout
  with application imports verified against that target and network blocked.
  GUI/test dependencies were reused from the development environment. A pytest
  import-rewrite warning resulted from importing the application before pytest
  to verify its installed location. This is not manual desktop acceptance.
- `git diff --check` passed.

```powershell
$env:TEMP = Join-Path (Get-Location) 'build'
$env:TMP = $env:TEMP
.\Scripts\python.exe -B -u -m pytest -q tests/editor_workspace tests/project_system --basetemp=.pytest_cache/placeholder-subsystems
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/placeholder-full
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/placeholder-wheel
.\Scripts\python.exe -B -u tests/change_sets/check_packaged_review.py build/placeholder-wheel/sammyai-0.6.2a0-py3-none-any.whl
```

## Maintainer Windows acceptance

- [ ] Open Shelf Life with a saved set of file tabs. Only those files restore,
  with the correct active file and no automatic Untitled tab. Restart SammyAI
  with the project active and verify the same result.
- [ ] Close and reopen the project, then switch directly between Car Show and
  Shelf Life. No extra automatic blank tab appears beside restored files.
- [ ] Type in the initial blank, undo back to empty, then open a project. The
  draft stays open and Redo still restores its text.
- [ ] Use New File to create an empty draft, then open a project. That explicitly
  created draft stays open. Repeat with a draft containing text or whitespace.
- [ ] Open a new/empty project. A blank editor remains available. Open its first
  file and verify that the untouched automatic blank disappears.
- [ ] Close the last tab. One blank editor appears; opening a file replaces it.

Record maintainer acceptance before marking this fix COMPLETED. Commit, push,
merge and tagging remain maintainer actions.
