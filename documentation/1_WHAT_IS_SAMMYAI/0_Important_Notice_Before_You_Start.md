## **Welcome to SammyAI v0.4.2-alpha!**

SammyAI v0.4.2-alpha is the current development release. It builds on SammyAI's project-based writing architecture, safer AI-assisted editing, automatic context, persistent memory, and redesigned chat workflow with additional usability and project-management refinements.

**Current Status:**

* **Version:** SammyAI v0.4.2-alpha
* **Development Stage:** Alpha
* **Projects:** SammyAI now works around normal project folders, a live Project Explorer, recent projects, project settings, and OS-managed application data.
* **Context Engine:** Project files can be synchronized automatically for retrieval, while explicit file references, Context Injection, RAG, and memory share a bounded prompt budget.
* **Editing Safety:** AI file changes are reviewed as structured change sets with diff review, path confinement, atomic writes, stale-content checks, rollback, and undo support.
* **Agents:** Assistant, Brainstormer, Writer, Editor, and Critic workflows are available through provider-neutral prompt layering.
* **Memory:** Project-scoped persistent memories and conversation summaries are available with user approval.
* **User Interface:** The chat composer, message layout, project explorer, advanced menus, and dark styling have been redesigned.

**Highlights of the Current v0.4.2-alpha Experience:**

* **Project Explorer:** Open a project folder, browse the live file tree, and open files directly from the workspace.
* **Automatic Project Context:** Supported project files are synchronized in the background when projects are opened or files are saved.
* **Explicit File Context:** Use file references when you need SammyAI to work from a specific file. Ambiguous filenames require a relative path.
* **Reviewed Change Sets:** AI editing proposals are shown for review before they touch your project files.
* **Persistent Memory:** Save important characters, plot facts, world details, style choices, decisions, and preferences as project memories after review.
* **New Chat Workflow:** Start a fresh chat session without losing the previous session's saved state.
* **Project File Actions:** Copy, paste, rename, and delete files from the Project Explorer with safeguards for unsaved documents and protected project metadata.
* **Missing Project Recovery:** Reconnect a moved project folder or safely remove its SammyAI-managed registration and runtime data.
* **Interface Refinements:** Use clearer search highlights, project-aware welcome messages, and an animated activity indicator while an agent is working.

**Important Notes:**

* This is an Alpha version intended for early adopters. Core features are functional, but expect continued refinement.
* Persistent memory and conversation summaries require approval. SammyAI should not silently write long-term memories.
* Legacy RAG and diff controls remain under **Advanced** while the new agent and context workflows are tested.
* Please report bugs, confusing workflows, and documentation gaps while this release stabilizes.
