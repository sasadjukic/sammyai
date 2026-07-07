# Supported Text Formats

SammyAI focuses on text-first creative writing formats that work well with LLMs, retrieval, and safe project editing.

## 1. Text Editor

The primary editor is a plain-text writing surface.

* **Supported formats:** `.txt`, `.md`
* **Capabilities:**
  * Open, edit, and save plain text and Markdown files.
  * Use UTF-8 by default, with fallback support for Latin-1.
  * Preserve normal text files inside your project folder.
* **Other formats:**
  * The editor may allow selecting other files, but binary formats such as `.docx`, `.odt`, and `.rtf` will not render as rich documents. Convert them to `.txt` or `.md` first.

## 2. Automatic Project Context

Project context synchronization scans supported files in the active project so SammyAI can retrieve relevant material during chat and agent workflows.

* **Supported formats:** `.txt`, `.md`, `.pdf`
* **Synchronization:** Changed, new, and deleted files update the project file manifest.
* **Isolation:** Retrieval is scoped to the active project.
* **PDF extraction:** PDF content is converted to text before indexing.

## 3. Context Injection (CIN)

CIN is a lightweight way to provide immediate high-priority context.

* **Supported formats:** `.txt`, `.md`, `.pdf`
* **Recommended size:** Keep CIN files small and focused.
* **Best for:** Character sheets, plot outlines, style guides, and short summaries.

## 4. Retrieval-Augmented Generation (RAG)

RAG is used for larger bodies of project knowledge.

* **Supported formats:** `.txt`, `.md`, `.pdf`
* **Soft limit:** Files larger than 500 KB may trigger a warning.
* **Hard limit:** The indexer supports files up to 50 MB.
* **Processing:** Documents are split into overlapping chunks for retrieval.

## 5. Reviewed Change Sets

AI-assisted file changes are limited to text-first project files.

* **Supported edit targets:** `.txt`, `.md`
* **Path rules:** Proposed changes must stay inside the active project root.
* **Safety:** Writes use staged files, backups, rollback, and stale-content checks.

> [!NOTE]
> SammyAI is in alpha. The current focus is reliable support for `.txt`, `.md`, and `.pdf` context, with `.txt` and `.md` as the safest editable formats.
