"""Writer-style controls and local profile editing; no model calls in this UI."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QSplitter, QVBoxLayout, QWidget,
    QStyle, QStyleOptionComboBox, QStylePainter,
)

from sammyai_core.style_profiles import (
    EXAMPLE_LIMIT, INSTRUCTION_LIMIT, NAME_LIMIT, StyleProfileSnapshot, StyleSelection,
)


def style_label(snapshot):
    return f"{snapshot.name} ({'project' if snapshot.project_id else 'global'})" if snapshot else "No style profile"


class StyleComboBox(QComboBox):
    def paintEvent(self, event):
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        field = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField, self)
        # Leave room for native/stylesheet padding as well as the arrow.
        width = min(field.width() - 24, self.width() - 70)
        option.currentText = self.fontMetrics().elidedText(option.currentText, Qt.ElideRight, max(0, width))
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.CC_ComboBox, option)
        painter.drawControl(QStyle.CE_ComboBoxLabel, option)


class StyleProfileEditor(QDialog):
    """Save only on acceptance, including previews of unsaved local edits."""

    def __init__(self, service, project_id, profile=None, parent=None):
        super().__init__(parent)
        self.setProperty("styleProfileDialog", True)
        self.service, self.profile = service, profile
        self.saved_profile = None
        self.setWindowTitle("Edit style profile" if profile else "Create style profile")
        self.resize(660, 670)
        layout = QVBoxLayout(self)
        intro = QLabel("Describe repeatable writing preferences. Start with 5–8 concrete rules, then test them on the same short passage.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.name_edit = QLineEdit(profile.name if profile else "")
        form.addRow(f"Name (up to {NAME_LIMIT} characters)", self.name_edit)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("Global — available across projects", None)
        if project_id:
            self.scope_combo.addItem("This project", project_id)
        scope = profile.project_id if profile else project_id
        self.scope_combo.setCurrentIndex(max(0, self.scope_combo.findData(scope)))
        self.scope_combo.setEnabled(profile is None)
        form.addRow("Scope", self.scope_combo)
        layout.addLayout(form)
        self.instructions_edit = QPlainTextEdit(profile.instructions if profile else "")
        self.instructions_edit.setAccessibleName("Style instructions")
        self.instructions_edit.setPlaceholderText(
            "Voice: direct and observant.\nRhythm: mostly short sentences; vary length when a thought needs room.\n"
            "Detail: choose specific objects and actions before abstract emotion.\nDialogue: preserve each character's diction.\n"
            "Avoid: stock metaphors, repeated explanations, and forced cliffhangers.")
        layout.addWidget(QLabel(f"Instructions — up to {INSTRUCTION_LIMIT:,} characters"))
        layout.addWidget(self.instructions_edit, 2)
        self.examples_edit = QPlainTextEdit(profile.examples if profile else "")
        self.examples_edit.setAccessibleName("Approved examples")
        self.examples_edit.setPlaceholderText("Optional: a short excerpt you approve, followed by what it demonstrates. Examples guide technique, not story facts.")
        layout.addWidget(QLabel(f"Approved examples — optional, up to {EXAMPLE_LIMIT:,} characters"))
        layout.addWidget(self.examples_edit, 1)
        note = QLabel("Global edits affect future requests in every project using this profile. Current requests keep their original style." if profile and profile.project_id is None else
                      "Your current request takes priority over conflicting preferences. Saving never rewrites a document.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.preview_button = buttons.addButton("Preview", QDialogButtonBox.ActionRole)
        self.preview_button.clicked.connect(self.preview)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _values(self):
        return {"name": self.name_edit.text(), "instructions": self.instructions_edit.toPlainText(),
                "examples": self.examples_edit.toPlainText()}

    def preview(self):
        try:
            snapshot = StyleProfileSnapshot("preview", self.scope_combo.currentData(), revision=1, **self._values())
            dialog = QDialog(self)
            dialog.setProperty("styleProfileDialog", True)
            dialog.setWindowTitle("Style preview — next writing request")
            dialog.resize(650, 520)
            layout = QVBoxLayout(dialog)
            text = QPlainTextEdit(
                f"{style_label(snapshot)}\n\nInstructions\n{snapshot.instructions}\n\n"
                f"Approved examples\n{snapshot.examples or '(none)'}\n\n"
                "Your current request takes priority over conflicting preferences. Required document formatting and review rules still apply. "
                "Critiques assess this style without adopting its voice. Examples guide technique and do not add facts to your story.")
            text.setReadOnly(True)
            layout.addWidget(text)
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            dialog.exec()
        except ValueError as error:
            QMessageBox.warning(self, "Style profile", str(error))

    def save(self):
        try:
            if self.profile:
                self.saved_profile = self.service.repository.update(self.profile.id, expected_revision=self.profile.revision, **self._values())
            else:
                self.saved_profile = self.service.repository.create(project_id=self.scope_combo.currentData(), **self._values())
        except Exception as error:
            QMessageBox.warning(self, "Could not save style", str(error))
            return
        self.accept()


class StyleProfilesDialog(QDialog):
    def __init__(self, service, project_id, parent=None):
        super().__init__(parent)
        self.setProperty("styleProfileDialog", True)
        self.service, self.project_id = service, project_id
        self.setWindowTitle("Manage writer styles")
        self.resize(780, 540)
        layout = QVBoxLayout(self)
        help_text = QLabel("Create a personal style, add short examples, and select it for future writing requests. Duplicate a profile to experiment without changing the original.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.show_archived = QCheckBox("Show archived profiles")
        self.show_archived.toggled.connect(self.refresh)
        layout.addWidget(self.show_archived)
        splitter = QSplitter()
        self.profiles = QListWidget()
        self.profiles.setAccessibleName("Writer style profiles")
        self.profiles.currentItemChanged.connect(self.show_profile)
        self.profiles.itemDoubleClicked.connect(lambda *_: self.edit())
        splitter.addWidget(self.profiles)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("Profile preview")
        splitter.addWidget(self.detail)
        splitter.setSizes([260, 440])
        layout.addWidget(splitter, 1)
        actions = QHBoxLayout()
        self.buttons = {}
        for label, callback in (("New…", self.create), ("Edit…", self.edit), ("Duplicate…", self.duplicate),
                                ("Archive", self.archive), ("Delete…", self.delete), ("Use style", self.use)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
            self.buttons[label] = button
        layout.addLayout(actions)
        bottom = QDialogButtonBox(QDialogButtonBox.Close)
        self.default_button = bottom.addButton("Set global default", QDialogButtonBox.ActionRole)
        self.default_button.clicked.connect(self.set_default)
        clear_default = bottom.addButton("Clear global default", QDialogButtonBox.ActionRole)
        clear_default.clicked.connect(lambda: self._mutate(lambda: self.service.select(None, StyleSelection())))
        bottom.rejected.connect(self.reject)
        layout.addWidget(bottom)
        self.refresh()

    def current(self):
        item = self.profiles.currentItem()
        return self.service.repository.get(item.data(Qt.UserRole)) if item else None

    def refresh(self, *_):
        current = self.current()
        self.profiles.clear()
        for profile in self.service.repository.list(self.project_id, include_archived=self.show_archived.isChecked()):
            item = QListWidgetItem(f"{profile.name} ({'project' if profile.project_id else 'global'})" + (" — archived" if profile.archived else ""))
            item.setData(Qt.UserRole, profile.id)
            self.profiles.addItem(item)
            if current and profile.id == current.id:
                self.profiles.setCurrentItem(item)
        if self.profiles.currentRow() < 0:
            self.profiles.setCurrentRow(0)
        self.show_profile()

    def show_profile(self, *_):
        profile = self.current()
        self.detail.setPlainText(f"{profile.name}\nRevision {profile.revision}\n\n{profile.instructions}\n\nApproved examples\n{profile.examples or '(none)'}" if profile else "Create your first style profile to get started.")
        for label, button in self.buttons.items():
            button.setEnabled(label == "New…" or profile is not None)
        self.buttons["Use style"].setEnabled(bool(profile and not profile.archived))
        self.buttons["Archive"].setText("Restore" if profile and profile.archived else "Archive")
        self.default_button.setEnabled(bool(profile and not profile.archived and profile.project_id is None))

    def create(self):
        StyleProfileEditor(self.service, self.project_id, parent=self).exec()
        self.refresh()

    def edit(self):
        if profile := self.current():
            StyleProfileEditor(self.service, self.project_id, profile, self).exec()
            self.refresh()

    def duplicate(self):
        if profile := self.current():
            # The editor lets the user choose the destination scope before saving.
            editor = StyleProfileEditor(self.service, self.project_id, parent=self)
            editor.name_edit.setText(profile.name[:NAME_LIMIT - 7] + " (copy)")
            editor.instructions_edit.setPlainText(profile.instructions)
            editor.examples_edit.setPlainText(profile.examples)
            editor.exec()
            self.refresh()

    def _mutate(self, callback):
        try:
            callback()
            self.refresh()
            return True
        except Exception as error:
            QMessageBox.warning(self, "Style profile", str(error))
            return False

    def archive(self):
        if profile := self.current():
            self._mutate(lambda: self.service.repository.archive(profile.id, expected_revision=profile.revision, archived=not profile.archived))

    def delete(self):
        if (profile := self.current()) and QMessageBox.question(
            self, "Delete style profile", f'Permanently delete “{profile.name}”? Projects selecting it will use no profile. Existing requests and history are preserved.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) == QMessageBox.Yes:
            self._mutate(lambda: self.service.repository.delete(profile.id, expected_revision=profile.revision))

    def use(self):
        if profile := self.current():
            if self._mutate(lambda: self.service.select(self.project_id, StyleSelection("profile", profile.id))):
                self.accept()

    def set_default(self):
        if profile := self.current():
            self._mutate(lambda: self.service.select(None, StyleSelection("profile", profile.id)))


class StyleProfileController:
    def __init__(self, window, service):
        self.window, self.service = window, service
        self.panel = None

    def bind_panel(self, panel):
        self.panel = panel
        panel.style_combo.currentIndexChanged.connect(self.select)
        panel.manage_styles_button.clicked.connect(self.manage)
        self.refresh()

    def capture(self, project_id):
        if not self.service:
            return None
        resolved = self.service.resolve(project_id)
        if resolved.notice:
            self.window._chat_panel_safe("add_system_message", resolved.notice)
        return resolved.snapshot

    def refresh(self):
        if not self.panel:
            return
        combo = self.panel.style_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.setEnabled(self.service is not None)
            self.panel.manage_styles_button.setEnabled(self.service is not None)
            combo.addItem("No style profile", StyleSelection())
            if not self.service:
                combo.setToolTip("Writer styles are unavailable because the project database is not initialized.")
                return
            project_id = self.window._active_chat_project_id()
            resolved = self.service.resolve(project_id)
            if project_id:
                default = self.service.resolve().snapshot
                combo.addItem("Use global default — " + style_label(default), StyleSelection("inherit"))
            for profile in self.service.repository.list(project_id):
                combo.addItem(style_label(profile.snapshot()), StyleSelection("profile", profile.id))
            for index in range(combo.count()):
                combo.setItemData(index, combo.itemText(index), Qt.ToolTipRole)
                if combo.itemData(index) == resolved.selection:
                    combo.setCurrentIndex(index)
            combo.setToolTip("Next request: " + style_label(resolved.snapshot) +
                             "\nUsed by Writer, Editor and selection edits; assessed by critiques. Assistant and Brainstormer keep their existing behavior.")
            if resolved.notice:
                self.window._chat_panel_safe("add_system_message", resolved.notice)
        except Exception:
            combo.clear()
            combo.addItem("Styles unavailable")
            combo.setEnabled(False)
            self.window._chat_panel_safe("add_system_message", "Could not load writer styles. Reopen the project or check the database before sending a styled request.")
        finally:
            combo.blockSignals(False)

    def select(self, index):
        selection = self.panel.style_combo.itemData(index)
        if self.service and isinstance(selection, StyleSelection):
            try:
                self.service.select(self.window._active_chat_project_id(), selection)
            except Exception as error:
                QMessageBox.warning(self.window, "Could not select style", str(error))
            self.refresh()

    def manage(self):
        if self.service:
            StyleProfilesDialog(self.service, self.window._active_chat_project_id(), self.window).exec()
            self.refresh()
