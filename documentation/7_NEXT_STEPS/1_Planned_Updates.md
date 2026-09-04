# Strategic Roadmap and Planned Updates

SammyAI v0.4.2-alpha is a functional foundation for project-based creative
writing. It combines a plain-text editor, project navigation, model and agent
workflows, automatic project context, persistent memory, and reviewed file
changes. The next phase will expand the everyday writing experience while
preserving the application's local-first design and user control over AI edits.

This roadmap presents the intended direction at a product level. Features will
be developed one at a time, and the next feature will begin only after the
current one is implemented, tested, documented, and working reliably. Release
numbers are planning targets and may change when implementation findings or
user feedback justify a revision.

For the technical sequence, test requirements, and completion criteria, see
the [Feature Implementation Guide](3_Feature_Implementation_Guide.md).

## v0.5 — Editor and Conversation Usability

The v0.5 series will improve the two surfaces writers use most often: the text
editor and the chat panel.

### v0.5.0-alpha — Multi-file editor workspace

SammyAI will support multiple open documents through a tabbed workspace. Tabs
will show filenames, file-type icons, and unsaved-change indicators. Writers
will be able to move between chapters, notes, outlines, and story bibles
without repeatedly closing and reopening files.

The workspace will also introduce safer document-state handling so saving,
closing, renaming, deleting, search, project context, and AI-assisted editing
continue to target the correct file.

### v0.5.1-alpha — Chat history

Saved conversations will become visible through a collapsible history view in
the chat panel. Writers will be able to find and reopen previous conversations,
distinguish project conversations from unassigned ones, and manage conversation
titles and deletion.

This work will expose conversation data that SammyAI already saves while
ensuring that model responses remain attached to the conversation in which
they were started.

### v0.5.2-alpha — US-English spell check

The editor and chat composer will gain local US-English spell checking,
including misspelling indicators, replacement suggestions, ignore controls,
and a personal dictionary. Spell checking will operate offline and will be
designed to remain responsive in long chapters and multi-file projects.

## v0.6 — Integrated AI Editing

The v0.6 series will make AI-assisted revision feel like part of the writing
workspace rather than a separate dialog-driven workflow.

### v0.6.0-alpha — Inline diff review

AI-proposed changes will move from popup review windows into the relevant
editor tab. Writers will be able to inspect proposed additions and removals in
context and accept or reject individual change groups.

Inline review will retain SammyAI's existing safeguards: explicit approval,
stale-content detection, restricted project paths, safe writes, rollback, and
undo/redo support. Review colors and controls will follow the SammyAI visual
language and will not rely on color alone.

### v0.6.1-alpha — Story-focused selection actions

Selected text will gain a writing-specific context menu with focused actions
such as rewriting, tightening prose, expanding description, improving
dialogue, changing tone, critiquing a passage, or continuing from the current
position.

Actions that modify text will produce an inline review instead of replacing
the writer's work automatically. Read-only actions, such as critique, will
leave the document unchanged.

## v0.7 — Personal Writing Preferences

### v0.7.0-alpha — Writer style profiles

Writers will be able to create and select explicit style profiles for a project
or across projects. A profile may describe preferences for voice, tone,
sentence rhythm, description, dialogue, pacing, and other craft choices.

Unlike general project memory, the active style profile will be applied
consistently and visibly to appropriate Writer and Editor workflows. Current
user instructions and document-format requirements will continue to take
precedence when they conflict with a saved preference.

## v0.8 — Authoring Formats and Finished Output

The v0.8 series will add format-aware authoring and a path from editable source
text to a finished document.

### v0.8.0-alpha — Prose and screenplay modes

SammyAI will distinguish prose and screenplay documents at the editor,
workflow, and project-context levels. Prose Mode will prioritize a comfortable
long-form writing surface. Screenplay Mode will add screenplay-aware elements,
navigation, keyboard behavior, and presentation.

The planned screenplay source format is Fountain so scripts remain portable,
plain-text files that can be opened in compatible writing tools. Exact format
behavior will be validated before implementation and documented as the feature
develops.

### v0.8.1-alpha — PDF export

Writers will be able to export the current document to PDF using layout rules
appropriate to its prose or screenplay mode. Export will support useful page
settings and metadata while including the current in-memory text, including
unsaved edits when the writer chooses to export them.

PDF generation will build on the document-format system so exported pages use
intentional typography and pagination rather than reproducing the editor
viewport.

## v0.9 — Beta Readiness

### v0.9.0-beta — Integration and reliability

The first beta milestone is planned as a stabilization release rather than a
new-feature release. Work will concentrate on data migration, long-document
performance, multi-file recovery, asynchronous workflow correctness,
accessibility, packaging, and end-to-end testing of the complete writing
experience.

## Continuing Priorities

The following priorities apply throughout every roadmap release:

* **Reliability and recovery:** Prevent silent data loss, detect stale content,
  preserve safe rollback paths, and provide useful error messages.
* **Agent quality:** Continue improving Writer revision, Editor proposals,
  Critic depth, prompt clarity, and provider-neutral behavior.
* **Context and memory:** Improve retrieval relevance, context budgeting,
  conversation summaries, provenance, and large-project handling.
* **Local-first behavior:** Keep projects and application state under the
  writer's control and avoid unnecessary network requirements.
* **User approval:** Keep AI-generated file changes reviewable and reversible.
* **Compatibility:** Preserve existing projects, conversations, memories, and
  supported text files as data models evolve.
* **Documentation:** Update guides, screenshots, known issues, and release
  notes as each feature ships.

> [!NOTE]
> This roadmap describes the current direction after v0.4.2-alpha. Priorities
> and release boundaries may be adjusted when testing reveals a safer or more
> useful sequence.
