# API Key Configuration

SammyAI supports both local and cloud-based Large Language Models (LLMs). While local models (like Gemma) run entirely on your machine, cloud-based models (like Gemini, Kimi and Deepseek) require **API Keys** for authentication and high-performance access.

![SammyAI API Keys Window](pictures/SammyAI_v1_API_Keys_Window.png)

---

## 1. Why Use Cloud Models?
SammyAI integrates cloud models to provide:
*   **High Performance**: Cloud models perform much better in writing sessions, especially if you need longer output.
*   **Enhanced Reasoning**: Access to massive models with deep understanding of complex literary structures.

## 2. Setting Up Your Keys
You can configure your keys by clicking the **Key** icon in the vertical sidebar toolbar.

1.  **Select Provider**: SammyAI currently supports:
    *   **Google API Key**: Required for the Gemini family of models.
    *   **Ollama Cloud API Key**: Required for Kimi and Deepseek cloud-integrated models.
2.  **Paste Key**: Enter your key into the respective field. For security, characters are masked during input.
3.  **Toggle Visibility**: Click the **eye (👁)** icon to verify your key if needed.
4.  **Save & Refresh**: Click **Save**. SammyAI will instantly refresh the LLM client, enabling the selected cloud models for use in the chat panel.

## 3. Security & Privacy
SammyAI is designed with a "Privacy First" philosophy:
*   **Local Storage**: Your API keys are stored securely on your local machine using standard system encryption services.
*   **Direct-to-Provider**: Keys are only sent to the model provider (Google or Ollama) during the active chat process and are never shared with or stored by SammyAI's developers.
*   **Easy Removal**: Use the **Clear** button in the configuration dialog to wipe all stored keys from your machine at any time.

---

> [!NOTE]
> Ensure your API keys have the necessary permissions on the provider's platform to avoid "Authentication Error" messages in the chat panel.
