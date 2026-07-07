# Common Installation and Setup Issues

This document lists common problems during installation, first launch, model setup, and project-context initialization.

## Hardware and System Requirements

### Local Model Performance

Local models run on your own hardware through Ollama.

* **Symptoms:** Slow token generation, model load failures, out-of-memory errors, or Ollama crashes.
* **What to try:** Use a smaller model, close other memory-heavy applications, or switch to a cloud model for complex tasks.

### RAM and Storage

* **Disk space:** Local model weights, project context indexes, caches, and dependencies can use significant disk space.
* **System RAM:** 16 GB is recommended for comfortable use with retrieval, background sync, and desktop UI.

## Dependency Management

### Python Environment

* **Python version:** SammyAI requires Python 3.11-3.14.
* **Virtual environment:** Use a dedicated virtual environment to avoid dependency conflicts.
* **Editable install:** Run `python -m pip install -e .` from the repository root.
* **Tests:** Install test dependencies with `python -m pip install -e ".[test]"`.

### Docker Environment

* **GUI display:** Docker GUI setup depends on your operating system and display server.
* **GPU passthrough:** Local model acceleration inside Docker may require additional GPU container setup.
* **Ollama access:** If Ollama runs on the host, the container must be able to reach the host service.

## Model Configuration

### Local Models

* **Missing model weights:** Pull the local model with Ollama before selecting it in SammyAI.
* **Wrong model name:** Use the exact model name shown by Ollama.
* **Ollama not running:** Start Ollama before using local models.

### Cloud Provider API Keys

* **Missing key:** Add the provider API key in the LLM Setup panel.
* **Invalid key:** Check the provider dashboard and regenerate the key if needed.
* **Quota or rate limits:** Provider errors such as too many requests usually mean the provider limit has been reached.

## Project Context and Database Initialization

### Project System Not Initialized

If SammyAI reports that the project system is not initialized:

* Confirm the app can write to its OS-managed application-data directory.
* Check whether another SammyAI process is holding the database open.
* Restart the app and reopen the project.

### Context Sync Does Not Run

* Confirm a project is open.
* Confirm files use supported context formats: `.txt`, `.md`, or `.pdf`.
* Use **Advanced > Project Context > Rebuild Active Project Index...** to force a rebuild.
* Use **Advanced > Project Context > Context Index Statistics...** to inspect index state.

### Legacy Manual Indexing

Manual indexing is no longer the normal first step for project files. Use **Advanced > Legacy Manual Indexing** only as a fallback or for external files outside the project.
