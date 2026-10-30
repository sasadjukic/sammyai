# Editor tab-overflow maintenance

**Status: IMPLEMENTED — awaiting maintainer Windows acceptance**

Branch: `codex/editor-tab-overflow`, based on accepted v0.6.2-alpha and the merged
automatic Untitled tab fix (PR #34, baseline `dbbb4bc`). Implementation date:
2026-10-30. Package version remains `0.6.2a0`; no release number is assigned.

## Problem and resulting behavior

The Shelf Life screenshot showed grey shapes at the right of the tab row when
agent chat was open. A themed reproduction confirmed these were the native tab
scroll buttons. They were 16 pixels wide while inheriting toolbar padding of
10 pixels on each side, obscuring their arrows. Files and tab identities were intact.

The native horizontal tab row now has dedicated 32-pixel scroll controls with
legible chevrons. Tab labels have bounded widths and middle ellipsis for long
names. Qt retains scrolling, active-tab visibility, drag reordering and keyboard
navigation. Arrows move the row without changing the active document or buffer.

A down-chevron Open tabs menu lists every document in tab order with its full
filename. The active document is checked and bold; unsaved dots and pending
review labels come from the same labels as the tab row. Full paths appear in
tooltips. Menu actions capture stable document IDs, so reordering cannot retarget
an action and an action for a closed document cannot reopen it.

Breadcrumb labels can shrink horizontally instead of setting the editor's
minimum width from the entire path. Their existing full-path tooltips and text
selection remain available. Document contents, project persistence, close/save
prompts, review decisions, chat behavior and database schemas are unchanged.

## Verification

Characterization tests first produced **5 failed, 2 passed**. They exposed the
undersized buttons, unbounded long labels and missing menu, while confirming
native scrolling and resize behavior. All seven tab tests now pass, including
full path tooltips, dirty-state visibility, reordering, closing, keyboard
navigation and hiding arrows when tabs fit.

- Editor/project subsystem suite: **192 passed, 1 skipped** in 58.82 seconds.
  Final arrow artwork and active-menu emphasis are also covered by the full run.
- Full supported suite: **545 passed, 1 skipped, 16 deselected** in 99.80 seconds.
  The skip is unavailable Windows symlink creation; external-service/model tests
  remain excluded. Two existing dependency deprecation warnings remain.
- Offline wheel build and isolated core/review package check passed.
- Installed tab-control check: **7 passed** in 1.06 seconds. A fresh virtual
  environment loaded the application, stylesheet and all three SVGs from the
  installed wheel, with network access blocked. Qt/pytest dependencies were
  reused from the development environment. The check has its own pytest root
  and configuration to avoid collecting neighboring temporary build folders.
- `git diff --check` passed.
- Offscreen screenshots were visually inspected at 1440×850 with and without
  chat, and 1200×850 with chat at `QT_SCALE_FACTOR=1.5`. The selected tab stays
  readable and arrows/menu remain distinct. This supplements Windows acceptance;
  it is not a report of live maintainer testing.
- The user guide includes captured tab-row and Open tabs menu images.

```powershell
$env:TEMP = Join-Path (Get-Location) 'build'
$env:TMP = $env:TEMP
.\Scripts\python.exe -B -u -m pytest -q tests/editor_workspace tests/project_system --basetemp=.pytest_cache/tab-overflow-subsystems
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/tab-overflow-full
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/tab-overflow-wheel
.\Scripts\python.exe -B -u tests/editor_workspace/check_packaged_tabs.py build/tab-overflow-wheel/sammyai-0.6.2a0-py3-none-any.whl
.\Scripts\python.exe -B -u tests/change_sets/check_packaged_review.py build/tab-overflow-wheel/sammyai-0.6.2a0-py3-none-any.whl
```

For an isolated interactive demo, run the following command from the checkout.
It uses temporary files and makes no model requests. Add `--capture PATH.png`
to render offscreen images; `--menu` also captures the menu.

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\Scripts\python.exe -B -u tests/editor_workspace/preview_tab_overflow.py --with-chat
```

## Maintainer Windows acceptance

- [ ] Open several Shelf Life files and show agent chat. The two scroll controls
  show clear arrows, and the active file's tab remains readable.
- [ ] Scroll left and right. Files remain open, the active file does not change,
  and any unsaved text and cursor position are preserved.
- [ ] Open the down-chevron menu. Full filenames and the active file are clear;
  selecting a hidden file activates it and reveals its tab.
- [ ] Drag a tab to a different position, then choose it through Open tabs and
  close another tab. The intended files activate/close, with normal dirty prompts.
- [ ] Resize the window and toggle chat. Long names shorten cleanly, tooltips
  show full paths, and scroll arrows disappear when the remaining tabs fit.
- [ ] Check at your normal Windows display scale, including 150% if used.

Record maintainer acceptance before marking this fix COMPLETED. Commit, push,
merge and tagging remain maintainer actions.
