# SammyAI v0.4.2-alpha

## Quality-of-Life Update

SammyAI v0.4.2-alpha is a focused refinement release that improves everyday usability across the chat composer, text editor, agent feedback, and Project Explorer. This update does not introduce a major new workflow; instead, it makes existing features clearer, more responsive, and easier to manage.

## What's New

### A More Personal Welcome

The empty chat composer now feels more natural and responsive to the current workspace.

- When no project is open, SammyAI rotates between several writing-focused welcome messages.
- When a project is active, the greeting includes its name—for example, *How can I help with Ten Degrees of Sky?*
- Long project names remain on a single line and are shortened gracefully when space is limited.

### Clearer Find and Replace Highlights

Search results now use SammyAI's established accent palette instead of the previous yellow-and-blue combination.

- Other matches are highlighted in soft rose (`#e9a5a5`).
- The currently selected match is highlighted in cyan (`#65c0e0`).
- Dark foreground text keeps both highlight states readable.
- The line-number gutter retains the editor's `#1e1e1e` background for a consistent editing surface.

### Animated Agent Activity Indicator

The static *Sammy is thinking...* state now includes an animated circular indicator. It appears while an agent is processing a request and stops when processing finishes, providing immediate visual confirmation that SammyAI is still working during longer responses.

### Project Explorer File Actions

Files can now be managed directly from the Project Explorer through a dedicated right-click menu.

- **Copy** a selected file.
- **Paste** it into a project folder. If a file with the same name already exists, SammyAI creates a safely numbered copy.
- **Rename** a file without leaving the application. Open-document and retrieval state are updated when necessary.
- **Delete** a file after an explicit confirmation.

File operations are restricted to regular files inside the active project. SammyAI also protects unsaved documents, symbolic links, and application-managed metadata from unsafe changes. Relevant project context is synchronized after a file operation.

### Better Handling of Missing Projects

Projects whose folders were moved or deleted no longer leave users at a dead end in **File > Open Recent Project**. Missing projects now provide two clear choices:

- **Locate Moved Folder...** reconnects the existing SammyAI project to its new folder. The project keeps the same identity, settings, memory, and linked conversations, while its RAG index is rebuilt for the new location.
- **Remove from SammyAI...** removes the recent-project entry and cleans up SammyAI-managed project data, including project memory, conversation summaries, linked chat data, cached state, and indexed RAG content.

Removing a project from SammyAI never deletes its source folder or manuscript files. Cleanup problems are reported to the user instead of being silently ignored.

## Data and Compatibility Notes

- Existing project registrations remain compatible with this release.
- Project association is recorded automatically for new chat sessions and messages, allowing later cleanup to remain scoped to the correct project.
- Older conversations created before project association was recorded may remain untouched because SammyAI cannot safely determine which project they belong to.
- Project Explorer copy, paste, rename, and delete actions currently apply to files; folder-management actions remain outside the scope of this update.

## Verification

The completed update passed the full automated test suite:

- **125 tests passed**
- **16 optional tests deselected**

Testing covers the updated composer behavior, search highlighting and line-number styling, animated activity state, Project Explorer file operations, project relocation and removal, project-scoped chat cleanup, and RAG index cleanup.

---

SammyAI remains alpha software under active development. Feedback and issue reports are welcome as the application continues to evolve.
