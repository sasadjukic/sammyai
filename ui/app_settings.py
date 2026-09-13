"""Application preferences entry point; existing model controls remain reusable."""
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QGroupBox,
                               QLabel, QMessageBox, QPushButton, QVBoxLayout)


class AppSettingsDialog(QDialog):
    def __init__(self, hub, open_model_settings, parent=None):
        super().__init__(parent)
        self.hub = hub
        self.setObjectName('appSettingsDialog')
        self.setWindowTitle('SammyAI Settings')
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        writing = QGroupBox('Writing')
        section = QVBoxLayout(writing)
        self.spell_check = QCheckBox('Enable spell check')
        self.spell_check.setChecked(hub.service.enabled)
        section.addWidget(self.spell_check)
        section.addWidget(QLabel('Language: English (United States)'))
        detail = QLabel('Applies to all document tabs and the chat composer.\nPersonal dictionary words are shared across projects.')
        detail.setWordWrap(True)
        section.addWidget(detail)
        layout.addWidget(writing)
        model = QPushButton('LLM settings…')
        model.clicked.connect(open_model_settings)
        layout.addWidget(model)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            self.hub.change('set_enabled', self.spell_check.isChecked())
        except OSError as error:
            QMessageBox.warning(self, 'Settings', f'Could not save settings: {error}')
            return
        self.accept()
