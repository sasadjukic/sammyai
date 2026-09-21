# Manual indexing retirement — 2026-09-20

Branch: `codex/retire-manual-indexing`, based on accepted inline diff review in
`main` (`54de7f3`). Implementation and automated validation are complete;
maintainer desktop testing and merge are pending. This is an unreleased
maintenance follow-up; package version remains `0.6.0a0`.

## Behavior

- Removed the Legacy Manual Indexing submenu, current-file indexing command,
  external-file indexing command, and legacy index manager.
- **Advanced > Project Context > Import Reference File...** copies a supported
  `.md`, `.txt`, or `.pdf` reference into the active project's `References` folder.
  It schedules the ordinary project sync, with project attribution and normal
  hash-based updates and removal. A file already inside the project is reused.
- Imports preserve source bytes and the external original. Existing files and
  open document paths are not overwritten; duplicate names receive a numeric
  suffix. Failed copies do not publish partial reference files.
- **Indexed Files...** inspects source paths, project attribution, and chunk
  counts. Its filters cover the active project, all projects and legacy entries,
  and unassigned legacy entries. Refresh and copying a source path are read-only.
- Rebuild, statistics, and explicit global reset remain under Project Context.
  The reset confirmation explains that unassigned legacy entries cannot be
  restored automatically. Legacy DBE remains available.

## Existing data

No automatic migration, reassignment, or deletion of existing index entries
occurs. Unassigned legacy entries remain inspectable and are excluded from
project-scoped retrieval. To use an old external reference in a project, locate
the source through **Indexed Files...** and import it into that project.

An imported reference is an independent copy. Changes to the external original
do not update it. Temporary chat attachments and explicit file context retain
their existing behavior.

## Validation

- Before changes, the relevant context, project, vector-store, and bootstrap
  tests passed: **36 passed**.
- Focused post-change run: **56 passed, 1 skipped**. Tests cover source-byte
  preservation, collisions and concurrent destination creation, failed-copy
  cleanup, excluded folders and junctions, project synchronization lifecycle,
  menu states, canceled imports, project changes during file selection, and
  read-only inventory with real temporary Chroma metadata.
- Full supported suite: `.\Scripts\python.exe -m pytest -q` — **230 passed,
  1 skipped, 16 deselected**, 2 existing dependency deprecation warnings,
  23.42 seconds on Windows / Python 3.14.6. Model/external tests are excluded.
  The skipped test requires Windows symlink creation permission; the simulated
  junction rejection test passed.
- The actual Qt inspector was rendered with the application stylesheet and
  visually inspected. [Screenshot](../3_USER_GUIDE/pictures/Context_Index.png).
- `.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation -w dist/manual-indexing-retirement`
  built the wheel successfully.
- `.\Scripts\python.exe tests\project_system\check_packaged_references.py dist\manual-indexing-retirement\sammyai-0.6.0a0-py3-none-any.whl`
  passed in a fresh temporary environment using `--no-index --no-deps`, isolated
  imports, and blocked network connections. It verifies the installed importer,
  collision behavior, inventory model, packaged inspector, and theme assets.
  This is a core/package check, not a full clean GUI installation.

To preview the inspector with sample data and no access to the live index:

```powershell
.\Scripts\python.exe tests\context_engine\preview_context_index.py
```

## Desktop acceptance checklist

- [] Open Advanced and confirm the legacy manual indexing submenu is gone,
  while Legacy DBE is available. With no project open, importing is disabled.
- [] Open a test project and import an external Markdown, text, or PDF reference.
  Confirm it appears in `References`, the source remains unchanged, and normal
  sync attributes its chunks to the active project in **Indexed Files...**.
- [ ] Import the same filename again. Confirm a numbered copy appears and the
  existing project copy is unchanged. Cancel an import and confirm no copy appears.
- [ ] In the inspector, test each scope, select a file, copy its source path,
  and refresh. If legacy entries exist, confirm they remain visible as unassigned.
- [ ] Save an edit to a project reference and verify context updates. Remove a
  test reference and rebuild; confirm its project index entry disappears while
  the original external file remains.
- [ ] Switch projects and confirm retrieval stays scoped to the active project.
  Verify ordinary chat, inline review, and Legacy DBE still work.

Use [the user guide](../3_USER_GUIDE/3_RAG_Menu_Options.md) for menu details and
recovery options. Merge through the maintainer workflow after acceptance.
