# Frequently Asked Questions

## 1. Technical Prerequisites and Setup

### What are the system requirements for running SammyAI?

Requirements depend heavily on whether you use local or cloud models.

* **RAM:** 16 GB is recommended for comfortable use with retrieval and background tasks.
* **GPU:** A modern GPU with enough VRAM is recommended for local models.
* **CPU:** A modern multi-core CPU is recommended.
* **Python:** Source installs require Python 3.11-3.14.

Cloud models reduce local model requirements, but the desktop app and retrieval features still need enough memory and disk space.

### Do I need Ollama?

You need Ollama only if you want to run local models. Cloud-only workflows can use configured provider API keys instead.

### Where does SammyAI store project data?

Your writing files stay in your project folder. SammyAI stores project registration, settings, application state, runtime data, and caches in OS-managed application data directories. It does not add hidden metadata files to your project folder.

## 2. Projects and Context

### What is a SammyAI project?

A project is a normal folder that contains your writing files. SammyAI registers the folder, shows it in the Project Explorer, and can synchronize supported files for project context.

### Which files can SammyAI use for context?

Project context supports `.txt`, `.md`, and `.pdf`. Safe AI file edits target `.txt` and `.md`.

### Do I still need to manually index files?

Usually, no. V0.4.1-alpha adds automatic project synchronization for supported files. Legacy manual indexing remains under **Advanced > Legacy Manual Indexing** for fallback use.

### What is the difference between project context, CIN, and memory?

* **Project Context or RAG:** Retrieves relevant chunks from project files.
* **Attached Reference or CIN:** Adds a short high-priority reference to the current conversation.
* **Persistent Memory:** Stores approved project facts and summaries for future sessions.

## 3. Chat and Agents

### What does New Chat do?

New Chat starts a fresh session context. Use it when changing tasks, moving to a new writing stage, or cleaning up a long conversation.

### Which agent should I choose?

* **Assistant:** General help and read-only discussion.
* **Brainstormer:** Ideas and alternatives.
* **Writer:** Drafting and revision workflow.
* **Editor:** Reviewed file-change proposals.
* **Critic:** Read-only feedback.

### Can SammyAI edit my files automatically?

The Editor agent can propose file changes, but changes are reviewed as change sets before they are applied. Existing files require explicit file context before modification.

## 4. Creative Capabilities and Content

### What is the default language for SammyAI?

SammyAI is currently optimized for US English for both conversation and narrative output.

### Will SammyAI support languages other than US English?

Expanded language support is a long-term goal. It requires testing with native speakers and different model families.

### Does SammyAI permit fictional crime, violence, or mature themes?

SammyAI is designed for creative writing across many genres, including mature fictional themes. You remain responsible for how you use model output and for provider policy compliance.

### Can SammyAI be used for non-fiction or professional content?

Yes, but it is primarily designed for creative writing. For factual or professional material, verify claims independently.

### Can SammyAI write poetry or songs?

SammyAI can help with rhythmic or poetic text, but it is not currently specialized for professional songwriting or poetry workflows.

## 5. Editor Features

### Why does the editor avoid rich formatting?

SammyAI focuses on text-first writing and LLM workflows. Plain text and Markdown are easier to retrieve, diff, review, and edit safely.

### Will SammyAI support formats like `.odt` or `.docx`?

Additional import or export support may be evaluated later. For now, `.txt` and `.md` are the safest editable formats, and `.pdf` is supported for context extraction.
