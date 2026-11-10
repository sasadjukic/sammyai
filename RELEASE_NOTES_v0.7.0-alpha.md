# v0.7.0-alpha — Writer style profiles

Implementation branch: `codex/writer-style-profiles`. Python package version:
`0.7.0a0`. Maintainer writing tests passed with `gemma4:31b` and `gpt-6-luna`.
The broader Windows acceptance checklist remains open; no release tag has been made.

## Writing preferences across workflows

- Create, edit, duplicate, archive, restore, and delete personal style profiles.
  Store a name, instructions, and optional approved examples locally.
- Use global profiles across projects or keep a profile within one project.
  Select a global default, inherit it per project, or explicitly choose no style.
- Writer and Editor apply the selected profile. Writer's evaluator and Critic
  assess adherence without adopting the voice themselves.
- Rewrite, Tighten, Expand, Improve Dialogue, Change Tone, Continue, and custom
  attached-passage edits use the same style layer. Critique Selection stays
  read-only. Explicit requests override conflicting preferences.
- A request captures its profile at submission. Later edits, profile switches,
  archive/delete operations, and Writer stages cannot change that snapshot.
- The Style control stays visible in Selection mode. Result tooltips, chat
  history, and diagnostics identify the profile/revision used. Prompt capture
  remains optional; ordinary metadata does not contain instructions/examples.
- Existing passage boundaries, strict result validation, cancellation, stale
  checks, inline review, safe application, and undo/redo remain in effect.

The [writer-style guide](documentation/3_USER_GUIDE/12_Writer_Style_Profiles.md)
includes setup steps, a personal-style worksheet, a reusable template, three
original sample profiles, and advice for comparing and refining results.

## OpenAI request compatibility

- Unset optional generation parameters are omitted, fixing the HTTP 400 caused
  by sending `max_tokens: null` to `gpt-6-luna`.
- GPT-5/GPT-6 and o1/o3/o4 families use `max_completion_tokens` when a limit is
  supplied and retain provider-default reasoning and sampling. SammyAI does not
  send temperature, top-p, or seed for these families. Older and unrecognized
  OpenAI model names retain the legacy parameter convention.
- Diagnostics report the settings actually sent. All writing workflows and
  selection actions use the same adapter; provider errors preserve their cause.

See [model settings](documentation/3_USER_GUIDE/7_LLM_Settings.md) for the effect
on presets. Support for new model families may require another compatibility
policy update; this change does not automatically discover model capabilities.

## Upgrade and rollback

The application adds SQLite migration 6 to the existing project database. It
does not modify story files or convert/delete existing STYLE memories. Profile
content is independent of retrieved project memory.

Before launching this version against important data, close SammyAI and back up
its application data directory, including the project database and conversations.
The actual location depends on the Windows account; see
[runtime locations](documentation/2_INSTALLATION/1_Start.md). Keep that pre-upgrade
backup if you need to return to v0.6.2. The older migration runner rejects newer
schemas: reinstalling the old app alone cannot downgrade the database. Restore
the pre-upgrade app-data backup with SammyAI closed; retain a separate copy of
the upgraded data first so new profiles/conversations are not lost.

## Limits and acceptance

Profiles make preference delivery consistent; generated prose remains dependent
on the model, task, and context. Assistant and Brainstormer retain their existing
behavior. Automatic style extraction, profile blending, per-character overrides,
and profile version-history restoration are outside this release.

In the maintainer's Shelf Life tests, both models followed the selected profile.
Whole-story revisions left some unwanted writing habits in place; focused edits
on selected passages produced more of the requested corrections. Further examples
and prose-quality comparisons are ongoing.

Instructions are limited to 6,000 characters and examples to 3,000. Selected
style content is never silently dropped or truncated to fit a model's context
window. Use a shorter profile/passage when needed. Ordinary diagnostics keep
identity and hashes, not a recoverable copy of deleted profile content.

See the [implementation and acceptance record](documentation/7_NEXT_STEPS/15_Writer_Style_Profiles.md)
for automated verification and the outstanding manual checklist.

Latest automated verification: **647 passed, 1 Windows symlink skip, 16
external/model tests deselected**, including 42 new OpenAI/Ollama adapter
regressions. The offline wheel built successfully and contains the updated
OpenAI adapter and parameter policy. The earlier profile implementation passed
all 28 installed-package profile UI checks and its migration/diagnostic/review
checks; offscreen Windows-font previews were inspected. These checks do not
replace maintainer testing of real projects and generated prose.
