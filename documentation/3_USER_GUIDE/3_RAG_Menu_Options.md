# Project Context and RAG Options

Retrieval-Augmented Generation (RAG) helps SammyAI find relevant details from project files without pasting entire documents into the prompt. In V0.4.1-alpha, project context is synchronized automatically for supported files.

---

## 1. Automatic Project Synchronization

When a project is open, SammyAI tracks supported files and updates project context in the background.

* **Supported formats:** `.md`, `.txt`, and `.pdf`.
* **Change detection:** Files are tracked with content hashes.
* **Project isolation:** Retrieval is scoped to the active project.
* **Sync timing:** Synchronization can run when a project opens or when files are saved.
* **Deleted files:** Removed files are cleaned from the project manifest and retrieval state.

## 2. Advanced > Project Context

Use this menu for project-level context maintenance.

* **Rebuild Active Project Index:** Reprocess supported files in the active project.
* **Context Index Statistics:** Show high-level information about the current context index.
* **Reset Entire Context Index:** Clear the index and mark project context for rebuild.

Use rebuild or reset when files moved outside SammyAI, retrieval seems stale, or you need to refresh the full project context.

## 3. Advanced > Legacy Manual Indexing

Legacy manual RAG controls remain available as fallbacks while the new context engine is tested.

* **Index Current File Manually:** Index the currently open file through the old workflow.
* **Add External File to Index:** Persistently index a file outside the active project.
* **Legacy Index Manager:** View and remove files from the legacy index.

Prefer automatic project context for normal project work.

## 4. Explicit File Context

Use explicit file references when SammyAI must rely on a specific file.

* Reference the exact file before asking for edits.
* Use relative paths when two files share the same name.
* Existing files require complete explicit file context before agent-driven modification.

## 5. Context Budget

Explicit file context, attached references, persistent memory, and retrieved RAG chunks share the same bounded prompt budget. If a response misses important context, narrow the prompt, reference fewer files, or summarize older material into persistent memory.

> [!IMPORTANT]
> RAG is persistent across sessions, but it is project-scoped. Switching projects changes the retrieval namespace.
