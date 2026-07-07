# AI Models Overview

SammyAI uses a dynamic model configuration system. Instead of relying on a fixed built-in model list, you can configure local and cloud model entries in the LLM Setup panel and choose the model that fits the task.

---

## 1. Local Models

Local models run through Ollama on your own hardware.

**Strengths:**

* Private by default because prompts stay on your machine.
* No per-request cloud cost.
* Useful for brainstorming, early drafting, and quick experiments.

**Trade-offs:**

* Quality and speed depend on your CPU, GPU, VRAM, and RAM.
* Smaller local models may struggle with long context, complex reasoning, or highly polished prose.

## 2. Cloud Models

Cloud models are hosted by external providers and accessed with your API key.

**Strengths:**

* Stronger reasoning and prose quality for many complex tasks.
* Larger context windows depending on provider and model.
* Useful for final polish, deep critique, complex restructuring, and long-range continuity.

**Trade-offs:**

* Prompt content is sent to the provider.
* Provider usage may have cost, quota, or rate limits.
* Availability and model IDs can change outside SammyAI.

## 3. Dynamic Configuration

In the LLM Setup panel, you can:

* Add local Ollama models.
* Add supported cloud provider models.
* Store up to 15 configured model entries.
* Edit or remove model entries without changing application code.
* Switch models from the chat workflow.

## 4. Choosing a Model

| Task | Good Starting Point |
| :--- | :--- |
| Private brainstorming | Local model |
| Fast rough drafting | Local model |
| Deep critique | Cloud model |
| Final prose polish | Cloud model |
| Sensitive project material | Local model where possible |
| Long project context | Model with a larger context window |

> [!TIP]
> Keep a small set of trusted models configured. A practical setup is one fast local model, one stronger local model if your hardware can run it, and one or two cloud models for difficult work.
