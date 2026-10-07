## **Welcome to SammyAI v0.6.0-alpha!**

SammyAI v0.6.0-alpha is the current development release. It adds inline diff review in the affected document tabs, with controls to accept or reject individual changes before applying them. Multi-file editing, chat history, and offline US English spell checking remain available.

**Current Status:**

* **Version:** SammyAI v0.6.0-alpha
* **Development Stage:** Alpha
* **Projects:** SammyAI now works around normal project folders, a live Project Explorer, recent projects, project settings, and OS-managed application data.
* **Context Engine:** Project files can be synchronized automatically for retrieval, while explicit file references, Context Injection, RAG, and memory share a bounded prompt budget.
* **Editing Safety:** AI file changes are reviewed as structured change sets with diff review, path confinement, atomic writes, stale-content checks, rollback, and undo support.
* **Agents:** Assistant, Brainstormer, Writer, Editor, and Critic workflows are available through provider-neutral prompt layering.
* **Memory:** Project-scoped persistent memories and conversation summaries are available with user approval.
* **User Interface:** The editor supports multiple independent document tabs, while the chat composer, message layout, Project Explorer, advanced menus, and dark styling share the same workspace.

**Highlights of the Current v0.6.0-alpha Experience:**

* **US English Spell Check:** Get spelling feedback and undoable corrections in every tab and the composer. Enable or disable checking under **Settings > Writing**.
* **Chat History:** Browse and reopen saved conversations, start new chats, rename or delete conversations, and filter by current project, all conversations, or unassigned chats.
* **Multi-File Editing:** Keep multiple Markdown and text documents open, switch between independent tabs, and restore project tabs after restarting.
* **Unsaved-Change Protection:** Dirty tabs prompt before closing or quitting, and dirty background tabs cannot be overwritten by conflicting AI changes.
* **Project Explorer:** Open a project folder, browse the live file tree, and open files directly from the workspace.
* **Automatic Project Context:** Supported project files are synchronized in the background when projects are opened or files are saved.
* **Explicit File Context:** Use file references when you need SammyAI to work from a specific file. Ambiguous filenames require a relative path.
* **Inline Diff Review:** Inspect AI editing proposals in the affected document tabs, accept or reject individual changes, and apply the accepted result with conflict checks and undo support.
* **Persistent Memory:** Save important characters, plot facts, world details, style choices, decisions, and preferences as project memories after review.
* **New Chat Workflow:** Start a fresh chat session without losing the previous session's saved state.
* **Project File Actions:** Copy, paste, rename, and delete files from the Project Explorer with safeguards for unsaved documents and protected project metadata.
* **Missing Project Recovery:** Reconnect a moved project folder or safely remove its SammyAI-managed registration and runtime data.
* **Interface Refinements:** Use clearer search highlights, project-aware welcome messages, and an animated activity indicator while an agent is working.

**Important Notes:**

* This is an Alpha version intended for early adopters. Core features are functional, but expect continued refinement.
* Persistent memory and conversation summaries require approval. SammyAI should not silently write long-term memories.
* Legacy manual indexing and DBE controls have been retired. Use **Advanced > Project Context** for project indexing and agent proposals with inline review for AI file edits.
* Please report bugs, confusing workflows, and documentation gaps while this release stabilizes.
