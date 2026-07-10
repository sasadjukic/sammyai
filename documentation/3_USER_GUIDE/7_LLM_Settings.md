# LLM Settings and Presets

The LLM Settings panel controls how the selected model responds in future messages. These settings are useful for moving between brainstorming, drafting, critique, and polishing.

---

![SammyAI LLM Setup](pictures/SammyAI_llm_settings_panel.png)

---

## 1. Creative Presets

* **Exploratory:** Higher randomness for brainstorming, world-building, and unusual story directions.
* **Balanced:** A middle setting for normal drafting and dialogue.
* **Focused:** Lower randomness for instruction following, factual consistency, and style adherence.

## 2. Core Parameters

### Temperature

Temperature controls randomness.

* **Lower values:** More predictable and conservative.
* **Higher values:** More varied and surprising.

### Top-P

Top-P controls nucleus sampling by limiting the model to a subset of likely next tokens.

* **Lower values:** More constrained wording.
* **Higher values:** More variety.

### Seed

Seed can make outputs more reproducible when the selected provider and model support seeded generation.

* Use a seed when comparing small prompt changes.
* Do not expect perfect reproducibility across different models or providers.

## 3. Applying Changes

1. Open **Settings** from the sidebar.
2. Choose a preset or adjust values manually.
3. Apply the settings.

Changes affect subsequent AI interactions.

> [!TIP]
> Use Focused settings with attached references, explicit file context, or persistent memory when consistency matters more than surprise.
