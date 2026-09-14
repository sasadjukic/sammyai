# US English spelling acceptance — 2026-09-13

Branch: `codex/us-english-spell-check`. Target version: `0.5.2a0`.
Implementation and automated validation are complete; interactive Windows acceptance and the maintainer's merge are accepted on 2026-09-13.

## Completed validation

- Before implementation: `python -m pytest -q tests/editor_workspace tests/foundation/test_chat_panel_redesign.py`
  — 23 passed.
- Final full suite: `python -m pytest -q` — 159 passed, 16 deselected,
  2 existing dependency deprecation warnings, 20.76 seconds on Windows / Python 3.14.6.
- Spelling coverage: 13 tests covering real US dictionary behavior, exact UTF-16
  offsets, smart apostrophes, multiline code, paths, persistence, failed saves,
  dictionary caching, cancellation, all tabs/composer, undo, search coexistence,
  settings Save/Cancel, stale corrections, suggestions menus, and viewport rendering.
- `python -m pip wheel . --no-deps --no-build-isolation -w dist/spell-check`
  builds the wheel with the dependency pin and bundled attribution notices.
- `python -m pip download spylls==0.1.7 --no-deps -d dist/spell-check`
  obtains the dependency wheel for the isolated check.
- `python tests/spelling/check_packaged_spelling.py dist/spell-check`
  creates a fresh virtual environment, installs only the two local wheels using
  `--no-index --no-deps`, then verifies spelling, suggestions, personal dictionary
  persistence and notices with network connections blocked and no source-tree imports.
  This validates the isolated spelling component, not a complete GUI installation.
- The real Settings widget was rendered offscreen with the Windows Segoe UI font
  and visually reviewed. Screenshot: `../3_USER_GUIDE/pictures/sammyai_writing_settings.png`.
- `git diff --check` passes.

## Windows manual acceptance still required

1. Start SammyAI from this branch. Open ten document tabs, including a long chapter,
   and type misspellings in different tabs and the composer. Confirm responsive typing
   and underlines when scrolling to distant parts of the chapter.
2. Search for an underlined word. Confirm both search highlighting and the underline
   remain visible, including after changing tabs and closing search.
3. Right-click a misspelling, open the Spelling submenu, select a suggestion, then
   Undo and Redo. Confirm only the intended occurrence changes and that standard
   Cut, Copy, Paste and Select All remain available.
4. Try Ignore Once on repeated words and insert text before the ignored occurrence.
   Try Ignore All across tabs/composer. Add an invented name to the dictionary.
5. Open Settings with the gear and with Edit > Settings. Disable spelling and Save.
   Confirm all underlines disappear; open a new tab and confirm it stays unchecked.
   Restart to verify the toggle and added dictionary word persist, then re-enable.
   Confirm Cancel does not change the preference.
6. Open LLM settings from Settings and exercise the existing presets and parameter
   controls. Confirm their existing behavior remains available.
7. With networking disabled, install/run the complete application in a clean Windows
   environment from the built wheel and provisioned dependency wheels. Repeat typing,
   suggestions and restart checks. The isolated core check above does not replace this.
8. Check keyboard navigation, display scaling, context menus, and the Settings layout
   on the actual desktop. Accept the feature, then merge and tag through the usual
   maintainer workflow. Mark the roadmap complete only after acceptance.

## Settings direction

Use one Settings entry point. Writing preferences belong to application configuration;
model parameters keep their existing configuration and UI; project-specific choices
belong to project settings. Introduce category navigation (Writing, Models, Appearance,
Projects) as controls accumulate. Avoid empty placeholder categories now.

The first personal dictionary is global. Project-specific words and a word-management
screen are intentionally deferred. No schema migration is needed: existing data remains
compatible and a missing preferences file enables spelling with an empty personal list.
