# Managing Context Windows

The context window is the amount of information a model can consider when generating a response. SammyAI helps manage context through explicit files, attached references, project retrieval, and persistent memory, but the budget is still finite.

---

## What Counts as Context?

A typical request can include:

1. System and agent instructions.
2. Conversation history.
3. Explicit file references.
4. Attached references or CIN.
5. Project Context or RAG results.
6. Persistent memories and approved summaries.
7. Your new prompt.

All of these compete for space.

---

## Why Long Chats Drift

Long sessions can cause the model to miss older details, repeat itself, or over-focus on recent turns. Even with retrieval and memory, the best prompt is still focused.

---

## Strategies

### 1. Start New Chats for New Tasks

Use **New Chat** for a new chapter, character, editing pass, or major planning stage.

### 2. Save Durable Facts

When a decision should persist, save it as project memory instead of relying on an old chat turn.

### 3. Reference Specific Files

Use explicit file references for files that must be followed exactly. Use relative paths when filenames are ambiguous.

### 4. Keep Attachments Small

Attached references are best for short summaries, style guides, and profiles. Large files are better handled by project context.

### 5. Summarize Before Moving On

When a planning session produces useful decisions, summarize the chat and review suggested memory items.

---

## Checklist: Start a New Chat When

- [ ] The conversation has moved to a different task.
- [ ] The model starts repeating itself.
- [ ] Important instructions are being missed.
- [ ] You moved from planning to drafting.
- [ ] You moved from drafting to critique or editing.
- [ ] The chat contains decisions that should become persistent memory.

> [!TIP]
> Use persistent memory for stable facts, project context for source material, and New Chat for clean task boundaries.
