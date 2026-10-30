# Project-close and switching tab maintenance

**Status: COMPLETED — 2026-10-30**

Branch: `codex/close-project-tabs`, based on accepted v0.6.2-alpha and the merged
Writer file-operation fix (PR #32, baseline `9191556`). Implementation date:
2026-10-30. Package version remains `0.6.2a0`; no release number or tag is assigned.

On 2026-10-30 the maintainer confirmed that every original Close Project
acceptance check passed using **Car Show**. A further test opened **Shelf Life**
directly while Car Show was open and exposed retained outgoing file tabs. This
record includes the switching extension. The maintainer subsequently confirmed
that the fix works and pushed the changes. Both fixes are merged into `main`
through PR #33 (`aaa567f`). Acceptance records the maintainer's report; it does
not claim independent observation of every additional checklist step.

## Problem and resulting behavior

The Shelf Life screenshot showed project files still in the editor after Close
Project. The close handler cleared the project service and explorer without
closing document sessions, so those files remained editable and saveable.
Direct project switches had the same gap: the project service and explorer
changed, but outgoing document sessions stayed open beside the destination files.

Close Project now collects open files inside the active project's folder,
including subfolders. It checks every modified project tab using the existing
Save/Discard/Cancel handling before removing the tabs. Cancel or a failed save
keeps the project open. A Discard choice does not remove that buffer if a later
dirty-file prompt is canceled; any Save already completed remains on disk.

Open Project, Open Recent Project, New Project and Locate Moved Folder now use
the same departure checks and tab cleanup. The outgoing tabs are removed only
after the destination opens successfully. If it fails, the current project,
tabs and unsaved buffers remain, including a buffer previously marked Discard
during this attempt. Choosing the already-open project is a no-op, preserving
its dirty buffers, active tab and pending review. Canceling a project picker
does not dismiss pending reviews.

Pending reviews retain their explicit cancellation prompt and never apply on
close. Review cancellation happens before saving the tab list so a temporary,
unapplied file proposal is not recorded for restoration. Dismissing a review is
an explicit decision and is not undone if a later close prompt is canceled.

The file-tab list and active file are saved before closing or switching projects.
Workspace persistence is suppressed while outgoing tabs are removed so their
activation signals cannot overwrite the destination's saved tab list.
Reopening restores existing files and the active tab through the existing
workspace restoration path. Closing also cancels a running selection request
and clears a pinned selection whose source tab was closed.

Untitled drafts and files outside the project root stay open. If all tabs close,
the existing editor behavior creates one empty untitled document. Project files,
recent-project history and project metadata are retained.

## Scope

- No changes to project contents, database schema, dependencies or version metadata.
- This handles explicit Close Project and project switching. Tab sizing with
  chat open and the extra untitled tab when opening a project remain separate issues.
- Writing quality and Writer prompt behavior are outside this fix.

## Automated verification

Regression tests were added before the handler changed: **8 failed, 2 passed**,
demonstrating retained tabs, missing dirty-file prompts and layout carryover.
The initial implementation passed all 10 cases. A further case covers a running
selection request and its late response after close.

Switching regression cases were also added before changing the handlers:
**16 failed, 4 passed**. The shared implementation then passed all **31 close
and switch tests**, covering all four switching entry points, each project's
saved tabs/active file, dirty-file decisions, failure preservation, same-project
selection, pending reviews and late selection replies.

Coverage includes nested project files, similarly named external folders,
unsaved untitled/external buffers, background dirty tabs, Save and Discard,
Cancel at a later prompt, failed saves, pending review cancellation, unapplied
create proposals, restored file order/active file, RAG active-file cleanup,
editor status reset and pinned selection cleanup.

- Editor/project subsystem suite: **167 passed, 1 skipped** in 52.07 seconds.
- Full supported suite: **520 passed, 1 skipped, 16 deselected** in 91.44 seconds.
  External-service and model-loading tests are excluded by the supported-suite configuration.
- Offline wheel build and isolated installed core/review check passed, using a
  fresh virtual environment with network access blocked.
- Installed GUI regression check: **31 passed** in 10.29 seconds. The wheel was
  installed into a fresh temporary target; copied tests ran outside the checkout
  with imports verified against the installed application and network access
  blocked. This check reused the development environment's GUI/test dependencies;
  it does not establish manual acceptance of a complete desktop installation.
  A pytest import-rewrite warning occurred because the application was imported
  first to verify its installed path.
- `git diff --check` passed.
- The Windows symlink test is skipped because this account cannot create symlinks.
  Existing dependency deprecation warnings are unrelated to this fix.

```powershell
$env:TEMP = Join-Path (Get-Location) 'build'
$env:TMP = $env:TEMP
.\Scripts\python.exe -B -u -m pytest -q tests/editor_workspace tests/project_system --basetemp=.pytest_cache/switch-project-subsystems
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/switch-project-full
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/switch-project-wheel
.\Scripts\python.exe -B -u tests/change_sets/check_packaged_review.py build/switch-project-wheel/sammyai-0.6.2a0-py3-none-any.whl
```

## Accepted Close Project checks — Car Show, 2026-10-30

Use disposable copies for the Save/Discard checks. This checklist covers editor
mechanics and file preservation; no model-quality evaluation is needed.

- [x] Open several Car Show files, including one in a subfolder. Close Project.
  All project file tabs disappear, the explorer closes, and the window title no
  longer includes the project. If no other tabs were open, one empty untitled
  document remains with zero words.
- [x] Reopen Car Show. Its previous file tabs and active file are restored.
- [x] Modify a project file, activate another tab, then Close Project. Choose
  Save and verify the edit on reopening; repeat with Discard and verify the
  original saved content remains.
- [x] Modify two project files. Choose Discard for the first and Cancel for the
  second. The project and all its file tabs remain open, including both edits.
- [x] Keep an unsaved untitled draft and an outside-project file open. Close
  Project. Both remain open with their contents intact.
- [x] Close Car Show, then open a different project. Car Show's files do not
  appear among the new project's tabs.
- [x] With a pending AI review, Cancel Close Project and verify the review stays.
  Close again and explicitly discard the review; no proposal is applied and the
  project tabs close.

These results record the maintainer's report; the application or saved chats were
not independently inspected for this acceptance run.

## Direct switching regression checklist

Retained for future regression runs following maintainer acceptance.

- [ ] With Car Show files open, open Shelf Life directly through Open Project.
  Car Show's file tabs disappear and Shelf Life's saved files/active tab restore.
  Switch back through Open Recent Project and verify Car Show's tabs restore.
- [ ] Modify a Car Show file and open Shelf Life. Cancel keeps Car Show and the
  edit open. Repeat with Save and Discard and verify the respective disk contents
  when returning to Car Show.
- [ ] Create a new project while Car Show is open. Its project tabs close;
  unrelated files and untitled drafts stay open.
- [ ] Select the already-open project through Open Project or Open Recent.
  Its active tab, unsaved edits and any pending review remain unchanged.
- [ ] With a pending review in Car Show, try opening Shelf Life. Cancel leaves
  the project/review open; explicit Discard switches without applying the proposal.

The accepted fix is merged. Release tagging remains a maintainer action.
