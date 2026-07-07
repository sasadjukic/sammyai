# SammyAI Workspace Layout

SammyAI V0.4.1-alpha uses a project-based workspace with a writing editor, Project Explorer, chat panel, and menu commands for context, memory, and reviewed edits.

---

## 1. Sidebar Toolbar

The vertical toolbar provides quick access to common actions.

* **File operations:** New, Open, Save, and Close for documents.
* **Search:** Open search with **Ctrl+F**.
* **Chat:** Open or collapse the SammyAI chat panel.
* **LLM Setup:** Configure local and cloud model entries.
* **Settings:** Adjust model sampling settings and presets.

## 2. Project Explorer

The Project Explorer is a collapsible dock beside the toolbar.

* Open it with **View > Project Explorer** or **Ctrl+Shift+E**.
* Double-click files to open them in the editor.
* Expand and collapse folders in the tree.
* The active project appears in the window title.
* Project files remain in their original folder. SammyAI stores app metadata in OS-managed application data.

## 3. Top Menu Bar

The menu bar contains project, editing, context, and memory commands.

* **File:** Create, open, close, and reopen projects; create, open, save, and close documents.
* **Edit:** Copy, paste, cut, undo, redo, repeat, search, replace, and reviewed diff tools.
* **Edit > Compare and Review:** Compare with a file, compare with clipboard, apply a diff file, and undo or redo applied change sets.
* **View:** Show or hide the Project Explorer.
* **Advanced > Persistent Memory:** Manage project memory and summarize the current chat for review.
* **Advanced > Project Context:** Rebuild, inspect, or reset the active project context index.
* **Advanced > Legacy Manual Indexing:** Use older manual RAG indexing tools when needed.

## 4. Editing Canvas

The center of the workspace is a plain-text editor for `.txt` and `.md` files.

* **Line numbers:** Useful for references and precise editing.
* **Search and replace:** Inline search appears above the editor.
* **Reviewed edits:** Accepted AI change sets update files after review.
* **Undo and redo:** Standard document undo and redo remain available, with additional change-set undo and redo in the Compare and Review menu.

## 5. Chat Panel

The chat panel is used for model and agent workflows.

* The composer is centered before the first message and moves to the bottom after the conversation starts.
* The composer includes attachment, agent, model, and send controls.
* Each message has its own copy button.
* New Chat starts a fresh session and is disabled while generation is running.

## 6. Status Bar

The status bar shows document and background task feedback.

* **Word count:** Live word count for the editor.
* **Cursor position:** Current line and column.
* **System status:** Messages about project sync, indexing, LLM initialization, and background work.

> [!TIP]
> Use **Ctrl+Shift+Y** to repeat the last edit-related action, and **Ctrl+D** to compare the current draft with another file.
