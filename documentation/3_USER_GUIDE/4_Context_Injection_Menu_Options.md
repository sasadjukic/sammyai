# Context Injection Menu (CIN) Options

Context Injection (CIN) is a specialized feature designed for providing SammyAI with high-priority, immediate reference material. unlike project-wide indexing, CIN places your selected content directly into the conversation "spotlight" for the most accurate and attentive AI interaction.

---

## 1. CIN vs. RAG: Choosing the Right Tool
While both features provide context, they serve different purposes in your creative workflow:

| Feature | Best For | Typical Size | Retrieval Method |
| :--- | :--- | :--- | :--- |
| **CIN** | High-priority references (Style guides, profiles) | < 50kB | Direct Injection (High Focus) |
| **RAG** | Project-wide knowledge (Lore, full drafts) | > 50kB | Semantic Search (Deep Memory) |

## 2. Upload File for CIN
This option allows you to select a specific document to be treated as a "primary reference" for the current dialogue.

*   **Supported Formats**: SammyAI supports native text extraction for `.txt`, `.md`, and `.pdf` files.
*   **50kB Limit**: To maintain optimal AI reasoning speed and focus, CIN is strictly limited to files smaller than **50kB**. For larger documents, please use the **RAG Menu** for indexing.
*   **Direct Injection**: Once uploaded, the content is "injected" into the prompt context for the very next message you send. This ensures the AI has the reference material "fresh in mind."

## 3. Clear CIN Context
This command resets the temporary context provided via CIN.

*   **When to Use**: Essential when you've finished working with a specific reference file and want the assistant to return to its standard operational context.
*   **Immediate Effect**: Clearing the context removes the injected data from the next conversation cycle, preventing old references from cluttering new creative directions.

---

> [!TIP]
> Use CIN during world-building to keep a "Character Profile" or "World Fact Sheet" constantly active in the AI's mind while you brainstorm new chapters.
