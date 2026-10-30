# Revising files with agents

In SammyAI v0.6.2-alpha, Brainstormer, Writer and Editor can propose coordinated
revisions in several parts of a file. Reference the file explicitly and describe
the intended changes:

> Update the character setup, Act One, Act Two and Act Three in @pilot_outline.md
> using the four changes we agreed on. Preserve unrelated passages and show me
> the proposed edits for review.

For revisions to existing passages, agents can return the old passages and their
replacements. SammyAI locates them in the original file and combines the changes
into one review. It does not need the agent to reproduce the entire document.
Full rewrites and new files are also supported when explicitly requested.

You do not need to write JSON or special markers in your request. Updated agent
instructions use ordinary text blocks for file content, so quotation marks,
backslashes and paragraph breaks do not need JSON escaping. Existing JSON
proposals remain supported for compatibility.

## Review and source checks

- Replacements must match unique passages in the file context supplied for that
  request. Matching preserves spaces and punctuation; Windows and Unix line
  endings are treated equivalently for locating passages.
- Several replacements refer to the same original file. They must not overlap.
  A replacement cannot target text introduced by another replacement in that run.
- If only part of a large file was supplied, the agent can replace fully visible
  passages. Unseen text cannot be replaced, and a whole-file rewrite still
  requires complete file context.
- Unchanged text is preserved. New replacement text uses the source file's line
  ending style. Current project, path and source-version checks still apply.
- All proposals go through [diff review](5_Diff_Edits_Menu_Options.md). Accept or
  reject individual changes, then apply. Nothing is written during generation
  or proposal parsing. Accepted changes support undo and redo.

Assistant and Critic remain read-only. Writer keeps the original file snapshot
through drafting, evaluation and revision.

## Writer file requests

Name the destination and the operation you want, for example:

> Use @story_outline.md to write Scene 1, then append it to @story_draft.md.

An empty Markdown or text file is a valid append destination. You do not need to
add a placeholder sentence first. Writer carries the requested destination and
operation through drafting, evaluation and revision. Intermediate drafts have
not been saved: the final append proposal must contain the complete revised new
scene, not a replacement for a sentence that exists only in the generated draft.

SammyAI checks the final proposal against the request and any validated draft
proposal. A changed operation, changed or missing destination, missing proposal,
or invalid source edit cannot proceed to review. A failed file request starts
its saved reply with **"Writer could not prepare the requested file change.
No files were changed."** Any remaining model prose is labeled as unapplied.
The failure remains visible when the chat is reopened, including after diagnostic
retention removes the detailed trace. Regenerate the request after checking the
reason in diagnostics.

Writer still uses three model calls. It does not retry automatically, reinterpret
an invalid replacement as an append, or apply an intermediate draft. A valid final
proposal still requires your normal inline review and acceptance.

## If a proposal is rejected

An ambiguous search needs a longer exact passage, usually including a nearby
heading or distinctive sentence. A missing search may mean the agent paraphrased
the original text or used an earlier draft. Ask it to reference the current file
and copy the target exactly. If the file changed while the agent was working,
request a fresh proposal.

Malformed or incomplete text blocks and provider-reported truncated responses
are rejected. This format removes JSON escaping as a requirement for writing;
it cannot guarantee that a model always follows the format or makes good edits.
Review remains necessary.

[Diagnostics](9_Chat_Agent_Diagnostics.md) records the proposal format (`text-v2`
or legacy `json-v1`) and operations. Enable failed-proposal capture before
reproducing a problem to retain the rejected response locally. The new format
does not require additional model calls or any capture setting to be enabled.
