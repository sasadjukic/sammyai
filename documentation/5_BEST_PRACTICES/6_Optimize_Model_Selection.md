# Optimizing Model Selection

SammyAI can use both local and cloud models in one workflow. The best model depends on privacy needs, hardware, cost, context size, and task difficulty.

---

## Local Models

Local models run through Ollama on your own machine.

**Strengths:**

* Private by default.
* No per-request cloud cost.
* Good for rough brainstorming and early drafting.

**Limitations:**

* Performance depends on your hardware.
* Smaller models can struggle with long context and complex edits.

---

## Cloud Models

Cloud models run on provider infrastructure and use your API key.

**Strengths:**

* Stronger reasoning for many complex tasks.
* Better final polish in many workflows.
* Often larger context windows.

**Limitations:**

* Prompt content is sent to the provider.
* Provider costs, quotas, and rate limits apply.
* Model availability and IDs can change.

---

## Task-to-Model Mapping

| Task | Recommended Type |
| :--- | :--- |
| Private brainstorming | Local |
| Fast rough drafting | Local |
| Sensitive project material | Local where possible |
| Deep critique | Cloud |
| Final prose polish | Cloud |
| Large context tasks | Model with a larger context window |

---

## Practical Hybrid Workflow

Use a local model for early exploration, then switch to a stronger model for critique, final polish, or difficult reasoning. Keep the same project context and memories available, but be aware that cloud requests send prompt content to the selected provider.

> [!TIP]
> If a local model loses track of a long scene, narrow the context first. If the task is still too complex, switch to a stronger configured model.
