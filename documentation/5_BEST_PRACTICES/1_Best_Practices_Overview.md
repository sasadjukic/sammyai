# Best Practices Overview

Creating a strong story with SammyAI is a collaborative process. SammyAI can generate, critique, revise, retrieve context, and remember approved project facts, but your judgment remains the final authority.

---

## The Core Philosophy

SammyAI is a writing partner, not a magic button. It works best when you provide clear goals, useful context, and careful review.

> [!NOTE]
> SammyAI can speed up drafting and revision, but your creative direction is what turns raw output into a finished story.

---

## Be Precise

The more specific your prompt is, the more useful the response becomes.

* **Define your style:** Do not just ask for a scene. Name the tone, genre, pace, and emotional target.
* **State the purpose:** Explain whether you want brainstorming, drafting, critique, or editing.
* **Provide constraints:** Mention point of view, tense, word count, character goals, and facts that must not change.
* **Avoid vague praise requests:** Ask for concrete improvements instead of asking whether something is good.

---

## Use the Right Context Tool

| Need | Best Tool |
| :--- | :--- |
| A specific file must guide the answer | Explicit file reference |
| A short reference should be active now | Attached Reference or CIN |
| Large project knowledge is needed | Project Context or RAG |
| A durable fact should keep mattering | Persistent Memory |
| A file should be changed safely | Editor agent with reviewed change set |

---

## Review AI Work

Always review generated content before treating it as final.

* Use the Critic agent for read-only feedback.
* Use the Editor agent for proposed file changes.
* Review change-set diffs before applying them.
* Use undo or redo for applied change sets when needed.
* Keep important approved facts in persistent memory instead of relying on a long chat.

---

## Golden Rules

| Best Practice | Why it Matters | Result |
| :--- | :--- | :--- |
| Be specific | Reduces generic output | Better prose and fewer wrong turns |
| Use project context | Gives SammyAI relevant material | Better continuity |
| Start fresh chats | Reduces context clutter | Cleaner responses |
| Save durable facts | Keeps key details available | Stronger long-term consistency |
| Review edits | Prevents unwanted file changes | Safer revision |

---

## Next Steps

Read the guides for Projects, LLM Chat, Project Context, Attached References, and Diff Review to understand how the V0.4.1-alpha workflow fits together.
