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
- Complete envelopes containing malformed JSON now report the JSON error and
  its location, including incorrect closing brackets or stray escaped newlines.
  Agent instructions clarify JSON escaping and closing structure. Restored chats
  show one rejection notice while retaining technical exceptions in diagnostics.
- A missing final file-object brace can be recovered with one character insertion
  when the rest of the JSON and envelope are complete. Content stays unchanged;
  normal validation and diff approval still apply. Recovery is visible in chat
  and diagnostics, with original output governed by failed-proposal capture.
- Optional prompt, response, Writer draft and failed-proposal capture uses bounded
  local storage, credential redaction and explicit uncaptured/truncated indicators.
- A timeline viewer adds editable export previews, content excluded by default,
  retention settings and diagnostic deletion.
- Additive SQLite migration 5 preserves existing project/memory data and chat JSON.
  Interrupted work is recorded without resuming reviews or replaying file writes.
- Agents can now propose several exact passage replacements within one file.
  All matches use the original supplied source and pass through normal diff review.
- File text uses a plain-text proposal format, avoiding JSON escaping for quotes,
  backslashes and newlines in replacements and full rewrites. Legacy JSON remains
  accepted. See [agent file editing](documentation/3_USER_GUIDE/10_Agent_File_Editing.md).

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
Diagnostics do not restore reviews or undo stacks after restart or add write
authority. Proposal recovery is limited to the single missing-brace case above;
other malformed output still requires regeneration. Clean packaged Windows
manual acceptance remains pending.
