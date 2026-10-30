# Writer file-operation maintenance

**Status: COMPLETED — 2026-10-29**

Branch: `codex/writer-file-operation`, based on accepted v0.6.2-alpha.
Implementation and maintainer Windows acceptance: 2026-10-29. The maintainer
reported that the acceptance tasks executed without issues in the **Car Show**
project. Acceptance covers workflow mechanics and execution, including file
operations and review; writing quality was explicitly not evaluated.

This maintenance fix is complete before v0.7.0 Writer style profiles. GitHub
push/merge and any release tag remain maintainer actions. The package version
remains `0.6.2a0`; this record does not assign a new release number.

## Problem and resulting behavior

The October 28 21:07 Writer request asked to append Scene 1 to an empty file.
The destination was fully supplied, but the final revision proposed replacing
a sentence absent from the saved file. Validation correctly rejected it. The
visible model response discussed the revision without delivering the scene.
A later request also returned prose without any file-change proposal despite
a populated destination. Neither case establishes an append-on-empty-file defect.

The Writer now retains a request-local destination/operation contract across
draft, evaluation and revision. Common explicit file commands are recognized
from the current user request only. Reading a reference does not make it a
destination. Resolved snapshots disambiguate basename references. The evaluator
stays read-only. All stages are told that drafts have not been saved; the final
proposal must apply to the original source, with all revised new material for
append/insertion operations.

A draft proposal that passes both the request contract and existing file/source
validation can refine a nonspecific request (such as "store the scene in this
file") to its chosen operation. An invalid draft cannot override an explicit
request, but the final stage can correct it. Draft validation only prepares an
in-memory change set; it never opens a review or applies a file.

Final proposals must retain every captured destination and operation before
ordinary source validation and preview. Missing proposals are rejected explicitly.
Failure is recorded after validation rather than announcing workflow completion
before checking the proposal. The persisted assistant reply starts with a clear
no-files-changed explanation, independent of diagnostic retention. Technical
reasons remain in diagnostic notices; raw failed responses still obey the
failed-proposal capture setting. No extra model call or automatic repair is added.

## Scope and limits

- Natural-language recognition is deliberately bounded, not a general language
  parser or a new authorization mechanism. Unrecognized wording is still supplied
  verbatim to every stage; a valid draft can establish the contract. If neither
  wording nor draft identifies a file operation, ordinary prose remains allowed.
- Existing project, path, immutable source, addition-budget, truncation, review
  and undo protections still apply. Invalid replacements are never converted
  into additions. Empty/truncated file revisions never apply a fallback draft.
- No story files, saved user chats, runtime settings, model configuration,
  project data, dependencies or database schemas are changed by this fix.
- This does not address editor tab sizing or project workspace restoration.

## Verification

Regression cases first demonstrated wrong-operation acceptance, missing-proposal
success and reference-file retargeting. Coverage now includes empty/nonempty
append, the unsaved-draft replacement failure, missing/empty revisions, validated
draft contracts, corrections to invalid drafts, multiple destinations, mixed
operations, path aliases, read-only references, trace privacy and chat reopening
after diagnostics removal. Package checks exercise append review preparation,
apply/undo and missing-proposal rejection without network access.

Verification results:

- Full supported suite: **488 passed, 1 skipped, 16 deselected** in 74.67 seconds.
  The skip is unavailable Windows symlink creation; external/model tests remain
  excluded. Two existing dependency deprecation warnings remain.
- After the final missing-proposal notice deduplication change, the Writer
  contract and diagnostics tests passed again: **61 passed** in 5.82 seconds.
- Offline wheel build and both isolated installed-package checks passed with
  network access blocked. The installed Writer supports empty-file append,
  apply/undo and missing-proposal rejection.
- `git diff --check` passed.

```powershell
$env:TEMP = Join-Path (Get-Location) 'build'
$env:TMP = $env:TEMP
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/writer-full-final
.\Scripts\python.exe -B -u -m pytest -q tests/diagnostics/test_trace_service.py tests/diagnostics/test_agent_traces.py tests/agent_workflows/test_writer_file_contract.py --basetemp=.pytest_cache/writer-verified
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/writer-operation-wheel
.\Scripts\python.exe -B -u tests/diagnostics/check_packaged_diagnostics.py build/writer-operation-wheel/sammyai-0.6.2a0-py3-none-any.whl
.\Scripts\python.exe -B -u tests/change_sets/check_packaged_review.py build/writer-operation-wheel/sammyai-0.6.2a0-py3-none-any.whl
```

## Accepted Windows run: Car Show

The maintainer confirmed successful execution of the acceptance tasks on
2026-10-29. The saved conversation `session_20261029_224236` and its linked
diagnostic records were then inspected read-only. The configured model was
`gemma4:31b` through `ollama_cloud`. Times below are local Europe/Belgrade
(UTC+1 on this date).

| Request time | Workflow and task | Recorded result |
| --- | --- | --- |
| 22:44:24 | Writer: append an opening sample using `car_show_bible.md` to empty `car_show_draft.md` | The destination snapshot was empty and complete. The captured request and final proposal both specified `append`. All three model stages responded normally. Review opened at 22:44:30; acceptance preceded file application at 22:44:35. |
| 22:48:23 | Writer: append another passage to the populated draft | The source contained 1,024 characters. The captured request and final proposal retained `append` and the same destination. All three stages responded normally. Review opened at 22:48:32; acceptance preceded application at 22:48:41. |
| 22:49:29 | Selection: Tighten Prose | Proposal validated, reviewed, accepted and applied at 22:49:36. |
| 22:50:05 | Selection: Improve Dialogue | Proposal validated, reviewed, accepted and applied at 22:50:19. |
| 22:53:06 | Selection: advice with an explicit instruction not to modify the draft | Returned critique/advice and completed at 22:53:07, with no review or file-application event. |

The two Writer request IDs are `7d148e76-0b51-4f8d-aabe-8d04abd3ad9c` and
`44978627-5c1a-4cc3-9c0a-98b6d2d39134`. Each persisted assistant message also
records three model calls. Their final proposals use `text-v2`, with no recorded
context errors, truncation or proposal failure. A hash check confirmed that the
first 1,024 characters of the current draft still exactly match the first
accepted append. The current file hash matches the last accepted selection edit.

### Acceptance coverage

- [x] Maintainer sign-off for mechanics and execution, explicitly excluding
  writing quality.
- [x] Live append to an empty file and a populated file, preserving the requested
  operation and destination through the three-stage Writer run.
- [x] Inline review and acceptance before application; original opening retained
  after the subsequent append and selection edits.
- [x] Live selection editing and advice-only execution, recorded as selection
  workflow evidence rather than three-stage Writer evidence.
- [x] Deterministic regression/package coverage for invalid or missing proposals,
  unsaved-draft replacement errors, failure visibility after chat reopening,
  read-only Writer requests, and apply/undo/redo.

### Evidence boundaries

The maintainer's report establishes manual acceptance. The saved run corroborates
the successful paths listed above; it contains no rejected/missing proposal or
undo/redo events. Those cases are supported by the automated and packaged checks,
not claimed as independently observed live failures in this conversation.

Prompt, draft, evaluator and successful raw-response capture were disabled.
Stage outcomes and operation metadata are retained, but the exact evaluator
corrections cannot be reconstructed from this run. The later advice request
carried a selection reference and therefore used the selection workflow. It is
not a separate live check of Writer's chat-only path.

No judgment about prose quality, voice, story effectiveness or readiness of
future Writer style profiles is part of this acceptance. No user story or chat
content was changed during the evidence review.
