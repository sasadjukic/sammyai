# SammyAI Feature Implementation Guide

## Purpose

This document turns the post-v0.4.2-alpha feature ideas into a sequential
implementation roadmap. Each feature receives its own release and must be
implemented, tested, documented, and accepted before work starts on the next
feature.

The proposed version numbers are planning suggestions. They reflect the size
and architectural impact of each change rather than a promise about release
dates.

## How to use this guide

For every release:

1. Start from the last accepted release, not from an unfinished feature branch.
2. Write or update characterization tests before changing existing behavior.
3. Implement the smallest complete version of the feature described here.
4. Run the feature tests, the relevant subsystem tests, and the full automated
   suite.
5. Complete the manual acceptance checklist on Windows.
6. Update user documentation and release notes.
7. Tag the release only after every definition-of-done item passes.
8. Do not begin the next feature while the current release has known
   correctness, data-loss, or migration problems.

The order is intentional. Later editor features depend on the document
workspace and review infrastructure introduced by earlier releases.

## Proposed release sequence

| Order | Proposed release | Feature | Scope |
| --- | --- | --- | --- |
| 0 | v0.4.2-alpha baseline | Stabilization checkpoint | Establish a reproducible starting point |
| 1 | v0.5.0-alpha | Multi-file editor workspace | Major editor architecture and UX change |
| 2 | v0.5.1-alpha | Chat history | Expose and manage persisted conversations |
| 3 | v0.5.2-alpha | US-English spell check | Shared editor/composer language tooling |
| 4 | v0.6.0-alpha | Inline diff review | Major AI-edit review workflow change |
| 5 | v0.6.1-alpha | Story-focused selection actions | Context-menu AI writing operations |
| 6 | v0.7.0-alpha | Writer style profiles | Persistent, deterministic style preferences |
| 7 | v0.8.0-alpha | Prose and screenplay modes | Format-aware editing and document semantics |
| 8 | v0.8.1-alpha | PDF export | Format-aware, paginated output |
| 9 | v0.9.0-beta | Integration hardening | No new features; prepare the combined system for beta |

## Cross-cutting architecture target

The current runtime services can remain in place. The main architectural work
is to stop treating the main window as the owner of every piece of document,
conversation, and review state.

The intended dependency flow is:

```text
DocumentService
      |
DocumentSession / DocumentWorkspace
      |                         |
EditorDecorationManager     active document identity
      |                         |
spell check                inline review
                                |
                      selection writing actions

DocumentFormatRegistry -> prose/screenplay rendering -> PDF export

ChatManager -> conversation list model -> chat history UI

StyleProfileRepository -> style prompt layer -> writer/editor workflows
```

Recommended ownership boundaries:

- `sammyai_core` owns persistent models, validation, repositories, and services.
- `ui` owns PySide6 widgets, view models, and user interaction.
- `editing` owns diffs, review sessions, accepted/rejected hunks, and safe
  application of reviewed changes.
- `sammyai.py` should coordinate these components instead of containing their
  internal behavior.

## Release 0: v0.4.2-alpha baseline checkpoint

### Goal

Create a known-good baseline so regressions introduced by later features are
measurable.

### Required steps

1. Choose one authoritative source for the application version.
2. Reconcile the current mismatch between `RELEASE_NOTES_v0.4.2-alpha.md` and
   the version declared in `pyproject.toml`.
3. Prefer PEP 440 syntax inside Python package metadata, such as `0.4.2a0`,
   while displaying `v0.4.2-alpha` to users if that remains the preferred
   product naming convention.
4. Install the development test dependencies with the project test extra.
5. Run the complete non-external, non-model test suite and record the exact
   command and result.
6. Create a reusable manual test project containing:
   - several `.md` chapters;
   - several `.txt` notes;
   - one PDF reference;
   - one long document;
   - at least two saved conversations;
   - project memories, including one style memory.
7. Confirm opening, editing, saving, project context synchronization, chat,
   agent workflows, reviewed changes, undo, redo, and memory management.
8. Record known issues that are explicitly accepted for the baseline.

### Baseline gate

- The full supported test suite passes.
- The working tree is clean.
- The application version is reported consistently.
- The reusable manual test project is documented and available.
- Every accepted baseline issue is written down rather than held in memory.

---

## Release 1: v0.5.0-alpha — Multi-file editor workspace

### Goal

Allow multiple documents to remain open in a VS Code-like tab bar without
losing unsaved text or confusing editor, project, RAG, or agent state.

### Product behavior

- Each open document has a tab showing a file-type icon, full filename, and
  dirty-state marker.
- Selecting an already-open file focuses its existing tab.
- Untitled documents can coexist and have unique names.
- Tabs can be activated and closed independently.
- Closing a dirty tab or quitting with dirty tabs asks the user to save,
  discard, or cancel.
- The active tab drives Save, Save As, search, word count, cursor position,
  manual indexing, selection operations, and legacy DBE context.
- Open tabs and the active tab are restored per project where practical.

### Recommended design

Create a non-Qt document state model, for example `DocumentSession`, containing
at least:

- stable session ID;
- resolved path or `None` for an untitled document;
- display name;
- clean content hash or clean snapshot;
- modified state;
- cursor and scroll position;
- document format ID;
- external-change state.

Create `ui/editor_workspace.py` with an `EditorWorkspace` widget that owns a
`QTabWidget`, a map of normalized paths to document IDs, and the active
document. Move `CodeEditor` and `LineNumberArea` out of `sammyai.py` into a
dedicated UI module.

Do not make every caller reach through the tab widget. Expose a small API such
as:

- `active_session()`;
- `active_editor()`;
- `open_document(path)`;
- `new_document()`;
- `save_document(id)`;
- `close_document(id)`;
- `sessions_for_path(path)`;
- `dirty_sessions()`.

### Implementation steps

1. Add characterization tests for the existing single-document open, save,
   rename, delete, RAG-active-file, DBE, search, and status-bar behavior.
2. Add `DocumentSession` and test path normalization, untitled IDs, clean/dirty
   transitions, and clean snapshot updates.
3. Extract `CodeEditor` without changing its visible behavior.
4. Add `EditorWorkspace` with one initial untitled tab and signals for active
   document, modified state, cursor position, and tab closure.
5. Implement icons. Start with `QFileIconProvider` or a small bundled mapping
   for Markdown, plain text, and later Fountain files. Always retain the file
   extension in the label.
6. Replace direct main-window ownership of `self.editor` and
   `self.current_file` with active-document accessors.
7. Migrate file actions: New, Open, Save, Save As, Close, and optionally Save
   All.
8. Migrate editor actions: undo, redo, copy, cut, paste, find, replace, word
   count, and line/column display.
9. Update Project Explorer activation so duplicate opens focus the existing
   tab.
10. Update rename and delete handling to locate every open session for the
    affected path, not only the active session.
11. Update safe change-set conflict detection to inspect all dirty open
    documents. A change set must not overwrite a dirty background tab.
12. When an agent changes a clean background tab, reload that tab or mark it as
    externally changed. Never silently leave stale content in an open tab.
13. Keep only the active document marked as the RAG active file. Change the
    active-file boost when the selected tab changes.
14. Capture document IDs for asynchronous operations so their results cannot
    be applied to whichever tab happens to be active later.
15. Store open project-relative paths and the active path in project settings.
    Ignore missing or out-of-project paths during restoration.
16. Add close-event handling for every dirty tab before runtime services shut
    down.
17. Update the user guide and screenshots.

### Automated tests

- Opening two files preserves both contents and cursor positions.
- Reopening the same normalized path does not create a duplicate tab.
- Multiple untitled documents receive unique names.
- Dirty markers update after edit, save, undo-to-clean, and Save As.
- Canceling a dirty-tab prompt keeps the tab and content open.
- Canceling the quit prompt prevents shutdown.
- Rename and delete operations correctly update or close matching tabs.
- A dirty background tab blocks a conflicting agent change set.
- A clean background tab is refreshed after an approved external change.
- Switching tabs updates search, status-bar data, and RAG active-file state.
- Project restoration tolerates renamed, deleted, and moved files.

### Definition of done

- No workflow can silently discard a dirty buffer.
- Existing single-file behavior remains available through the active tab.
- All document-related tests and the full suite pass.
- The manual test project can keep at least ten documents open and switch,
  edit, save, close, rename, and restore them reliably.
- No known wrong-document bug remains in asynchronous chat or DBE workflows.

---

## Release 2: v0.5.1-alpha — Chat history

### Goal

Make already-persisted conversations visible, understandable, and safely
switchable from the chat panel.

### Product behavior

- A history button expands or collapses a conversation list.
- Each row shows a useful title and last-updated time.
- Current-project conversations are shown by default.
- Users can switch conversations, start a new conversation, rename one, and
  delete one with confirmation.
- Older sessions without project metadata remain accessible under an
  Unassigned or All Conversations view.
- The selected session and its full transcript are restored correctly.

### Implementation steps

1. Introduce a `ConversationSummary` or `SessionListItem` view model containing
   ID, title, preview, project ID, created time, updated time, and message count.
2. Add a `ChatManager` API that returns sessions sorted by `updated_at`
   descending rather than exposing only raw IDs.
3. Generate an initial title from the first user message. Keep title generation
   deterministic and local; AI-generated titles can be considered later.
4. Store explicit renamed titles in existing session metadata for backward
   compatibility.
5. Persist the last active session ID globally or per project. If it no longer
   exists, choose the most recently updated valid session.
6. Add a collapsible history panel to the chat header. Use a narrow overlay or
   splitter so opening history does not make the composer unusable.
7. Add transcript-loading APIs to `ChatPanel` instead of reconstructing widget
   internals from the main window.
8. Render user, assistant, and supported system messages in timestamp order.
9. Capture the originating session ID when sending a model request. Pass it
   explicitly when building context and saving the response.
10. Decide how session switching behaves while a model is responding. The
    preferred behavior is to permit switching while keeping activity attached
    to the originating conversation.
11. Refresh list titles, previews, counts, and timestamps after every mutation.
12. Preserve current project-removal cleanup semantics.
13. Add empty, loading, corrupted-session, and deletion-confirmation states.
14. Update the conversation documentation.

### Automated tests

- Persisted sessions appear in newest-first order.
- A selected session renders the correct messages and agent metadata.
- New, rename, and delete update both UI state and JSON persistence.
- A response started in session A remains in session A after switching to B.
- Project filters do not hide unassigned legacy conversations permanently.
- Corrupted or missing session files do not prevent other history from loading.
- Removing a project removes only conversations known to belong to it.

### Definition of done

- Users can discover and reopen every valid persisted conversation.
- Asynchronous responses can never be written to the wrong session.
- Backward-compatible sessions load without a manual migration.
- Chat persistence, project cleanup, and full-suite tests pass.

---

## Release 3: v0.5.2-alpha — US-English spell check

### Goal

Provide responsive US-English spelling feedback and corrections in every
document tab and in the chat composer.

### Recommended design

Create a UI-independent `SpellCheckService` with a swappable dictionary
backend. Begin with a distributable US-English dictionary or a pure-Python
backend after checking its package and dictionary-data licenses. Do not require
an internet connection or a system-installed native library at runtime.

Create one `EditorDecorationManager` per text widget. It must merge spell,
search, inline-diff, and future format decorations instead of allowing each
feature to overwrite `setExtraSelections()` independently.

### Implementation steps

1. Select and document the dictionary backend and license.
2. Add dependency and dictionary data to both `pyproject.toml` and packaging
   configuration.
3. Implement tokenization with exact character ranges.
4. Initially ignore URLs, email addresses, file paths, Markdown code spans,
   numbers, punctuation-only tokens, and configured all-cap screenplay tokens.
5. Add a debounced background scan. Do not scan an entire long document
   synchronously on each keystroke.
6. Underline misspellings without changing document contents or modified
   state.
7. Extend the standard right-click menu with ranked replacement suggestions,
   Ignore Once, Ignore All, and Add to Dictionary.
8. Add the same behavior to `AutoGrowingTextEdit` in the composer.
9. Store personal dictionary words locally. Decide explicitly whether entries
   are global or project-specific; supporting both is preferable.
10. Recheck affected blocks after edits and recheck all visible documents after
    dictionary changes.
11. Add an application setting to enable or disable spell checking and display
    the active language as English (United States).
12. Test packaging in a clean environment to ensure dictionary data is
    included.

### Automated tests

- Known words are not marked and unknown words are marked at correct offsets.
- Contractions, possessives, hyphenated words, Unicode punctuation, and line
  breaks are handled consistently.
- URLs, Markdown code, and paths are ignored as designed.
- Replacement changes only the selected occurrence and participates in undo.
- Ignore/Add to Dictionary update all relevant widgets.
- Spell decorations coexist with search decorations.
- Large documents do not run a full dictionary scan on the UI thread.

### Definition of done

- Spell checking works in all open editor tabs and the composer.
- Typing remains responsive in a long chapter.
- Corrections are undoable and never alter text automatically.
- The feature works offline in a clean packaged installation.
- All editor, composer, packaging, and full-suite tests pass.

---

## Release 4: v0.6.0-alpha — Inline diff review

### Goal

Review AI-proposed changes inside the relevant editor tab with clear accepted
and rejected states, while preserving SammyAI's existing safe-apply guarantees.

### Recommended UX

Do not insert diff marker text into the user's real document. Create an inline
review mode inside the editor area. A practical first implementation can swap
the normal editing surface for a read-only review document in the same tab,
showing context, removed lines, proposed lines, and hunk controls.

Use theme tokens for:

- accepted/addition foreground and background;
- rejected/deletion foreground and background;
- current hunk;
- unresolved hunk;
- review gutter and controls.

### Recommended model

Add a `ReviewSession` containing:

- review ID and source change-set ID;
- target document ID and normalized path;
- immutable original content and hash;
- proposed content and hash;
- structured hunks;
- per-hunk state: pending, accepted, or rejected;
- creation time and originating agent/session IDs.

The final content must be synthesized once from the original snapshot and all
accepted hunks. Do not repeatedly apply hunks to an already-mutated buffer,
because earlier decisions can shift later line ranges.

### Implementation steps

1. Add structured hunks to `FileChangePreview` or create a new review-specific
   preview model. Keep unified text generation as a compatibility/export view.
2. Write tests that map before/after content to stable hunk IDs.
3. Implement `ReviewSession` state transitions and final-content synthesis.
4. Add an inline review surface to each document tab.
5. Render unchanged context, removed content, inserted content, and hunk
   boundaries accessibly; do not rely on color alone.
6. Add Accept Hunk, Reject Hunk, Accept All, Reject All, Previous, and Next.
7. Keep the editable document locked while its review is unresolved, or make
   cancellation explicit before editing resumes.
8. On completion, build a safe change set from the accepted result and apply it
   through `SafeFileTools` so stale-content checks, rollback, and undo remain in
   force.
9. Detect conflicts if the file or buffer changed after review creation. Offer
   regenerate/cancel rather than force-applying.
10. Support the active single-file proposal first, then multi-file change sets
    by opening or locating the corresponding tabs.
11. Keep the current popup review available behind a temporary fallback until
    inline review passes all compatibility tests.
12. Route legacy DBE and structured agent change sets through the same review
    controller.
13. Remove the fallback only after feature parity is verified.
14. Update screenshots and Diff-Based Editing documentation.

### Automated tests

- Accept all produces byte-for-byte proposed content.
- Reject all leaves byte-for-byte original content.
- Mixed hunk decisions produce the expected composite content.
- Decisions remain correct when earlier hunks change line counts.
- Editing or external modification during review produces a conflict.
- Reviews remain attached to the originating tab after tab switches.
- Multi-file review blocks dirty conflicting tabs.
- Applied inline reviews can be undone and redone through existing history.
- Colors come from theme configuration and controls have text/tooltips.

### Definition of done

- No AI edit bypasses explicit review.
- Partial acceptance is deterministic and covered by tests.
- Safe apply, rollback, stale-content detection, undo, and redo still work.
- Reviews cannot jump to the wrong document after tab or chat switching.
- The popup is either removed or retained only as a documented fallback.
- All editing and full-suite tests pass.

---

## Release 5: v0.6.1-alpha — Story-focused selection actions

### Goal

Let writers select text and invoke useful story-editing operations from the
standard right-click menu, with every mutation returned through inline review.

### Initial action set

Keep the first menu intentionally small:

- Rewrite Selection;
- Tighten Prose;
- Expand Description;
- Improve Dialogue;
- Change Tone...;
- Critique Selection;
- Continue From Here.

Critique is read-only. The other actions either propose a replacement for the
selection or an insertion at the cursor.

### Implementation steps

1. Override or extend `CodeEditor.contextMenuEvent()` by starting with Qt's
   standard context menu, preserving Cut, Copy, Paste, Select All, and spell
   suggestions.
2. Create a `SelectionActionRequest` containing document ID, path, clean hash,
   selected range, exact selected text, bounded surrounding context, format ID,
   active style profile ID, chat session ID, and action type.
3. Disable actions that require a selection when no text is selected.
4. Define provider-neutral prompt templates and a strict output contract for
   replacement text.
5. Run actions asynchronously while keeping the request attached to its
   originating document and selection snapshot.
6. Render mutating results through `ReviewSession`; never replace selection
   text immediately.
7. Show critiques in chat or a dedicated non-mutating panel without creating a
   fake diff.
8. If the document changes before the response arrives, mark the result stale
   and require regeneration.
9. Add progress, cancellation, empty-result, malformed-result, and model-error
   states.
10. Record agent and action metadata in the conversation for traceability.
11. Document exactly what text and surrounding context each action sends to
    the configured model.

### Automated tests

- The standard Qt context actions remain available.
- Selection actions enable and disable correctly.
- Prompt input contains the exact selection and bounded context.
- Results return to the originating document after tab switches.
- A changed selection snapshot cannot be silently overwritten.
- Mutating actions always enter inline review.
- Critique never changes the document.
- Model errors leave the document untouched.

### Definition of done

- Every initial action has predictable behavior and documentation.
- No asynchronous result can modify the wrong document or stale selection.
- All mutations require inline acceptance and remain undoable.
- Editor, agent-workflow, and full-suite tests pass.

---

## Release 6: v0.7.0-alpha — Writer style profiles

### Goal

Let users define, select, and consistently apply preferred writing styles
without depending on the relevance ranking of generic project memory.

### Scope decision

The first release should implement explicit user-authored style profiles.
Automatic imitation of a named author or automatic extraction from large
writing samples is a separate future enhancement and should not block a useful,
controllable first version.

### Recommended model

Add a database migration for a `style_profiles` table with fields such as:

- ID;
- optional project ID (`NULL` for global profiles);
- profile name;
- style instructions;
- optional short approved examples;
- active/default flags or an explicit active-profile setting;
- created and updated timestamps.

Generic memories with kind `STYLE` can remain useful evidence, but the active
profile should be injected deterministically through a named prompt layer.

### Implementation steps

1. Define precedence rules:
   - system safety and output contracts are never overridden;
   - the user's current explicit request overrides style preferences;
   - the active document format overrides incompatible style formatting;
   - the active style profile guides voice and craft where no conflict exists.
2. Add the database migration, repository, service, and dataclasses.
3. Support global profiles and project-specific profiles.
4. Add create, edit, duplicate, archive/delete, set active, and preview UI.
5. Add a style selector near the agent selector or in project settings. Make
   “No style profile” an explicit choice.
6. Add a `STYLE` prompt layer between the agent role and workflow/output
   instructions, or another documented stable location.
7. Apply the profile by default to Writer and Editor operations. Decide
   separately whether Assistant and Brainstormer should receive it; Critic
   should be able to evaluate adherence without adopting the voice itself.
8. Include the active profile in selection action requests and Writer
   draft/evaluate/revise stages.
9. Prevent evaluator prompts from accidentally rewriting the style profile.
10. Optionally offer a one-time conversion of existing approved style memories
    into profiles, with user confirmation and no deletion of the source memory.
11. Add an inspectable “style used” entry to agent run metadata.
12. Document examples of effective style instructions and conflicting rules.

### Automated tests

- Database migration preserves all existing projects and memories.
- Global and project profile lookup obeys scope and active selection.
- Prompt composition includes the active profile exactly once and in stable
  order.
- Explicit current-run instructions can override a style preference.
- Writer draft and revision stages receive the same intended profile.
- Critic can assess style without being told to reproduce it.
- No-profile mode reproduces pre-feature prompt composition.

### Definition of done

- Users can reliably see which style profile is active.
- The same profile produces the same prompt layer across supported workflows.
- Existing style memories and projects remain compatible.
- Migration, prompt-layer, workflow, and full-suite tests pass.

---

## Release 7: v0.8.0-alpha — Prose and screenplay modes

### Goal

Introduce explicit document semantics and writing assistance for prose and
screenplays while keeping source files portable and text-first.

### Format decision

Recommended canonical representations:

- Prose: Markdown or plain text.
- Screenplay: Fountain plain text.

The UI may present margins, typography, element types, and shortcuts without
storing opaque rich-text markup. This keeps files usable in other editors and
compatible with RAG and safe change sets.

### Recommended architecture

Create a central `DocumentFormatRegistry`. Each format definition should own:

- format ID and display name;
- recognized extensions;
- editable/referenceable/indexable capabilities;
- tokenizer or parser;
- editor presentation policy;
- keyboard behavior;
- prompt guidance;
- export renderer.

Replace the currently scattered extension sets in document, context, indexer,
file-tool, file-dialog, and Project Explorer code with this registry.

### Implementation steps

1. Write a short product specification defining what Prose Mode and Screenplay
   Mode do. Avoid calling a font-only change a document format.
2. Add `DocumentFormat` and the central registry.
3. Migrate existing `.txt`, `.md`, and `.pdf` capability checks to registry
   queries without changing behavior.
4. Store project default format and per-document detected/selected format.
5. Implement Prose Mode first: word wrapping, readable text width, paragraph
   presentation, and prose-specific status information.
6. Add `.fountain` as an editable, referenceable, and indexable text type.
7. Implement a Fountain parser that identifies scene headings, action,
   character cues, dialogue, parentheticals, transitions, centered text, and
   notes without destructively rewriting source text.
8. Add screenplay-aware presentation and navigation.
9. Add Enter/Tab behavior for common element transitions, while retaining an
   escape route to literal plain-text editing.
10. Add a visible current-element indicator and format selector.
11. Add a document-format prompt layer so Writer, Editor, and selection actions
    receive the same semantic requirements.
12. Make spell checking aware of Fountain markup and screenplay conventions.
13. Make inline diff review preserve format parsing and decorations.
14. Add sample prose and Fountain fixtures covering edge cases.
15. Update supported-format, project, RAG, agent, and editor documentation.

### Automated tests

- Registry migration preserves existing extension behavior.
- Markdown and plain-text content round-trip byte-for-byte after viewing.
- Fountain content round-trips without hidden formatting changes.
- Fountain elements are classified consistently.
- Keyboard transitions create the intended element types and remain undoable.
- Format state follows the correct tab and survives project restoration.
- RAG, explicit references, and safe file tools support `.fountain`.
- Spell, search, inline review, and selection actions coexist in both modes.

### Manual validation

- Draft and edit a prose chapter.
- Draft and edit a multi-scene Fountain screenplay containing dialogue,
  parentheticals, transitions, and page-breaking-length scenes.
- Open the Fountain file in an independent compatible editor and confirm that
  it parses as expected.

### Definition of done

- “Prose” and “Screenplay” describe observable semantic behavior.
- Source files remain portable plain text.
- No format operation silently rewrites a document.
- Every existing editor feature works in both modes or is explicitly disabled
  with an explanation.
- Format, RAG, safe-edit, and full-suite tests pass.

---

## Release 8: v0.8.1-alpha — PDF export

### Goal

Export the current in-memory document to a readable, paginated PDF that follows
its prose or screenplay format rules.

### Recommended design

Create an export service independent of the editor widget, for example
`exporting/pdf_exporter.py`. Its input should be document content, format ID,
document metadata, and export settings. Do not treat a screenshot or direct
printout of the editor viewport as the canonical export path.

Use Qt's PDF/printing facilities where they provide stable results. Add another
PDF library only if required capabilities cannot be achieved reliably with the
existing PySide6 dependency.

### Implementation steps

1. Define initial export options: output path, page size, margins, title,
   author, font, page numbers, and optional headers/footers.
2. Define sensible separate defaults for prose and screenplay.
3. Implement a format-to-layout renderer using the same format semantics as the
   editor.
4. Export the in-memory buffer, including unsaved edits, after clearly showing
   which document is being exported.
5. Add File > Export to PDF... and an optional toolbar action.
6. Validate the destination, append `.pdf` when appropriate, and confirm before
   overwriting an existing file.
7. Keep export failure atomic: an incomplete export must not replace a valid
   existing PDF.
8. Add progress feedback for long documents without blocking normal window
   repainting.
9. Add document metadata to the PDF where supported.
10. Ensure screenplay dialogue, scene headings, margins, page breaks, and page
    numbers follow the selected screenplay specification.
11. Test installed-package resource and font lookup, not only source-tree runs.
12. Update supported-formats and user-guide documentation with known layout
    limitations.

### Automated tests

- Prose and screenplay exports create valid, non-empty PDF files.
- Extracted PDF text contains the expected content in the expected order.
- Page count increases for a controlled long fixture.
- Metadata and page-size settings are present where supported.
- Unsaved in-memory content is included.
- Canceling or failing an export leaves existing files untouched.
- Unicode punctuation and common story characters render correctly.

### Visual verification

Render exported PDF pages to images and inspect at minimum:

- first page;
- a normal middle page;
- a page boundary containing a paragraph or dialogue block;
- last page;
- a page containing italics or other supported emphasis;
- a screenplay page with scene heading, action, character, parenthetical, and
  dialogue elements.

### Definition of done

- Exported PDFs open in at least two independent PDF readers.
- Prose and screenplay fixtures have acceptable typography and pagination.
- Export never modifies the source document.
- Failure and overwrite behavior are safe and tested.
- PDF, format, packaging, and full-suite tests pass.

---

## Release 9: v0.9.0-beta — Integration hardening

### Goal

Stop adding features and validate the complete authoring workflow before
calling the application beta-quality.

### Required validation

1. Upgrade a copy of real v0.4.2-alpha data through every database migration.
2. Test projects containing many chapters, long chats, style profiles, and
   several simultaneously open documents.
3. Exercise parallel states: model response in one chat, another chat visible,
   several tabs open, one dirty background tab, and a pending inline review.
4. Test crash/restart behavior during editing, review, and export.
5. Test high-DPI displays, keyboard-only navigation, focus order, accessible
   labels, and light/dark theme assumptions.
6. Profile project restoration, spell checking, large-document switching,
   review rendering, and PDF generation.
7. Remove compatibility adapters and popup fallbacks only when their callers
   and tests have been migrated.
8. Consolidate duplicated format, theme, and persistence constants.
9. Refresh every screenshot and user-facing document.
10. Publish a complete migration and rollback note.

### Beta gate

- No known data-loss or wrong-target asynchronous bug.
- No open high-severity migration, review, or export defect.
- The full supported test suite passes in a clean development environment.
- Packaged Windows installation passes the complete manual workflow.
- Release notes identify remaining alpha-quality limitations that are not beta
  blockers.

## Standard release checklist

Use this checklist for every feature release:

- [ ] Scope and non-goals are written before implementation.
- [ ] Existing behavior is protected by characterization tests.
- [ ] New core logic has unit tests.
- [ ] UI-to-service integration has tests.
- [ ] Failure, cancellation, stale-state, and restart paths are tested.
- [ ] Database/file migrations are backward compatible and tested from an old
      fixture.
- [ ] No user document is overwritten without review or confirmation.
- [ ] Background work captures stable document and conversation identities.
- [ ] The complete automated suite passes.
- [ ] The Windows manual acceptance checklist passes.
- [ ] Packaging is tested from a clean environment.
- [ ] User documentation and screenshots are updated.
- [ ] Version metadata and release notes agree.
- [ ] The release is tagged from a clean working tree.

## Change-control rule

Small corrective work discovered during a feature belongs to that release when
it is necessary for correctness. Unrelated improvements should be recorded for
later rather than expanding the current scope. The next feature begins only
after the current definition of done is satisfied or the roadmap is explicitly
revised.
