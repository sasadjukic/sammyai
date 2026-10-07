# Chat and agent diagnostics — implementation and acceptance

Work branch: `codex/chat-agent-diagnostics`, based on accepted `main` at
`3530dea`. Release 5 implementation started on 2026-10-07.

## Scope

Persist request identity before context assembly; record context degradation,
individual model calls and Writer stages, proposal validation, human review,
safe application and undo/redo. Provide a local timeline, bounded optional
content capture, export preview/redaction, retention and deletion. Preserve
existing conversation JSON and project data through an additive migration.

No automatic repair, automatic acceptance, additional file-write authority,
new agents, deterministic model replay or crash-resumable editing is included.
Offline proposal inspection runs the parser only and never applies changes.

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
