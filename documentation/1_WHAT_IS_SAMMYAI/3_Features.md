# SammyAI Features

SammyAI provides a project-based writing workspace with AI chat, context retrieval, persistent memory, reviewed edits, and configurable model access. The goal is to help you create with better continuity while keeping you in control of what changes.

---

## Projects and Project Explorer

A SammyAI project is a normal folder containing your writing files. SammyAI registers that folder in a local SQLite database and stores runtime data in OS-managed application directories.

* **Project Explorer:** Browse the active project's files and folders in a collapsible dock.
* **Live filesystem tree:** Expand folders and double-click files to open them.
* **Recent projects:** Reopen previous projects from the File menu.
* **Startup restore:** SammyAI can restore the active project state when the application starts.
* **No hidden project files:** SammyAI keeps app metadata outside your writing folder.

---

## Agent Workflows

SammyAI now supports multiple writing agents. Each agent uses provider-neutral prompt layering so the workflow is not tied to a single model vendor.

* **Assistant:** General help, discussion, and read-only project guidance.
* **Brainstormer:** Idea generation, alternatives, story structure, and creative exploration.
* **Writer:** Draft generation with evaluator and revision workflow support.
* **Editor:** Revision proposals through reviewed change sets.
* **Critic:** Read-only critique and feedback.

The selected agent is persisted per chat session.

---

## Project Context and RAG

The context engine helps SammyAI retrieve relevant project material without pasting large files into every prompt.

* **Automatic synchronization:** Supported project files are scanned in the background when projects open or files are saved.
* **Supported retrieval formats:** `.md`, `.txt`, and `.pdf`.
* **Project isolation:** Retrieval is scoped to the active project ID.
* **Content hashes:** Changed, new, and deleted files update the project manifest.
* **Explicit file references:** Use file references when a specific file must be included.
* **Ambiguity handling:** If two files share the same name, use a relative path.
* **Context budget:** Explicit files, context injection, RAG, and memory share a bounded context budget.

Legacy manual indexing remains available under **Advanced > Legacy Manual Indexing** while the new context engine is tested.

---

## Context Injection

Context Injection provides high-priority reference material for the next prompt cycle. It is best for short, precise files such as character sheets, style notes, chapter summaries, and world rules.

* **Best for:** Small reference files that must be followed closely.
* **Supported formats:** `.txt`, `.md`, and `.pdf`.
* **Trade-off:** CIN gives direct focus, but large files can crowd the context budget.

---

## Persistent Memory

Persistent Memory stores approved project facts that should remain useful across sessions.

* **Categories:** Character, plot, world, style, decision, preference, and general.
* **Provenance:** Memories can be linked to users, files, chats, agents, and summaries.
* **States:** Memories can be active or archived.
* **Review flow:** Conversation summaries and memory suggestions require approval.
* **Usage:** Active memories are injected before semantic retrieval when relevant.

Access memory tools through **Advanced > Persistent Memory**.

---

## Reviewed Change Sets and Diff Review

SammyAI can propose structured file changes without immediately writing them to disk.

* **Change types:** Create, update, delete, and character-range edits.
* **Path safety:** Edits are confined to supported files inside the active project root.
* **Conflict checks:** Hash-based stale-content detection helps prevent overwriting newer changes.
* **Atomic writes:** Staged writes, backups, and rollback reduce partial-update risk.
* **Undo and redo:** Reviewed edits preserve editor undo history where possible.
* **Diff review:** Multi-file proposals can be reviewed before acceptance.

Diff tools are available under **Edit > Compare and Review**.

---

## LLM Setup Panel

The LLM Setup panel lets you configure a custom set of models.

* **Dynamic management:** Add, edit, and remove model entries.
* **Provider support:** Configure local Ollama models and supported cloud providers.
* **Model slots:** Configure up to 15 models across available providers.
* **Workflow fit:** Keep fast local models for private drafting and cloud models for complex reasoning or polishing.

---

## LLM Settings Panel

The LLM Settings panel controls sampling behavior for subsequent model responses.

* **Temperature:** Adjust creativity and randomness.
* **Top-P:** Control nucleus sampling.
* **Seed:** Set a seed where supported for more reproducible outputs.
* **Presets:** Use Exploratory, Balanced, and Focused settings for common writing stages.

---

## Multi-model Chat

SammyAI lets you switch configured models during a chat session.

* **Compare strengths:** Try a local model and a cloud model on the same scene problem.
* **Task optimization:** Use different models for brainstorming, drafting, critique, and polishing.
* **Session continuity:** The current session context follows the conversation unless you start a new chat.

---

## Quick Reference

| Your Goal | Recommended Tool |
| :--- | :--- |
| Start or organize a writing folder | Project Explorer |
| Generate ideas | Brainstormer agent |
| Draft a scene | Writer agent |
| Critique a draft | Critic agent |
| Revise project files safely | Editor agent with reviewed change sets |
| Reference a specific file | Explicit file reference |
| Reference short high-priority notes | CIN |
| Reference large project knowledge | Project Context or RAG |
| Preserve important facts across sessions | Persistent Memory |
