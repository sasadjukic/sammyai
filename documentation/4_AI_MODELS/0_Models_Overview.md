# 🧠 AI Models Overview

With the release of Alpha 0.3.1, SammyAI has moved away from a fixed list of models. Instead, we now provide a **Dynamic LLM System** that gives you the freedom to choose, test, and integrate any model from our supported providers.

This flexibility ensures that as the AI landscape evolves, your creative toolkit remains state-of-the-art.

---

## 1. Local Models (Ollama)

Running models locally offers the ultimate in privacy and offline availability. The performance of these models is directly tied to your computer's hardware (specifically your GPU/VRAM).

### Recommendations
*   **For Lightweight Drafting**: `gemma4:e4b` — Fast, efficient, and perfect for quick brainstorming sessions.
*   **For Deep Narrative**: `qwen3.6:27b` — Offers a higher degree of reasoning and prose quality for more complex scenes.
*   **Power Tip**: The more powerful your PC or server, the larger the models you can run. High-end systems can handle `70B+` parameter models, which rival cloud performance.

## 2. Cloud Model Providers

Cloud models are hosted on powerful remote servers and offer the highest levels of creative "intelligence," reasoning, and context handling.

| Provider | Latest Recommended Models | Strengths |
| :--- | :--- | :--- |
| **Google** | `gemini-3.1-pro`, `gemini-3.1-flash` | Massive context windows, deep logical reasoning, and world-building expertise. |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` | Exceptional instruction following and consistent narrative style. |
| **Anthropic** | `claude-3.5-sonnet`, `claude-3.5-opus` | Highly "human-like" prose and nuanced character dialogue. |
| **Ollama Cloud** | `deepseek-v4-pro`, `kimi-k2.6` | Powerful alternatives with unique creative styles and robust reasoning. |

## 3. Dynamic Configuration

You are no longer restricted to what we've chosen for you. In the **LLM Setup Panel**, you can:
*   **Mix and Match**: Keep a fast local model for drafting and a powerful cloud model for final polishing.
*   **Total Control**: Configure up to **15 different models** and switch between them instantly in the chat panel.
*   **Future Proof**: When a new model is released (e.g., "GPT-5" or "Gemini 4"), you can add it to SammyAI the same day by simply entering its model ID.

## 4. Privacy & API Access

To use cloud models, you simply provide your own API Key in the **LLM Setup Panel**.
*   **Direct Access**: SammyAI connects your machine directly to the provider.
*   **Cost Efficiency**: Many providers offer generous free tiers or "pay-as-you-go" pricing, making high-end AI highly accessible.

---

> [!TIP]
> **Start Local, Finish Cloud**
> Many writers find success using a local model for initial messy drafts to save on API costs, then switching to a "Pro" cloud model like `claude-3.5-sonnet` for the final character beats and dialogue refinement.
