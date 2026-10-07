# v0.6.1-alpha — Chat and agent diagnostics

Development branch: `codex/chat-agent-diagnostics`. Manual Windows acceptance
and release tagging are pending. Python package version: `0.6.1a0`.

- Persistent request timelines connect context, model calls, proposal validation,
  review decisions, file application and undo/redo across app restarts.
- Chat and project identity travel with asynchronous progress, errors and results.
  Missing files, partial context, failed retrieval and empty retrieval are distinct.
- Incomplete change envelopes are rejected explicitly. Empty or provider-reported
  truncated stages cannot produce file changes. Successful model calls no longer
  imply successful edits in the displayed request outcome.
- Optional prompt, response, Writer draft and failed-proposal capture uses bounded
  local storage, credential redaction and explicit uncaptured/truncated indicators.
- A timeline viewer adds editable export previews, content excluded by default,
  retention settings and diagnostic deletion.
- Additive SQLite migration 5 preserves existing project/memory data and chat JSON.
  Interrupted work is recorded without resuming reviews or replaying file writes.

See [the user guide](documentation/3_USER_GUIDE/9_Chat_Agent_Diagnostics.md) and
[acceptance record](documentation/7_NEXT_STEPS/9_Chat_Agent_Diagnostics.md).

## Upgrade and rollback

Back up the application data directory before an upgrade. Migration 5 creates
diagnostic tables and leaves existing chat/project tables intact. Older binaries
reject newer schema versions; reverting application code alone does not downgrade
the database. Restore the pre-upgrade database backup to return to an older
release. Preserve any new chats and project files separately before rollback.

## Limits

Provider metadata depends on what the configured SDK returns. Prompts and outputs
cannot be recovered when capture was disabled. Metadata and captured writing may
contain private names and paths; review and redact an export before sharing.
Diagnostics do not restore reviews or undo stacks after restart, repair proposals,
or add write authority. Clean packaged Windows manual acceptance remains pending.
