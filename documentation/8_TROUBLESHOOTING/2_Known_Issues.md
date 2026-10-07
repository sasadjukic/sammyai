# Known Issues

This document tracks known limitations, model tendencies, and workflow risks in SammyAI v0.6.0-alpha.

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

If a file changes after its request context is captured, SammyAI rejects a stale
proposal. Files are checked again when a change set is applied.

**What to try:** Reopen or refresh the file context, then ask the Editor agent to prepare a new change set.

### Large-File Proposal Rejected

A partial reference can authorize additions, but cannot authorize replacing or
deleting the whole file. If the model returns a whole-file rewrite anyway, SammyAI
reports that partial context was supplied and rejects the proposal.

**What to try:** Ask explicitly to append only new material, or insert it before a
unique heading/complete line. Include the `@file` reference in the current request.
If an anchor is missing, ambiguous, or absent from context, name or quote a more
specific source line. If a numbered scene already exists, request a revision rather
than adding the same scene again. A new-text budget error concerns the size of the
addition, so split that writing request into smaller additions.

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
