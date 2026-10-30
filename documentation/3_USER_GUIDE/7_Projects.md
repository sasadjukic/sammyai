# Writing Projects

A SammyAI project is a normal folder containing the documents for one writing project. SammyAI does not copy, relocate, or add hidden files to that folder.

## Create a Project

1. Choose **File > New Project** or press **Ctrl+Shift+N**.
2. Select the parent folder.
3. Enter a project name.

SammyAI creates the folder, registers it in the local project database, opens the Project Explorer, and starts project context setup.

## Open an Existing Folder

Choose **File > Open Project** or press **Ctrl+Shift+O**, then select a folder. The folder is registered the first time it is opened. Afterwards it appears under **File > Open Recent Project**.

If a different project is already open, SammyAI checks its modified files with
Save/Discard/Cancel prompts, closes its project file tabs, and restores the
destination project's saved tabs and active file. This also applies to New
Project and Locate Moved Folder. Untitled drafts and files outside the outgoing
project stay open. Cancel, a failed save, or a failed project open keeps the
current project and its buffers open. Selecting the already-open project leaves
its tabs, unsaved edits and pending reviews alone.

When project files restore, the unused automatic **Untitled** tab disappears.
The same applies when opening the first file from the explorer or Open File.
Tabs created explicitly with **New File**, drafts you have edited (even if undo
returns them to empty), and tabs with a pending review are kept. A project with
no restorable files still has a blank editor ready for writing.

## Work with Project Files

* Double-click a file in the Project Explorer to open it.
* Expand and collapse folders directly in the tree.
* File changes made by another application can appear through the filesystem watcher.
* Use **Ctrl+Shift+E** to show or hide the Project Explorer.
* The active project name appears in the window title.

## Close a Project

Choose **File > Close Project** to close the open files inside that project's
folder, including files in subfolders. SammyAI also hides the explorer and clears
the active-project state. The files stay on disk and the project stays in recent
history.

If a project file has unsaved changes, choose **Save**, **Discard**, or **Cancel**.
All modified project tabs are checked before the project closes, including
background tabs. Cancel or a failed save keeps the project open; a Save already
completed during this attempt remains saved. Pending AI reviews must also be
resolved or explicitly discarded before closing.

Untitled drafts and files outside the project folder stay open. If no tabs
remain, SammyAI opens an empty untitled document. The project's saved file-tab
list and active file are retained for reopening it. A running selection request
is canceled on close, and a pinned selection from a closed file is cleared.

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
