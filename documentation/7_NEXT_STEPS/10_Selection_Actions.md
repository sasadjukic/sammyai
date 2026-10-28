# Story selection actions — implementation and acceptance

Started 2026-10-21 from `main` at `04caaf1`, on
`codex/story-selection-actions`. The implementation is merged into `main`, and
maintainer Windows acceptance was confirmed on 2026-10-28.

## Implementation

- UI-independent immutable selection snapshots, bounded context and strict
  provider-neutral replacement/insertion/critique contracts.
- Per-surface menu registry shared by editor tabs and composer. Qt editing and
  spell actions remain the base menu; story contributions target editors only.
- Automatic single-passage composer reference, explicit pinning, removal and
  conversation-local drafts, with Unicode-correct logical line ranges.
- Asynchronous controller with request-owned document/chat/project identity,
  cancellation, stale-buffer/path/disk checks, inline review and diagnostic links.
- Existing safe file transactions, CRLF preservation and draft Undo/Redo.

## Automated verification

Verified on 2026-10-21:

- Selection, editor, spelling, diagnostics, agent and chat subsystem run:
  **308 passed** (before the final deleted-conversation regression test).
- Full supported suite: **454 passed, 1 skipped, 16 deselected**, 67.28 seconds.
  This includes 33 selection tests. The skip is Windows symlink creation; external
  provider and model-download tests are excluded by the repository configuration.
  Two existing dependency deprecation warnings remain.
- Offline wheel build and isolated installed-package checks for selection
  contracts, diagnostics and review/file history.
- Qt-rendered Windows-font screenshots inspected for the reference chip, editor
  and composer menus, and the resulting inline review. These are synthetic
  offline checks, not configured-provider manual acceptance.
- `git diff --check` passed.

The first full run hit sandbox temporary-folder permissions in existing RAG
tests. Redirecting both Python/OS temporary files and pytest temporary files to
the workspace resolved those failures without changing the RAG tests.

```powershell
$env:TEMP = Join-Path (Get-Location) 'build'
$env:TMP = $env:TEMP
.\Scripts\python.exe -m pytest -q --basetemp=.pytest_cache/selection-full2
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/selection-wheel-final
.\Scripts\python.exe tests/diagnostics/check_packaged_diagnostics.py build/selection-wheel-final/sammyai-0.6.2a0-py3-none-any.whl
.\Scripts\python.exe tests/change_sets/check_packaged_review.py build/selection-wheel-final/sammyai-0.6.2a0-py3-none-any.whl
.\Scripts\python.exe tests/editor_workspace/preview_selection_actions.py --capture build/selection-preview-final
```

Run `preview_selection_actions.py` without `--capture` for an isolated interactive
demo using a fake provider. It never sends a model request or changes a real
writing project.

## Manual Windows acceptance

- [✓] Highlight one line and several lines; verify reference labels and no pasted
  source in the composer. Include non-BMP characters such as emoji.
- [✓] Pin via Add Selection to Chat, switch tabs, then ask about the original
  passage. Remove the reference and verify ordinary agent chat.
- [✓] Compare editor and composer right-click menus, including spelling suggestions.
- [✓] Try all seven actions with a configured provider, including tone cancel,
  read-only critique and continuation in the middle of a document.
- [✓] Accept/reject individual hunks; verify saved-file history and unsaved-draft
  Undo/Redo. Confirm text outside the selection/insertion is preserved.
- [✓] Edit, rename, close or externally change the source while generating;
  verify the result is stale. Switch tabs and verify the original target.
- [✓] Cancel during generation; verify a late reply cannot open review or apply.
- [✓] Check provider failure, empty/malformed/truncated output and diagnostics.
- [✓] Run the packaged application and inspect long filenames, narrow composer widths, multiline references, and keyboard context-menu use.
