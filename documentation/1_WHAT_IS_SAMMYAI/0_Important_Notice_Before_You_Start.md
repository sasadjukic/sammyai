## **Welcome to the V0.4.1-alpha Release of SammyAI!**

SammyAI V0.4.1-alpha is a major alpha update focused on project-based writing, safer AI-assisted editing, automatic context, persistent memory, and a redesigned chat workflow.

**Current Status:**

* **Version:** SammyAI V0.4.1-alpha
* **Development Stage:** Alpha
* **Projects:** SammyAI now works around normal project folders, a live Project Explorer, recent projects, project settings, and OS-managed application data.
* **Context Engine:** Project files can be synchronized automatically for retrieval, while explicit file references, Context Injection, RAG, and memory share a bounded prompt budget.
* **Editing Safety:** AI file changes are reviewed as structured change sets with diff review, path confinement, atomic writes, stale-content checks, rollback, and undo support.
* **Agents:** Assistant, Brainstormer, Writer, Editor, and Critic workflows are available through provider-neutral prompt layering.
* **Memory:** Project-scoped persistent memories and conversation summaries are available with user approval.
* **User Interface:** The chat composer, message layout, project explorer, advanced menus, and dark styling have been redesigned.

**Key Highlights of V0.4.1-alpha:**

* **Project Explorer:** Open a project folder, browse the live file tree, and open files directly from the workspace.
* **Automatic Project Context:** Supported project files are synchronized in the background when projects are opened or files are saved.
* **Explicit File Context:** Use file references when you need SammyAI to work from a specific file. Ambiguous filenames require a relative path.
* **Reviewed Change Sets:** AI editing proposals are shown for review before they touch your project files.
* **Persistent Memory:** Save important characters, plot facts, world details, style choices, decisions, and preferences as project memories after review.
* **New Chat Workflow:** Start a fresh chat session without losing the previous session's saved state.

**Important Notes:**

* This is an Alpha version intended for early adopters. Core features are functional, but expect continued refinement.
* Persistent memory and conversation summaries require approval. SammyAI should not silently write long-term memories.
* Legacy RAG and diff controls remain under **Advanced** while the new agent and context workflows are tested.
* Please report bugs, confusing workflows, and documentation gaps while this release stabilizes.
