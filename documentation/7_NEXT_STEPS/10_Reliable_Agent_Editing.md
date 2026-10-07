# Targeted replacements and plain-text proposals

User-requested follow-up on `codex/change-directive-validation`, 2026-10-07.
Extends the diagnostics investigation with automated editing improvements.

## Problem and behavior

Four revisions to separate passages previously required a whole-file `write`.
The model also had to JSON-escape all of that writing. Captured responses ended
normally but produced invalid JSON closers and escapes. Individual punctuation
repairs did not address that output contract.

The agent now proposes multiple exact replacements for one file. SammyAI resolves
the passages in an immutable source snapshot and creates one `FileChangeRequest`
with multiple `TextEdit` objects. There are no model-supplied offsets. Searches
must be unique, nonempty, non-overlapping and fully visible in explicit context.
Only line-ending differences are normalized during matching. Unchanged text stays
intact; inserted replacement text follows the source line-ending convention.

All existing path/project/source-version checks and hunk review remain required.
Partial context permits replacements only within visible ranges. Whole-file
write/delete still requires complete context. Empty replacement text removes the
matched passage. Read-only agents, incomplete workflows, undo and redo retain
their existing behavior. Proposal preview failure cannot leave an actionable
change set in the run result.

## Plain-text protocol

`sammyai_core/proposal_protocol.py` parses `<sammyai_edits>` into the existing
in-memory directive structure. No long passage is decoded from JSON or XML.
The prompt version is `agent-prompts-v2-text-edits`. The default contract applies
to Brainstormer, Editor, Writer draft and Writer final revision; evaluation stays
read-only. Writer searches always refer to the original supplied source.

```text
<sammyai_edits>
summary: Revise two passages
file: chapter.md
operation: replace
<<<SAMMYAI_SEARCH>>>
Exact old passage.
<<<SAMMYAI_REPLACEMENT>>>
New passage with "ordinary quotes" and real newlines.
<<<SAMMYAI_END>>>
<<<SAMMYAI_SEARCH>>>
Another exact old passage.
<<<SAMMYAI_REPLACEMENT>>>
Another new passage.
<<<SAMMYAI_END>>>
</sammyai_edits>
```

The parser constructs `files[].replacements[]` with `old_text` and `new_text`.
Each file occurs once; repeat the search/replacement blocks for its changes.
Repeat `file:` / `operation:` for different files within one envelope.

`write` and `append` use `<<<SAMMYAI_CONTENT>>>` through `<<<SAMMYAI_END>>>`.
Insert operations use `<<<SAMMYAI_ANCHOR>>>`, then `<<<SAMMYAI_CONTENT>>>`, then
`<<<SAMMYAI_END>>>`; the anchor is an exact unique source line. `delete` has no
text blocks. All metadata values occupy one line.

Blocks preserve literal content, including leading/trailing spaces, quotes,
backslashes, Unicode and extra blank lines. One LF/CRLF immediately before a
closing marker is framing; an additional blank line represents a content newline.
Reserved control lines cannot occur as literal content. Conflicting markers,
missing blocks, incomplete envelopes, and multiple/mixed proposals fail closed.

The legacy JSON parser and its narrowly scoped missing-brace recovery remain
available for compatibility. JSON may also carry the new replacement operation;
it receives the same source validation. A literal legacy tag inside a raw content
block is ordinary writing. Valid JSON can contain a literal new tag in a string.

## Diagnostics and verification

`proposal.validation` includes `proposal_format` and operation names. Existing
capture settings cover raw proposals without introducing new automatic content
capture. Parsing errors include structural locations without quoting writing.
The offline inspector understands both formats and has no apply capability.

Automated verification covers four-part CRLF revisions, long raw rewrites,
ambiguous/missing/overlapping matches, unseen ranges, stale sources, project and
path protection, Writer stages, read-only/truncated flows, mixed formats,
capture privacy, partial hunk approval, undo/redo and installed-wheel imports.

Final full suite: **421 passed, 1 skipped, 16 deselected** in 43.52 seconds.
The skip is Windows symlink creation unavailable on this account; external/model
tests are excluded by repository defaults. Two existing dependency warnings remain.

```powershell
.\Scripts\python.exe -u -m pytest -q
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build\reliable-editing-wheel
.\Scripts\python.exe tests\diagnostics\check_packaged_diagnostics.py build\reliable-editing-wheel\sammyai-0.6.1a0-py3-none-any.whl
.\Scripts\python.exe tests\change_sets\check_packaged_review.py build\reliable-editing-wheel\sammyai-0.6.1a0-py3-none-any.whl
git diff --check
```

The offline wheel build and both isolated package checks passed. Package tests
install without dependencies in temporary virtual environments, block network
connections, and verify parser availability, raw multi-passage preparation,
diagnostics persistence, existing review behavior, CRLF, apply and undo/redo.

Live model conformance and narrative quality remain manual acceptance items.
No model API calls or changes to the user's story files are part of offline tests.
