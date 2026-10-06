# Legacy DBE retirement — 2026-09-21

Branch: `codex/retire-legacy-dbe`, based on `main` at `af882d8` after the
maintainer tested and merged manual indexing retirement. The maintainer reported
that DBE retirement was pushed and merged into `main` (`109bd18`); merge recorded
on 2026-10-06. Individual checklist results were not supplied. Package version
remains `0.6.0a0` for this maintenance follow-up.

## Behavior

- Advanced now contains **Persistent Memory** and **Project Context**. The
  **Enable Legacy DBE Mode** toggle and its trailing menu separator are removed.
- Chat requests always use the selected agent: Assistant, Brainstormer, Writer,
  Editor, or Critic. The separate DBE context builder, model prompt, response
  splicing, signal, and review handler are removed.
- For AI edits, save the document in the active project, select **Editor**, and
  reference the exact file in the request, for example
  `Tighten the dialogue in @chapter.md`. Complete file context and explicit
  review still govern project edits.
- Selecting editor text or placing the cursor does not implicitly send that
  passage as editable context. Story-focused selection actions remain the
  next planned feature in the implementation guide.
- **Edit > Compare and Review** retains file, clipboard, and patch comparisons.
  These share inline review with agent proposals, including conflict checks,
  explicit application, draft undo/redo, and safe project file history.
- Existing documents, projects, index entries, and chat history are preserved.
  No database or saved-data migration is required; DBE mode was transient.

The temporary popup review compatibility option remains available for manual
comparisons and agent change sets. Its generic dialog title is now **Diff Viewer**.

## Validation

- Before implementation, existing editor workspace, chat history, UI bootstrap,
  and agent workflow tests passed: **66 passed**.
- Six additional characterization tests passed before removing DBE. They cover
  all five agents through the chat send handler, preservation of unsent editor
  selections, and an Editor proposal reaching review before safe apply/undo/redo.
- Existing DBE-based review tests now exercise supported manual comparisons:
  draft undo/redo, CRLF preservation, the originating tab after a tab switch,
  and rejection of document path changes during review. Asynchronous chat still
  saves its response in the originating conversation.
- Full supported suite: `.\Scripts\python.exe -m pytest -q` — **236 passed,
  1 skipped, 16 deselected**, 2 existing dependency deprecation warnings,
  25.70 seconds on Windows / Python 3.14.6. The existing skipped reference-import
  test requires Windows symlink creation permission. Model/external tests were
  not run.
- `.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation -w dist/legacy-dbe-retirement`
  built the wheel successfully. The stale ignored build copy of the deleted DBE
  module was removed before building.
- `.\Scripts\python.exe tests\change_sets\check_packaged_review.py dist\legacy-dbe-retirement\sammyai-0.6.0a0-py3-none-any.whl`
  passed in a fresh temporary environment using only the local wheel,
  `--no-index --no-deps`, isolated imports, and blocked network connections.
  It verifies chat persistence, review synthesis, CRLF, safe apply/undo/redo,
  theme assets, and absence of the retired DBE prompt from the wheel. This is
  a core/package check, not a full clean GUI installation.
- No DBE runtime references remain in the main window, chat manager, review UI,
  or core services. `git diff --check` passes.

## Desktop acceptance checklist

- [X] Launch SammyAI and confirm Advanced contains only Persistent Memory and
  Project Context, with no legacy DBE toggle or trailing separator.
- [X] Open a project, save a chapter, choose Editor, and request a change using
  an explicit file reference. Confirm inline review opens and the file remains
  unchanged until decisions are applied. Verify project history undo/redo.
- [X] Send ordinary chat requests with the other agents. Confirm the selected
  agent responds and no cursor/selection-based DBE review opens.
- [X] Compare an unsaved draft with clipboard text. Accept and apply, then
  verify editor undo/redo. Compare a saved project file and verify file history.
- [X] Check file and patch comparisons, review cancellation, tab switching,
  and protection against external changes while a proposal is open.
- [X] Reopen an existing conversation and confirm its transcript is intact.
  Confirm Project Context import and index inspection remain available.

See the [chat guide](../3_USER_GUIDE/2_LLM_Chat.md) and
[review guide](../3_USER_GUIDE/5_Diff_Edits_Menu_Options.md) for the supported
workflow. Merge through the maintainer workflow after acceptance.
