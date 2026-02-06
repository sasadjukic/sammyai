# 🧠 Managing Context Windows

The context window is arguably the most significant constraint on current-generation Large Language Models (LLMs). Understanding how to manage this "short-term memory" is essential for keeping your story on track and ensuring SammyAI remains sharp and consistent throughout your project.

---

## 🗄️ What is a Context Window?

Think of the context window as the "active RAM" of the AI. It contains everything the model is currently considering to generate its next response.

**A typical context window consists of:**
1.  **System Prompt**: The core instructions for the AI.
2.  **Conversation History**: Your previous questions and the AI's answers.
3.  **Injected Data**: Anything you've served via **CIN** or **RAG**.
4.  **The Generation**: The actual response the model is currently writing.

> [!CAUTION]
> **Performance Degradation**
> As a context window fills up, the model's performance naturally degrades. It has more information to process, which increases the likelihood of "hallucinations," contradictions, or missed instructions.

---

## 📉 The "Lost in the Middle" Phenomenon

LLMs, much like humans, suffer from **Primacy Bias** and **Recency Bias**. They tend to pay the most attention to information at the very beginning and the very end of a conversation.

*   **Primacy**: The initial setup and core instructions.
*   **Recency**: The most recent 2-3 turns of conversation.

In long threads, the information in the "middle" often receives lower priority, causing the AI to forget plot points or character details that were discussed earlier in the session.

---

## 🛠️ Strategies for Success

### 1. Segment Your Projects
Don't try to build your entire world, all your characters, and write five chapters in a single chat. 

*   **Start a New Chat** for each major milestone (e.g., "Character Bio - Elias," "World Setup - The Mars Colony").
*   Once a segment is finalized, summarize the results and use **Context Injection (CIN)** to feed that summary into your next writing session.

### 2. The "Fresh Start" Rule
If your conversation feels like it's "skidding off the road"—if the AI starts repeating itself, ignoring your formatting, or losing its character voice—it’s time for a fresh start.

> [!TIP]
> **Hit the "Clear Chat" Button**
> Starting a new conversation clears the "clutter" from the AI's memory and allows it to focus entirely on your current goal.

---

## ✅ Checklist: Is it time for a New Chat?

If you answer **"Yes"** to any of the following, we recommend starting a new session:
- [ ] Has the conversation exceeded 10-15 turns?
- [ ] Is the AI starting to ignore established character traits?
- [ ] Have you moved from world-building to active drafting?
- [ ] Is the model becoming repetitive or overly verbose?
- [ ] Have you reached a major plot turning point?

---

## 🚀 Pro-Tip: Use Features to Save Space
Instead of re-pasting your story bible into the chat every time, use the **CIN** tab. This allows SammyAI to reference your foundational data efficiently without bloating the conversation history, keeping your context window free for active writing.
