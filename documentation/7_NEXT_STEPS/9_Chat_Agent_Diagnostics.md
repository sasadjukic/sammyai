# Chat and agent diagnostics — implementation and acceptance

Work branch: `codex/chat-agent-diagnostics`, based on accepted `main` at
`3530dea`. Release 5 implementation started on 2026-10-07.

## Scope

Persist request identity before context assembly; record context degradation,
individual model calls and Writer stages, proposal validation, human review,
safe application and undo/redo. Provide a local timeline, bounded optional
content capture, export preview/redaction, retention and deletion. Preserve
existing conversation JSON and project data through an additive migration.

The initial diagnostics release included no automatic repair, automatic
acceptance, additional file-write authority, new agents, deterministic model
replay or crash-resumable editing.
Offline proposal inspection runs the parser only and never applies changes.
The subsequent single-brace recovery below extends proposal handling without
changing write authority or diff approval.

## Implemented

- Additive SQLite migration 5 and a core-owned `RequestTraceService`.
- Submission/message/run identity; request-scoped context and worker signals.
- Context references, hashes/ranges, policy limits, retrieval outcomes and errors.
- Independent Writer/model-call evidence, duration and available provider metadata.
- Explicit incomplete-envelope, empty-stage and truncated-stage rejection.
- Linked inline/popup review decisions, accepted change sets, apply, rollback,
  cleanup failures and file-tool undo/redo.
- Restart interruption records; visible storage gaps without bypassing file checks.
- Timeline viewer, four capture toggles, redacted editable exports and deletion.
- User guide, synthetic dialog screenshot and v0.6.1-alpha development notes.

## Automated verification — 2026-10-07

Baseline before changes: `.\Scripts\python.exe -m pytest -q` — **279 passed,
1 skipped, 16 deselected**. The three initial diagnostics characterization tests
also passed before production changes.

Final full suite: `.\Scripts\python.exe -m pytest -q` — **326 passed, 1 skipped,
16 deselected** in 43.93 seconds. The skip is Windows symlink creation unavailable
on this account. External/provider and model-download tests remain excluded by
the repository's standard test configuration. Two existing dependency deprecation
warnings remain.

Packaging and visual checks:

```powershell
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build\diagnostics-wheel
.\Scripts\python.exe tests\diagnostics\check_packaged_diagnostics.py build\diagnostics-wheel\sammyai-0.6.1a0-py3-none-any.whl
.\Scripts\python.exe tests\change_sets\check_packaged_review.py build\diagnostics-wheel\sammyai-0.6.1a0-py3-none-any.whl
.\Scripts\python.exe tests\diagnostics\preview_diagnostics.py documentation\3_USER_GUIDE\pictures\Diagnostics.png
git diff --check
```

All passed. Both wheel checks use fresh virtual environments without provider
SDKs or network access. They cover diagnostics migration/reload/capture/deletion
and existing chat persistence, large-file addition, review, CRLF and safe
apply/undo/redo. The dialog screenshot was inspected with Windows fonts and the
application theme. These checks do not substitute for interactive packaged
Windows acceptance with configured providers.

## Acceptance still required

- [ ] Reproduce the October 6 typo / partial context / malformed proposal case.
- [ ] Reopen the conversation and restart, including an interrupted request.
- [ ] Exercise Writer draft/evaluate/revise and mixed-hunk review with undo/redo.
- [ ] Verify distinct provider, stale-file and retrieval failure outcomes.
- [ ] Inspect content-excluded and content-included exports and redact a preview.
- [ ] Verify capture settings, retention and diagnostic deletion on Windows.
- [ ] Complete clean packaged Windows acceptance before tagging a release.

The release is not marked completed until maintainer manual acceptance.

## Malformed JSON follow-up — 2026-10-07

Branch: `codex/change-directive-validation`, based on merged diagnostics at
`6341273`. A captured response contained both envelope tags but invalid JSON at
the ending: an omitted file-object brace, an extra quote and escaped newlines
outside strings. The envelope regex previously masked this as an envelope error.

Envelope matching now leaves JSON validation to the decoder. Rejections include
the JSON line/column; technical evidence records location without bypassing
content-capture settings. The agent prompt clarifies escaping and closing syntax.
Restored chat prefers the friendly proposal notice over its duplicate exception,
while preserving the exception in the timeline. No automatic repair is added.

Verification: **114 focused tests passed**; full default suite **343 passed,
1 skipped, 16 deselected** in 41.04 seconds, with the same two dependency warnings.
Read-only offline inspection of the captured response reports a JSON error at
line 3, column 10517. No provider call or user-file write was made. Regression
fixtures use synthetic text, not captured writing. Live generation with the
updated prompt remains unverified; model output can still fail validation.

## Single missing-brace recovery — 2026-10-07

A subsequent captured response had one missing file-object closing brace before
the final `]}`. The response ended normally and its content string was complete.
One `}` insertion made the body valid JSON without removing or changing any
original character. The pre-diagnostics parser also rejected this response;
it would silently miss the earlier malformed ending, so diagnostics alone cannot
explain the new sequence of model formatting failures.

The workflow now attempts that one insertion only for file-capable agents whose
stages were neither empty nor reported truncated. Recovery requires complete
envelope tags, the final array/root closers, and a flat final file object with
string path, operation and content. It does not fix quotes, escapes, trailing
text, missing content or other malformed structures. All context, path, file
policy and diff-approval checks remain in place.

`proposal.syntax_error` retains the original structural failure, and
`proposal.syntax_recovered` records the insertion and response hashes. A chat
notice accompanies a successfully prepared review. Failed-proposal capture
retains the original malformed response when enabled. No extra model call is
made, and the strict offline inspector continues to report the original error.

Read-only replay confirmed recovery of the latest captured response; the earlier
response with several syntax problems stays rejected. **134 focused tests passed**
using synthetic fixtures, including unchanged values, approval, capture privacy,
chat reload, path safety, authorization and incomplete/read-only workflows.
The final full default suite passed: **363 passed, 1 skipped, 16 deselected** in
41.49 seconds, with the same dependency warnings and Windows symlink skip.
`git diff --check` passed. No live provider request was made during verification.

For longer-term prevention, provider-enforced JSON schemas would address a broader
class of syntax errors. [Ollama's official documentation](https://docs.ollama.com/capabilities/structured-outputs)
currently states that Ollama Cloud does not support structured outputs. The
current client requests unconstrained text; schema enforcement is not added here.
