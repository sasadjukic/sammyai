# v0.5.2-alpha — US English spell check

Status: implementation on `codex/us-english-spell-check`; Windows manual acceptance and merge are have been accepted. No release tag has been created.

## Changes

- Offline US English spelling in every editor tab and the chat composer.
- Ranked suggestions, undoable occurrence replacement, Ignore Once, Ignore All,
  and a persistent global personal dictionary.
- A Settings dialog with Writing preferences and access to existing LLM settings.
  The spelling toggle defaults to on and persists across restarts.
- Shared decoration layers preserve search highlights alongside spelling underlines.
- Debounced, cancellable workers, cached block tokenization and word lookups,
  stale-result rejection, and viewport-only underline rendering.
- Spylls 0.1.7 and its bundled SCOWL US dictionary, with packaged license notices.

## Scope and design

This release adds spelling and a small application settings entry point. Grammar
checking, automatic correction, other languages, project dictionaries, and a full
settings redesign are outside its scope. Future settings can be grouped into
Writing, Models, Appearance, and Projects when each has enough controls. Keep
application preferences separate from model presets and project metadata.

## Acceptance

See `documentation/7_NEXT_STEPS/4_Spell_Check_Acceptance.md`. Version metadata is `0.5.2a0`.
