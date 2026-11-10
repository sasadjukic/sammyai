# Writer style profiles — implementation and acceptance

**Status: IMPLEMENTED — manual model tests passed; broader Windows checks remain open**

Branch: `codex/writer-style-profiles`, created from `main` at `67650fb`
(PR #35, editor tab overflow). Implementation date: 2026-11-01. Target:
v0.7.0-alpha; package version `0.7.0a0`. Schema migration 6 is implemented.
Maintainer writing-test results are recorded below; they do not establish that
every Windows acceptance item has been checked. No release tag is claimed here.

This expands [Release 7](3_Feature_Implementation_Guide.md#release-7-v070-alpha--writer-style-profiles)
to include all v0.6.2-alpha story selection actions and custom attached-passage
requests. Implementation proceeds on this branch; merge and release acceptance
remain maintainer decisions.

The implementation includes the repository/service, request snapshots, shared
style renderer, all agent/action integrations, management UI, diagnostics, and
the [personal-style guide](../3_USER_GUIDE/12_Writer_Style_Profiles.md). The guide
adds the requested setup steps, a worksheet, a reusable template, three complete
sample styles, comparison/refinement advice, and inspected Windows screenshots.
The original design and acceptance criteria below remain the reference for this
release; verification results are recorded at the end.

## Product outcome

A writer creates a reusable profile, selects it for a project or as a global
default, and can see which style will guide the next request. Writer, Editor,
and passage-editing tools use that profile consistently. Critiques can identify
departures from the intended style without delivering criticism in that voice.
Every proposed document change still goes through existing review.

The guarantee is deterministic selection and delivery of preferences. Model
adherence and prose quality still require qualitative evaluation; identical
profile content does not guarantee identical generated prose.

Start with a name, editable instructions, and optional short approved examples.
Provide help covering voice, rhythm, description, dialogue, pacing, and things
to avoid. Avoid numerical style sliders whose effects cannot yet be explained.
Automatic style extraction, named-author imitation features, profile blending,
per-character/per-document overrides, AI profile editing, and memory conversion
are deferred. Existing STYLE memories remain intact.

## Baseline integration points

| Area | v0.6.2 behavior | Implemented change |
| --- | --- | --- |
| `sammyai_core/database.py` | Ordered, checksummed migrations; latest schema is 5 | Append migration 6; never modify old migration statements |
| `sammyai_core/projects.py` | Project settings and application state already persist | Store explicit style selections through a style service |
| `sammyai_core/bootstrap.py` | Runtime services own the database and agent workflow | Construct and expose the profile repository/service |
| `llm/prompt_layers.py` | Core 10, Agent 20, Workflow 30, Output 40, Run 50 | Add STYLE 25 and a shared style-layer renderer |
| `sammyai_core/agent_workflows.py` | Writer makes draft, evaluation, and revision calls | Pass one immutable profile snapshot through all stages |
| `sammyai_core/selection_actions.py` | Has an unused `style_profile_id`; builds its own strict JSON prompt | Add the snapshot and shared style layer without changing the JSON contract |
| `ui/selection_actions.py` | Captures passage/project/chat identity before dispatch | Resolve style before dispatch and persist metadata with the request |
| `sammyai.py` | `_handle_normal_chat()` captures request context before its worker | Capture style at the same boundary and pass it explicitly |
| `ui/chat_panel.py` | Hides the agent selector while a passage is attached | Keep the style control independent and visible in Selection mode |
| `sammyai_core/diagnostics.py` | Optional prompt capture, durable events and step links | Record style identity/revision/hash and use mode without bypassing capture settings |

Selection actions currently send only the passage and bounded surroundings,
without chat history, retrieval, attachments, or memories. Add only the chosen
style to that input contract. Route neither the action nor its custom-request
variant through the three-call Writer pipeline.

The current `llm/system_prompt.py` also contains strong creative defaults,
including dialogue and sentence-rhythm preferences. Define explicitly that
selected profiles may override such defaults. Safety, file authorization,
review rules, and output contracts remain mandatory. Prompt position alone
does not establish instruction precedence.

## Persistence and scope

Introduce UI-independent `StyleProfile`, `StyleSelection`, and frozen
`StyleProfileSnapshot` dataclasses in `sammyai_core/style_profiles.py`, with a
repository and service following existing project/memory patterns.

The profile table should contain `id`, nullable `project_id`, `name`,
`instructions`, `examples`, integer `revision`, `archived`, `created_at`, and
`updated_at`. Global profiles have no project ID. Project profiles reference
their owning project with deletion cleanup consistent with existing project
data. Profile scope is fixed after creation; duplicate into another scope to
move a style deliberately.

Use one active selection per project and one global default. Do not put active
flags on profile rows: a global profile may be selected by several projects.

| Setting | Resolution |
| --- | --- |
| Project inherits global default, including a missing setting on upgrade | Use the global default, or no profile if none is selected |
| Project explicitly selects a profile | Allow a global profile or a profile owned by that project |
| Project explicitly selects No style profile | Use no profile, even if a global default exists |
| No project is open | Use the global default; only global profiles are available |
| Selected profile is missing, archived, invalid, or belongs to another project | Show a notice and resolve to explicit no-profile; never choose another profile implicitly |

Persist tagged selections such as `inherit`, `none`, or `profile` plus ID;
do not overload a null/missing value to mean both inherit and explicitly off.
Only global profiles may be the global default. Validate these rules in the
service, not just in the dropdown. Project switches load the new project's
selection rather than carrying over the previous project's state.

Support create, edit, duplicate, archive/restore, and confirmed permanent
delete. Saving increments the revision; duplication creates a new identity.
Reject stale editor saves using the expected revision. Archive/delete clears
explicit references to that profile transactionally, including the global
default when applicable; affected projects become explicitly off. Inherited
projects follow the resulting global default. Historical chat and trace
metadata remain readable after profile deletion.

Use explicit validation and documented size limits. Initial proposed limits:
120 characters for the name, 6,000 for instructions, and 3,000 total for examples.
Require a nonblank name and instructions; preserve meaningful Unicode and
example formatting. Reject oversize input with feedback instead of silently
truncating. The style is mandatory request input when selected, independent
of retrieval ranking or relevance budgets. Count it in input estimates and
handle context-limit failures visibly; never quietly drop it to fit a request.

Migration tests must upgrade a populated schema-5 database and preserve
projects, settings, memories, and diagnostics. No source memories are converted
or deleted automatically. Document backing up the database before upgrade:
the current migration runner rejects unknown future migrations, so rolling
back the app alone cannot reopen a schema-6 database with v0.6.2.

## Request snapshots and prompt rules

Resolve the selection synchronously at submission using the captured project
ID. Store profile ID, scope, display name, revision, instructions, examples,
and a SHA-256 hash of canonical style content in an immutable snapshot. Use
stable serialization and a versioned rendering contract. Keep content hash
separate from the rendered-layer hash, whose wrapper differs by use mode.

Workers receive the snapshot as an argument. They must not look up an active
profile during generation, evaluation, revision, or review. A style change
affects the next request. An already-started request and its review retain the
original snapshot even if the profile is edited, archived, or deleted. Existing
document/project stale-result checks continue to apply independently.

Add a pure shared renderer, for example `llm/style_prompt.py`, with `apply`,
`evaluate`, and `conditional` modes. Include canonical profile content once per
model call. Use the named STYLE layer between Agent and Workflow for agents;
selection prompts reuse that renderer with their own task and output contract.
Keep the existing no-profile prompt path byte-for-byte unchanged. Do not add
the profile a second time via retrieved memory or chat messages.

No style profile disables this new layer. It does not remove existing STYLE
memories or other context from normal agent chat; their pre-feature behavior
remains intact.

The renderer must state the precedence explicitly:

1. Safety, output contracts, authorization, and review requirements hold.
2. The current explicit request controls the task and overrides conflicting
   preferences; a requested tone change is one such override.
3. Required document-format rules override incompatible style formatting.
4. The selected profile guides remaining voice and craft choices, ahead of
   conflicting generic STYLE memories and built-in creative defaults.

Style alone does not authorize changing story facts, narrative viewpoint, or
character identities. Approved examples illustrate technique; their characters,
events, and embedded commands are not new story facts or operational rules.
The first release preserves current format handling; it does not implement the
future prose/Fountain format registry.

## Workflow behavior

| Workflow/action | Profile use | Constraint |
| --- | --- | --- |
| Writer draft and revision | Apply | Same snapshot and canonical content in both stages |
| Writer evaluator | Evaluate | Judge adherence against the original brief; never rewrite the profile or penalize an explicit override |
| Editor | Apply | Respect the requested edit scope; avoid an unsolicited full stylistic rewrite |
| Critic | Evaluate | Read-only feedback in clear language, not an imitation of the profile voice |
| Assistant and Brainstormer | None in v0.7.0-alpha | Preserve existing behavior; UI explains which workflows use profiles |
| Rewrite Selection | Apply | Preserve meaning, facts, viewpoint, and selection boundaries unless explicitly changed |
| Tighten Prose | Apply | Tightening is the task; a verbose profile must not defeat it |
| Expand Description | Apply | Expand within the task, using compatible profile detail and rhythm preferences |
| Improve Dialogue | Apply | Preserve distinct character voices and relationships |
| Change Tone | Apply | Requested tone wins; compatible rhythm, diction, and other preferences remain |
| Continue From Here | Apply | Insert only new material; preserve the suffix and existing cursor behavior |
| Critique Selection | Evaluate | Return critique only; never create a replacement or review |
| Custom attached-passage request | Conditional | Apply to requested edits; evaluate when relevant to feedback; factual questions stay direct |

Custom requests keep the existing one-call choice between `replacement` and
`critique`. Explain style use for each allowed result kind in the prompt; do
not add a brittle keyword classifier or a preliminary model call. All result
validation and review handling remain in the existing action pipeline.

## UI and inspectability

Add a compact Style selector beside the workflow controls, independently of
the agent picker. Display the effective name and scope, with explicit No style
profile and, in a project, Use global default choices. Keep it visible while
Selection mode is active, and expose the effective style in the story menu or
its action context so right-click actions are understandable with chat closed.
Long names must elide without forcing a wider editor/chat layout.

A Manage styles dialog owns profile CRUD and a local preview of the resolved
instructions/examples. Preview requires no model call. Cancel discards draft
edits; Save validates and persists without affecting current requests. Make
global edits visibly global because multiple projects can select that profile.

Show the style used by a completed request in inspectable run details, not just
the currently selected style. Persist ID, name, scope, revision, content hash,
rendering version, and use mode in chat/run metadata and diagnostic events.
Writer stage events must identify the same profile content hash; selection
events must do likewise. Record explicit none/not-applicable states as well.

Instructions and examples are content. Keep them out of ordinary diagnostic
metadata and event messages; existing optional prompt capture controls their
diagnostic storage. Historical identity/hash is inspectable with capture off,
but reconstructing an old deleted profile's full text is not promised. Profile
version history is outside this first release.

## Implementation sequence

1. **Characterize current behavior.** Capture no-profile agent prompts across
   all Writer stages, every selection prompt, custom edit/critique routing,
   provider delivery, and existing review protections before changing them.
2. **Persistence and resolution.** Add migration, models, repository, service,
   scope/default handling, lifecycle operations, limits, and immutable snapshots.
   Register the service in runtime construction without coupling it to widgets.
3. **Shared style rendering and agents.** Add STYLE ordering and explicit
   precedence. Wire submission snapshots through Writer/Editor/Critic, retaining
   no-profile behavior and existing file proposal validation.
4. **Selection integration.** Capture the same snapshot in action requests;
   cover all seven actions and custom attached-passage requests. Keep exact
   selection/surroundings, strict JSON validation, and existing single-call flow.
5. **Management UI and metadata.** Add the selector/dialog, independent Selection
   visibility, scope labels, preview, restart persistence, and inspectable style
   records in chat and diagnostic steps. Verify narrow layouts and keyboard use.
6. **Acceptance and release documentation.** Run subsystem/full tests and wheel
   checks; evaluate prose with configured providers; update user docs, screenshots,
   package metadata, and v0.7.0-alpha release notes. Mark complete only after
   maintainer Windows acceptance under the main guide's release rules.

Each step must leave runnable, reviewable code. The first complete vertical
slice is selecting a persisted profile, submitting Rewrite Selection, inspecting
the captured style, and accepting/undoing the reviewed result. Finish the rest
of the workflow matrix before calling the feature implemented.

## Automated verification

Add `tests/style_profiles/` for migration, repository, resolution, and rendering
coverage. Extend the existing agent, selection, diagnostics, and Qt suites.
Use temporary databases/projects and fake completions for the automated gate.

- Upgrade and repeated migration preserve existing schema-5 data; database
  failures roll back atomically. Global/project scope and foreign IDs are tested.
- Create/edit/duplicate/archive/restore/delete persist; stale saves fail; deleting
  a project leaves global profiles and other projects intact.
- Inherit, explicit none, missing/archived selection, no project, restart, and
  global-default changes resolve as specified without cross-project leakage.
- All Writer stages retain one content hash even when the profile changes
  between calls. Profile deletion after submission also preserves the snapshot.
- Style content appears exactly once and in stable order. No-profile prompts
  match characterization fixtures. Critic/evaluator receive evaluation wording.
- Provider delivery tests preserve the style layer across existing supported
  adapters without adding provider-specific profile logic.
- Parameterize all mutating selection actions plus Critique and both custom
  result kinds. Verify exact passage/context, snapshot ownership, profile edits
  during a delayed call, and tone/task precedence instructions.
- Selection changes still require inline review. Critique cannot produce edits;
  stale/canceled/invalid/truncated/error replies leave the document untouched.
  Accepted changes retain draft Undo/Redo or saved-file history as appropriate.
- UI tests cover visible style in Selection mode, scope selection, canceled
  dialog edits, restart, project changes, and long names in a narrow composer.
- Chat and diagnostic reload preserve style metadata; capture-off tests assert
  that distinctive example/instruction text never appears in diagnostic content
  or metadata. Editing/deleting a profile does not rewrite historical records.

Prompt tests verify delivery and precedence wording, not subjective prose
quality. The acceptance exercise below evaluates whether those rules work with
actual providers. Run relevant suites and then the full supported suite using
the existing Windows temporary-directory workaround:

```powershell
$env:TEMP = Join-Path (Get-Location) 'build'
$env:TMP = $env:TEMP
.\Scripts\python.exe -B -u -m pytest -q tests/style_profiles tests/agent_workflows tests/editor_workspace tests/project_system tests/diagnostics tests/context_engine tests/llm_tests/test_system_prompt_delivery.py --basetemp=.pytest_cache/style-subsystems
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/style-full
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/style-wheel
```

The profile suite is implemented in `tests/style_profiles/`. Installed-wheel
profile/migration checks extend `tests/diagnostics/check_packaged_diagnostics.py`;
`tests/editor_workspace/check_packaged_tabs.py` also runs the profile UI tests
against the installed package. Safe review/history checks remain in
`tests/change_sets/check_packaged_review.py`.

## Windows and writing-quality acceptance

- [ ] Create two contrasting profiles (for example, restrained concrete prose
  and expansive sensory prose) with the same short story fixture. Compare both
  profiles and no-profile results against a written brief.
- [ ] Exercise Writer's three stages and Editor with explicit file requests.
  Check voice, facts, character distinctions, task compliance, and final proposals.
- [ ] Try every story action under both profiles; include a tone request that
  conflicts with a saved preference, a deliberately narrow editing request,
  custom feedback, and custom revision. Critique remains read-only.
- [ ] Confirm approving/rejecting hunks, Undo/Redo, unsaved drafts, cancellation,
  tab/project switches, and stale-document protection with an active profile.
- [ ] Edit/switch/archive/delete a profile during a delayed request. Verify that
  the pending result identifies its original profile and the next request uses
  the new resolved selection.
- [ ] Verify global/project inheritance, explicit none, project removal, restart,
  long names, narrow layouts, keyboard navigation, and Windows display scaling.
- [ ] Inspect diagnostics with prompt capture on and off. Confirm that the UI
  reports which profile was used rather than displaying current profile content
  as if it were historical evidence.
- [ ] Test packaged migration on a backed-up pre-feature database and launch the
  installed build. Record provider/model/settings and qualitative findings for
  at least two configured providers where available; document remaining limits.

The selection guide, layout, agent guidance, best practices, feature overview,
installation notes, roadmap, and release notes now describe the implemented
profile behavior, model input, scope/precedence, and migration/rollback path.

## Verification record

The branch began at `67650fb`. Characterization was recorded before changing
runtime behavior: 49 baseline tests passed. No-profile prompt fingerprints remain
unchanged. The broader subsystem run passed 472 tests with one Windows symlink
skip. Initial profile verification on 2026-11-01:

- Full supported suite: **605 passed, 1 skipped, 16 deselected**, 121.43 seconds.
  The skip is unavailable Windows symlink creation; external/model tests remain
  excluded by the standard configuration. Two existing dependency deprecation
  warnings remain.
- Offline wheel build: `sammyai-0.7.0a0-py3-none-any.whl`.
- Isolated installed-package diagnostics/profile migration, three-stage Writer
  style delivery, deletion/snapshot retention, and safe review/history checks
  passed with network access blocked in the checks.
- Installed-package editor/profile UI checks: **28 passed**. Application code,
  theme, and icons came from the wheel; Qt/test dependencies were reused from
  the development environment.
- Eighty Markdown links checked across changed/new documentation; local targets
  and code fences passed. `git diff --check` passed.

Final verification commands (with TEMP/TMP set to workspace `build` as above):

```powershell
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/style-full-final --tb=short
.\Scripts\python.exe -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/style-wheel-final
.\Scripts\python.exe -B -u tests/diagnostics/check_packaged_diagnostics.py build/style-wheel-final/sammyai-0.7.0a0-py3-none-any.whl
.\Scripts\python.exe -B -u tests/editor_workspace/check_packaged_tabs.py build/style-wheel-final/sammyai-0.7.0a0-py3-none-any.whl
.\Scripts\python.exe -B -u tests/change_sets/check_packaged_review.py build/style-wheel-final/sammyai-0.7.0a0-py3-none-any.whl
```

Offscreen Qt previews with Windows fonts were inspected for the profile editor,
manager, selected-passage composer, and long profile names in a narrow window.
Theme and elision issues found during inspection were corrected. The screenshots
in the user guide come from temporary synthetic projects with a fake provider.

The maintainer's existing OpenAI key was checked without displaying its value:
the Windows user environment value matches the application's saved key, and
an authentication-only models request returned HTTP 200. Automated feature tests
use fake completions; this authentication check does not establish writing quality.
Subsequent maintainer prose comparisons are recorded below. The broader
real-project Windows checklist above remains open for unreported checks.

Reproduce the isolated UI preview with:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\Scripts\python.exe -B -u tests/editor_workspace/preview_writer_styles.py --capture build/style-preview
```

Omit `--capture` to open the isolated interactive demo. It uses temporary data
and a fake provider, preserving the user's writing projects and application data.

## OpenAI compatibility follow-up

The maintainer's manual comparison found that `gemma4:31b` followed the profile
and reduced more writing tics after story-focused selection edits. The Luna run
failed before generation: the saved 2026-11-01 diagnostic identified
`max_tokens: null` as an invalid request parameter. The unconditional OpenAI
argument was already present at the branch baseline.

`llm/openai_parameters.py` now owns the OpenAI generation-parameter policy.
Unset values are omitted. GPT-5/GPT-6 and o1/o3/o4 families, including dated and
fine-tuned variants, use `max_completion_tokens` for explicit limits and leave
reasoning/sampling at provider defaults. Temperature, top-p, and seed are
omitted for those families. This conservative policy also omits sampling for
variants that could accept it with effort `none`; SammyAI does not currently
offer a reasoning-effort control. Older and unrecognized models retain legacy
parameter names and configured sampling. Other provider adapters are unchanged.

The policy follows OpenAI's [token-limit reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
and [reasoning/sampling compatibility guidance](https://developers.openai.com/api/docs/guides/latest-model).
Future families need an explicit policy review. Requests keep the selected model
and complete style prompt; errors do not trigger model fallback or prompt removal.
`effective_settings` contains only generation overrides sent to OpenAI.

Regression tests exercise real SDK JSON serialization through an offline HTTP
transport, including every Writer stage, Editor, and all selection actions.
They cover the original null-field defect, explicit limits, configured sampling
on older models, preserved HTTP errors, truncated selection responses, and
diagnostic privacy/settings. Existing UI tests cover review and Undo/Redo.

Follow-up verification on 2026-11-01:

- The Luna request regression failed against the old adapter, exposing the
  serialized null token limit and sampling overrides before the fix.
- Full supported suite: **647 passed, 1 skipped, 16 deselected**, 178.40 seconds.
  All 42 new adapter regressions ran. The existing Windows symlink skip and two
  dependency deprecation warnings remain.
- Offline wheel: `build/openai-wheel/sammyai-0.7.0a0-py3-none-any.whl`.
  Its adapter and parameter-policy files match the tested source.
- Changed documentation links and code fences passed validation;
  `git diff --check` passed. No live generation requests were made for this fix.

```powershell
.\Scripts\python.exe -B -u -m pytest -q --basetemp=.pytest_cache/openai-full --tb=short
.\Scripts\python.exe -B -m pip wheel . --no-deps --no-build-isolation --no-index --wheel-dir build/openai-wheel
```

## Maintainer writing-test results — v0.7.0-alpha

After the adapter fix, the maintainer confirmed that `gpt-6-luna` completes the
task and makes the requested style changes, joining the successful `gemma4:31b`
test. Both models left several unwanted writing habits after an initial
whole-story edit. Smaller, specific adjustments through story-focused selection
actions produced the requested fixes. These are qualitative observations from
the Shelf Life comparison, not measured elimination rates or a guarantee across
stories. The maintainer will continue monitoring with more examples.

The Luna runtime failure is resolved in the reported manual test. The broader
Windows checklist remains open wherever individual checks have not been reported.
Retain this procedure for further model comparisons:

1. Restart SammyAI from this branch, select `gpt-6-luna`, and confirm Shelf Life
   inherits the intended global style.
2. Repeat the Editor revision into `shelf_life_draft_style.md` and a short Writer
   request. Check that every stage completes and identifies the captured style.
3. Exercise Rewrite, Tighten, Expand, Improve Dialogue, Change Tone, Continue,
   Critique, and custom selection requests. Review proposed edits before applying;
   Critique and custom feedback should remain read-only.
4. Compare prose against `shelf_life_draft.md`, record remaining tics, and check
   diagnostics for the actual model, style revision, and effective settings.
