# Writing Projects

A SammyAI project is a normal folder containing the documents for one writing project. SammyAI does not copy, relocate, or add hidden files to that folder.

## Create a Project

1. Choose **File > New Project** or press **Ctrl+Shift+N**.
2. Select the parent folder.
3. Enter a project name.

SammyAI creates the folder, registers it in the local project database, opens the Project Explorer, and starts project context setup.

## Open an Existing Folder

Choose **File > Open Project** or press **Ctrl+Shift+O**, then select a folder. The folder is registered the first time it is opened. Afterwards it appears under **File > Open Recent Project**.

## Work with Project Files

* Double-click a file in the Project Explorer to open it.
* Expand and collapse folders directly in the tree.
* File changes made by another application can appear through the filesystem watcher.
* Use **Ctrl+Shift+E** to show or hide the Project Explorer.
* The active project name appears in the window title.

Closing a project hides the explorer and clears the active-project state. It does not delete the folder, remove recent-project history, or close the currently displayed document.

## Project Context

When a project is open, SammyAI can synchronize supported `.md`, `.txt`, and `.pdf` files for retrieval.

* New and changed files are detected with content hashes.
* Deleted files are removed from the project manifest.
* Retrieval is isolated by project ID.
* Rebuild and reset commands are available under **Advanced > Project Context**.

## Persistent Project Memory

Project memory stores approved facts and summaries for the active project.

* Use **Advanced > Persistent Memory > Manage Project Memory...** to review and edit memories.
* Use **Advanced > Persistent Memory > Summarize Current Chat...** to create an editable summary and suggested memory items.
* Memories are scoped to the active project.

## Local Project Metadata

SammyAI stores project registration and settings in `sammyai.sqlite3` inside the operating system's application-data directory. Project-specific runtime data and caches are stored in separate app-managed directories keyed by project ID.

These locations can be overridden with `SAMMYAI_DATA_DIR` and `SAMMYAI_CACHE_DIR`.
