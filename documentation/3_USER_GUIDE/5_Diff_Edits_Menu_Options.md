# Diff Review and Change-Set Options

SammyAI V0.4.1-alpha uses reviewed change sets for safer AI-assisted editing. Instead of immediately rewriting files, SammyAI can prepare a structured proposal and show the diff before you apply it.

---

## 1. Reviewed Change Sets

Change sets can include:

* File creation.
* File updates.
* File deletion.
* Character-range edits inside supported text files.

Safety features include:

* Project-root path confinement.
* Supported edit targets limited to `.md` and `.txt`.
* Hash-based stale-content conflict detection.
* Atomic writes with staged files and backups.
* Multi-file rollback if an apply step fails.
* Undo and redo for applied change sets.

## 2. Editor Agent Workflow

Use the Editor agent when you want SammyAI to propose file changes.

1. Open a project.
2. Reference the exact file that should be changed.
3. Ask for a specific edit.
4. Review the proposed change set.
5. Accept or reject the proposal.

Existing files require complete explicit file context before modification. This prevents the agent from editing a file based on stale or incomplete assumptions.

## 3. Edit > Compare and Review

The Compare and Review menu contains manual diff tools.

* **Compare with File... (Ctrl+D):** Compare the current editor text with another file.
* **Compare with Clipboard (Ctrl+Shift+D):** Compare the editor text with clipboard content.
* **Apply Diff from File...:** Load a `.diff` or `.patch` file and review it before applying.
* **Undo Last Applied Change Set:** Revert the most recent applied change set when possible.
* **Redo Last Applied Change Set:** Reapply an undone change set when possible.

## 4. Legacy DBE Mode

The old DBE toggle remains under **Advanced** as **Enable Legacy DBE Mode**. It is kept as a fallback while the newer agent and change-set pipeline is tested.

> [!TIP]
> Prefer the Editor agent and reviewed change sets for project file edits. Use manual comparison tools when you want to inspect external text or patches.
