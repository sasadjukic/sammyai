# Strategic Roadmap and Planned Updates

This roadmap outlines likely focus areas after V0.4.1-alpha. Priorities may change based on testing, user feedback, model behavior, and stability work.

> [!NOTE]
> V0.4.1-alpha introduced project architecture, automatic context synchronization, reviewed change sets, agent workflows, persistent memory, and a redesigned chat UI. The next phase is about hardening and improving those systems.

## 1. Reliability and Validation

* **Long-form stress testing:** Validate project context, memory, and editing workflows across novels, screenplays, series bibles, and multi-chapter drafts.
* **Regression coverage:** Expand tests around project sync, memory injection, conflict handling, and agent output parsing.
* **Recovery paths:** Continue improving rollback, stale-content handling, and clear error messages.

## 2. Agent Workflow Quality

* **Writer workflow tuning:** Improve draft, evaluation, and revision behavior.
* **Editor reliability:** Make structured file proposals more consistent and easier to review.
* **Critic depth:** Improve feedback quality for plot, character, pacing, continuity, and prose.
* **Prompt layering:** Refine provider-neutral instructions for different model families.

## 3. Context and Memory Improvements

* **Retrieval quality:** Improve relevance ranking and context budgeting.
* **Memory review:** Make memory suggestions easier to approve, edit, archive, and search.
* **Project summaries:** Improve conversation summaries and source provenance.
* **Large project handling:** Continue testing large projects with many files and long histories.

## 4. User Experience

* **Workflow clarity:** Improve labels, status messages, and review dialogs.
* **Project Explorer polish:** Continue refining navigation and file-state feedback.
* **Documentation updates:** Keep user guides aligned as V0.4.1-alpha workflows stabilize.

## 5. Format and Provider Support

* **Editable formats:** Evaluate additional import or export paths while keeping `.txt` and `.md` as the safest editing targets.
* **Provider compatibility:** Continue making model configuration flexible as providers change model IDs and APIs.
