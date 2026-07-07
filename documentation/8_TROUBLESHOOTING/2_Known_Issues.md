# Known Issues

This document tracks known limitations, model tendencies, and workflow risks in SammyAI V0.4.1-alpha.

## LLM Behavior and Style

### Repeated Names and Tropes

Some models repeatedly suggest similar character names, settings, or tropes when prompts are vague.

**What to try:** Provide a time period, region, genre, naming rules, or examples of names to avoid.

### Numeric and Symbolic Formatting

Models may prefer numerals or symbols when prose would read better with words.

**What to try:** Add style instructions such as "spell out small numbers" or "write symbols as words unless technical notation is required."

### Cross-Language Artifacts

In long sessions or large-context prompts, models may occasionally include non-English text or unexpected characters.

**What to try:** Start a New Chat, narrow the context, and restate the language requirement.

## Context and Memory

### Context Budget Pressure

Explicit files, attached references, project retrieval, memories, summaries, and conversation history share a bounded prompt budget.

**What to try:** Reference fewer files, attach shorter summaries, or save stable facts as persistent memory.

### Stale Retrieval

Project context should update automatically, but external file changes or failed background tasks can leave retrieval stale.

**What to try:** Use **Advanced > Project Context > Rebuild Active Project Index...**.

### Memory Quality

Persistent memory is only useful when saved facts are concise and durable.

**What to try:** Review suggested memories carefully, archive outdated facts, and avoid storing temporary brainstorming as durable memory.

## Editing and Change Sets

### Edit Conflicts

If a file changes after a change set is prepared, SammyAI may reject the apply step to prevent overwriting newer content.

**What to try:** Reopen or refresh the file context, then ask the Editor agent to prepare a new change set.

### Unsupported Edit Targets

Safe AI file edits are focused on `.txt` and `.md`.

**What to try:** Convert rich documents to Markdown or plain text before asking SammyAI to edit them.

## External Services

### Authentication Errors

Cloud providers return authentication errors when API keys are missing, expired, invalid, or not permitted to use the selected model.

### Connectivity and Load

Provider outages, local network problems, or high provider load can interrupt requests.

### Rate Limits

Free or low-tier accounts can hit quota limits quickly. Switch models, wait for reset, or adjust provider plan if needed.
