# Context Injection and Attached References

Context Injection (CIN) is used for high-priority reference material that should guide the current conversation. In the V0.4.1-alpha UI, the chat composer exposes this as an attachment control, and the Advanced menu exposes commands to attach or remove a reference.

---

## 1. CIN vs. Project Context

| Feature | Best For | Retrieval Method |
| :--- | :--- | :--- |
| **Attached Reference or CIN** | Short, high-priority files | Direct prompt context |
| **Project Context or RAG** | Larger project knowledge | Semantic retrieval |
| **Persistent Memory** | Durable project facts | Approved memory injection |

## 2. Attach Reference

Use **Attach Reference...** when a specific external file should guide the next prompt.

* **Supported formats:** `.txt`, `.md`, and `.pdf`.
* **Best size:** Small and focused files work best.
* **Best examples:** Character profile, style note, chapter summary, rules sheet, or outline.
* **Prompt budget:** Attached references share the same budget as explicit files, memory, and RAG results.

## 3. Remove Attached Reference

Use **Remove Attached Reference** when the current temporary reference is no longer relevant.

Removing the reference prevents old material from influencing later messages and frees more context budget for the next task.

## 4. When to Use Persistent Memory Instead

If a fact should remain useful across sessions, store it as project memory instead of repeatedly attaching the same note. Use **Advanced > Persistent Memory** to manage durable memories and conversation summaries.

> [!TIP]
> Use attached references for short-term focus. Use persistent memory for facts that should keep mattering later.
