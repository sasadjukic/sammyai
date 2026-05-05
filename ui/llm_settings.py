from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton, QWidget, QLineEdit, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QIntValidator


class LLMSettingsDialog(QDialog):
    """
    A modernized dialog to configure LLM sampling parameters (temperature, top-p, seed).
    """
    
    def __init__(self, temperature=0.9, top_p=0.9, seed=None, model_name="unknown", parent=None):
        super().__init__(parent)
        self.setObjectName("llmSettingsDialog")
        self.setWindowTitle("Model Settings")
        self.setFixedWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        self.temp_value = temperature
        self.top_p_value = top_p
        self.seed_value = seed
        self.model_name = model_name
        
        self.setup_ui()
        self._update_preset_buttons()
        
    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Panel Container
        panel = QFrame()
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setObjectName("settingsHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        title_label = QLabel("Model settings")
        title_label.setObjectName("settingsTitle")
        
        self.model_pill = QLabel(self.model_name)
        self.model_pill.setObjectName("modelPill")
        self.model_pill.setAlignment(Qt.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.model_pill)
        
        panel_layout.addWidget(header)
        
        # Body
        body = QWidget()
        body.setObjectName("settingsBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 15, 20, 15)
        body_layout.setSpacing(15)
        
        # Presets Row
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(8)
        
        self.btn_exploratory = QPushButton("Exploratory")
        self.btn_exploratory.setProperty("class", "presetBtn")
        self.btn_exploratory.setCursor(Qt.PointingHandCursor)
        self.btn_exploratory.clicked.connect(lambda: self.apply_preset("exploratory"))
        
        self.btn_balanced = QPushButton("Balanced")
        self.btn_balanced.setProperty("class", "presetBtn")
        self.btn_balanced.setCursor(Qt.PointingHandCursor)
        self.btn_balanced.clicked.connect(lambda: self.apply_preset("balanced"))
        
        self.btn_focused = QPushButton("Focused")
        self.btn_focused.setProperty("class", "presetBtn")
        self.btn_focused.setCursor(Qt.PointingHandCursor)
        self.btn_focused.clicked.connect(lambda: self.apply_preset("focused"))
        
        preset_layout.addWidget(self.btn_exploratory)
        preset_layout.addWidget(self.btn_balanced)
        preset_layout.addWidget(self.btn_focused)
        
        body_layout.addLayout(preset_layout)
        
        # Section: Core Sampling
        core_divider = QLabel("Core Sampling")
        core_divider.setProperty("class", "sectionDivider")
        body_layout.addWidget(core_divider)
        
        # Temperature
        temp_row = QVBoxLayout()
        temp_header = QHBoxLayout()
        temp_label = QLabel("Temperature")
        temp_label.setProperty("class", "paramLabel")
        self.temp_val_label = QLabel(f"{self.temp_value:.1f}")
        self.temp_val_label.setProperty("class", "paramValue")
        temp_header.addWidget(temp_label)
        temp_header.addStretch()
        temp_header.addWidget(self.temp_val_label)
        
        temp_desc = QLabel("How adventurous the model is with word choice.")
        temp_desc.setProperty("class", "paramDesc")
        
        temp_slider_row = QHBoxLayout()
        temp_min_label = QLabel("0")
        temp_min_label.setProperty("class", "rangeLabel")
        self.temp_slider = QSlider(Qt.Horizontal)
        self.temp_slider.setMinimum(0)
        self.temp_slider.setMaximum(20)
        self.temp_slider.setValue(int(self.temp_value * 10))
        self.temp_slider.valueChanged.connect(self._on_temp_changed)
        temp_max_label = QLabel("2")
        temp_max_label.setProperty("class", "rangeLabel")
        
        temp_slider_row.addWidget(temp_min_label)
        temp_slider_row.addWidget(self.temp_slider)
        temp_slider_row.addWidget(temp_max_label)
        
        temp_row.addLayout(temp_header)
        temp_row.addWidget(temp_desc)
        temp_row.addLayout(temp_slider_row)
        body_layout.addLayout(temp_row)
        
        # Top-P
        topp_row = QVBoxLayout()
        topp_header = QHBoxLayout()
        topp_label = QLabel("Top-p")
        topp_label.setProperty("class", "paramLabel")
        self.topp_val_label = QLabel(f"{self.top_p_value:.2f}")
        self.topp_val_label.setProperty("class", "paramValue")
        topp_header.addWidget(topp_label)
        topp_header.addStretch()
        topp_header.addWidget(self.topp_val_label)
        
        topp_desc = QLabel("Controls the model's overall scope of imagination.")
        topp_desc.setProperty("class", "paramDesc")
        
        topp_slider_row = QHBoxLayout()
        topp_min_label = QLabel("0")
        topp_min_label.setProperty("class", "rangeLabel")
        self.topp_slider = QSlider(Qt.Horizontal)
        self.topp_slider.setMinimum(0)
        self.topp_slider.setMaximum(20) # 0 to 1.0 with 0.05 steps -> 20 steps
        self.topp_slider.setValue(int(self.top_p_value * 20))
        self.topp_slider.valueChanged.connect(self._on_topp_changed)
        topp_max_label = QLabel("1")
        topp_max_label.setProperty("class", "rangeLabel")
        
        topp_slider_row.addWidget(topp_min_label)
        topp_slider_row.addWidget(self.topp_slider)
        topp_slider_row.addWidget(topp_max_label)
        
        topp_row.addLayout(topp_header)
        topp_row.addWidget(topp_desc)
        topp_row.addLayout(topp_slider_row)
        body_layout.addLayout(topp_row)
        
        # Section: Advanced
        adv_divider = QLabel("Advanced")
        adv_divider.setProperty("class", "sectionDivider")
        body_layout.addWidget(adv_divider)
        
        # Deterministic Seed
        seed_row = QVBoxLayout()
        seed_label = QLabel("Deterministic Seed")
        seed_label.setProperty("class", "paramLabel")
        seed_desc = QLabel("Fixed seed for reproducible writing style.")
        seed_desc.setProperty("class", "paramDesc")
        
        seed_input_row = QHBoxLayout()
        self.seed_toggle = QPushButton("Off")
        self.seed_toggle.setObjectName("seedToggle")
        self.seed_toggle.setCheckable(True)
        self.seed_toggle.setChecked(self.seed_value is not None)
        self.seed_toggle.setText("On" if self.seed_value is not None else "Off")
        self.seed_toggle.setCursor(Qt.PointingHandCursor)
        self.seed_toggle.clicked.connect(self._on_seed_toggle)
        
        self.seed_input = QLineEdit()
        self.seed_input.setObjectName("seedInput")
        self.seed_input.setPlaceholderText("e.g. 42")
        self.seed_input.setValidator(QIntValidator(0, 999999999))
        if self.seed_value is not None:
            self.seed_input.setText(str(self.seed_value))
        self.seed_input.setEnabled(self.seed_value is not None)
        
        seed_input_row.addWidget(self.seed_toggle)
        seed_input_row.addWidget(self.seed_input)
        seed_input_row.addStretch()
        
        seed_row.addWidget(seed_label)
        seed_row.addWidget(seed_desc)
        seed_row.addLayout(seed_input_row)
        body_layout.addLayout(seed_row)
        
        panel_layout.addWidget(body)
        
        # Footer
        footer = QWidget()
        footer.setObjectName("settingsFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(20, 10, 20, 10)
        
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.setObjectName("resetToDefaultsBtn")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.clicked.connect(lambda: self.apply_preset("balanced"))
        
        footer_layout.addWidget(reset_btn)
        footer_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setProperty("class", "footerBtn")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        apply_btn = QPushButton("Apply")
        apply_btn.setProperty("class", "btnPrimary")
        apply_btn.setCursor(Qt.PointingHandCursor)
        apply_btn.clicked.connect(self.accept)
        
        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(apply_btn)
        
        panel_layout.addWidget(footer)
        main_layout.addWidget(panel)

    def _on_temp_changed(self, value):
        self.temp_value = value / 10.0
        self.temp_val_label.setText(f"{self.temp_value:.1f}")
        self._update_preset_buttons()

    def _on_topp_changed(self, value):
        self.top_p_value = value / 20.0
        self.topp_val_label.setText(f"{self.top_p_value:.2f}")
        self._update_preset_buttons()

    def _on_seed_toggle(self, checked):
        self.seed_toggle.setText("On" if checked else "Off")
        self.seed_input.setEnabled(checked)
        if not checked:
            self.seed_value = None
        else:
            try:
                self.seed_value = int(self.seed_input.text()) if self.seed_input.text() else 42
                if not self.seed_input.text():
                    self.seed_input.setText("42")
            except ValueError:
                self.seed_value = 42

    def apply_preset(self, preset_name):
        if preset_name == "exploratory":
            self.temp_value = 1.3
            self.top_p_value = 0.95
        elif preset_name == "balanced":
            self.temp_value = 0.9
            self.top_p_value = 0.9
        elif preset_name == "focused":
            self.temp_value = 0.5
            self.top_p_value = 0.7
            
        self.temp_slider.blockSignals(True)
        self.topp_slider.blockSignals(True)
        self.temp_slider.setValue(int(self.temp_value * 10))
        self.topp_slider.setValue(int(self.top_p_value * 20))
        self.temp_slider.blockSignals(False)
        self.topp_slider.blockSignals(False)
        
        self.temp_val_label.setText(f"{self.temp_value:.1f}")
        self.topp_val_label.setText(f"{self.top_p_value:.2f}")
        self._update_preset_buttons()

    def _update_preset_buttons(self):
        # Update active state for buttons
        is_exploratory = abs(self.temp_value - 1.3) < 0.01 and abs(self.top_p_value - 0.95) < 0.01
        is_balanced = abs(self.temp_value - 0.9) < 0.01 and abs(self.top_p_value - 0.9) < 0.01
        is_focused = abs(self.temp_value - 0.5) < 0.01 and abs(self.top_p_value - 0.7) < 0.01
        
        self.btn_exploratory.setProperty("active", is_exploratory)
        self.btn_balanced.setProperty("active", is_balanced)
        self.btn_focused.setProperty("active", is_focused)
        
        # Refresh styles to pick up the [active="true"] selector
        self.btn_exploratory.style().unpolish(self.btn_exploratory)
        self.btn_exploratory.style().polish(self.btn_exploratory)
        self.btn_balanced.style().unpolish(self.btn_balanced)
        self.btn_balanced.style().polish(self.btn_balanced)
        self.btn_focused.style().unpolish(self.btn_focused)
        self.btn_focused.style().polish(self.btn_focused)

    def get_values(self):
        """Returns (temperature, top_p, seed)"""
        seed = None
        if self.seed_toggle.isChecked():
            try:
                seed = int(self.seed_input.text())
            except ValueError:
                seed = 42
        return self.temp_value, self.top_p_value, seed
