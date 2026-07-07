# LLM Setup and Configuration

The LLM Setup panel lets you configure the models that appear in SammyAI chat. You can mix local Ollama models with supported cloud provider models.

---

## 1. Dynamic Model Management

The LLM Setup panel gives you control over which models are available.

* **Model slots:** Configure up to 15 model entries.
* **Local models:** Add Ollama models running on your machine.
* **Cloud providers:** Add supported cloud provider models with your own API keys.
* **On-the-fly updates:** Add, edit, or delete entries without changing application code.

## 2. Add a Model

1. Open the **LLM Setup** panel from the sidebar.
2. Select the provider.
3. Enter the exact model name or provider model ID.
4. Enter an API key if the provider requires one.
5. Save the entry.

The model appears in the chat panel model selector.

## 3. Delete a Model

Select a configured model entry and delete it from the setup panel. This removes it from the chat selector but does not delete local Ollama model weights from your machine.

## 4. Why Mix Local and Cloud?

* **Local models:** Best for privacy, fast rough drafting, and no per-request cloud cost.
* **Cloud models:** Best for complex reasoning, critique, longer context, and final polish.

## 5. Security and Privacy

* API keys are stored locally.
* Keys are sent only to the provider needed for an active request.
* Prompt content is sent to cloud providers only when you choose a cloud model.
* Local models are the best option for sensitive project material.

> [!TIP]
> Keep the configured model list focused. A small set of trusted models is easier to choose from during active writing.
