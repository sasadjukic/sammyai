# v0.5.1-alpha — Chat history (unreleased)

- Added a collapsible conversation list with current-project, all-conversation,
  and unassigned views, automatic titles, timestamps, previews, and counts.
- Restore saved transcripts and agent metadata, rename conversations, and delete
  with confirmation. Remember the last selected conversation across restarts.
- Preserve unsent drafts while switching conversations during the app session.
- Capture conversation identity explicitly for normal and legacy DBE requests.
  Conversation changes are disabled during generation in this first version.
- Skip unreadable sessions with a visible notice and preserve their files.
- Preserve existing project cleanup behavior; failed deletion retains UI state.

## Automated verification

`Scripts/python.exe -m pytest -q`: **146 passed, 16 deselected**. Two existing
third-party deprecation warnings remain. Coverage includes persistence,
restoration, project filtering and cleanup, deletion failure/cancellation,
transcript metadata, drafts, narrow-panel layout, and normal/DBE requests whose
active conversation changes before their worker executes. Offscreen Qt visual
inspection also verified the panel at 500 × 750 pixels.

## Acceptance

Windows manual acceptance is pending. No release tag or completion status has
been applied. Verify narrow and tall chat panels, keyboard selection, restart
restoration, project filters, rename, delete/cancel, offline/error recovery,
and both normal and DBE generation before releasing.
