from PySide6.QtWidgets import QApplication

from editing.change_set_viewer import ChangeSetReviewDialog
from editing.change_sets import (
    ChangeSetPreview,
    FileChangeKind,
    FileChangePreview,
)


def test_change_set_review_dialog_lists_and_switches_file_diffs():
    app = QApplication.instance() or QApplication([])
    preview = ChangeSetPreview(
        change_set_id="change-1",
        description="Revise two chapters",
        files=(
            FileChangePreview(
                relative_path="one.md",
                kind=FileChangeKind.UPDATE,
                unified_diff="--- a/one.md\n+++ b/one.md\n@@ -1 +1 @@\n-old\n+new",
                additions=1,
                deletions=1,
            ),
            FileChangePreview(
                relative_path="two.md",
                kind=FileChangeKind.CREATE,
                unified_diff="--- a/two.md\n+++ b/two.md\n@@ -0,0 +1 @@\n+new",
                additions=1,
                deletions=0,
            ),
        ),
    )
    dialog = ChangeSetReviewDialog(preview)

    assert dialog.file_list.count() == 2
    assert "+2 -1" in dialog.summary_label.text()
    assert "a/one.md" in dialog.diff_view.toPlainText()

    dialog.file_list.setCurrentRow(1)
    app.processEvents()
    assert "a/two.md" in dialog.diff_view.toPlainText()

    dialog.close()
    app.processEvents()
