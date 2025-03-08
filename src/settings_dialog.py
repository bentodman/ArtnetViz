#!/usr/bin/env python3
"""
Advanced Settings Dialog for ArtNetViz

This module provides a UI dialog for configuring advanced application settings
that require a restart to take effect, such as network settings and test source
configuration. Regular visualization settings are managed directly in the main UI.
"""

import os
import yaml
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox, 
    QComboBox, QCheckBox, QGroupBox, QPushButton, QTabWidget,
    QListWidget, QListWidgetItem, QDoubleSpinBox, QFormLayout,
    QMessageBox, QWidget
)
from PyQt6.QtCore import Qt

class SettingsDialog(QDialog):
    """
    Advanced settings dialog for configuring ArtNetViz settings that require a restart.
    Regular visualization settings are managed directly in the main window.
    """
    
    def __init__(self, config=None, parent=None):
        """Initialize the settings dialog with existing config if available."""
        super().__init__(parent)
        self.setWindowTitle("ArtNetViz Advanced Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        
        # Load default config if none provided
        self.config = config or self._get_default_config()
        
        # Initialize UI
        self._init_ui()
        
        # Load config values into UI
        self._load_config_into_ui()
    
    def _init_ui(self):
        """Initialize the UI components."""
        # Main layout
        layout = QVBoxLayout(self)
        
        # Tab widget to organize settings
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # ArtNet settings tab
        artnet_tab = QWidget()
        artnet_layout = QFormLayout(artnet_tab)
        
        # Network settings
        network_group = QGroupBox("Network Settings")
        network_layout = QFormLayout(network_group)
        
        self.host_input = QLineEdit()
        network_layout.addRow("Host (IP Address):", self.host_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(6454)  # Default ArtNet port
        network_layout.addRow("Port:", self.port_input)
        
        artnet_layout.addRow("", network_group)
        
        # Note about universes
        note_label = QLabel(
            "<i>Note: Universe settings can be managed directly in the main window.</i>"
        )
        note_label.setWordWrap(True)
        artnet_layout.addRow("", note_label)
        
        tabs.addTab(artnet_tab, "ArtNet Network")
        
        # Test Source tab
        test_tab = QWidget()
        test_layout = QFormLayout(test_tab)
        
        self.test_source_enabled = QCheckBox("Enable Test Source")
        test_layout.addRow("", self.test_source_enabled)
        
        test_info_label = QLabel(
            "When enabled, the application will generate test patterns instead of listening for real Art-Net data."
        )
        test_info_label.setWordWrap(True)
        test_layout.addRow("", test_info_label)
        
        self.pattern_combo = QComboBox()
        self.pattern_combo.addItems([
            "GRADIENT_H", "GRADIENT_V", "CHECKERBOARD", "MOVING_BAR_H",
            "MOVING_BAR_V", "PULSE", "RANDOM", "SINE_WAVE"
        ])
        test_layout.addRow("Pattern:", self.pattern_combo)
        
        self.speed_input = QDoubleSpinBox()
        self.speed_input.setRange(0.1, 10.0)
        self.speed_input.setSingleStep(0.1)
        self.speed_input.setValue(1.0)
        test_layout.addRow("Speed:", self.speed_input)
        
        tabs.addTab(test_tab, "Test Source")
        
        # Restart note
        restart_note = QLabel(
            "<b>Note:</b> Changes to these settings require restarting the application to take effect."
        )
        restart_note.setWordWrap(True)
        restart_note.setStyleSheet("color: #CF6679;")
        layout.addWidget(restart_note)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(save_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
    
    def _add_universe(self):
        """Add a universe to the list."""
        universe = self.add_universe_input.value()
        
        # Check if this universe is already in the list
        for i in range(self.universes_list.count()):
            if self.universes_list.item(i).text() == str(universe):
                return  # Universe already in list
        
        # Add to the list
        self.universes_list.addItem(QListWidgetItem(str(universe)))
    
    def _remove_universe(self):
        """Remove the selected universe from the list."""
        selected_items = self.universes_list.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            self.universes_list.takeItem(self.universes_list.row(item))
    
    def _load_config_into_ui(self):
        """Load configuration values into UI components."""
        # ArtNet Settings
        artnet_config = self.config.get('artnet', {})
        self.host_input.setText(artnet_config.get('host', '0.0.0.0'))
        self.port_input.setValue(artnet_config.get('port', 6454))
        
        # Test Source Settings
        test_config = self.config.get('test_source', {})
        self.test_source_enabled.setChecked(test_config.get('enabled', False))
        
        pattern = test_config.get('pattern', 'MOVING_BAR_H')
        index = self.pattern_combo.findText(pattern)
        if index >= 0:
            self.pattern_combo.setCurrentIndex(index)
            
        self.speed_input.setValue(test_config.get('speed', 1.0))
    
    def _save_settings(self):
        """Save the settings from UI to the config dictionary."""
        # ArtNet settings
        if 'artnet' not in self.config:
            self.config['artnet'] = {}
        
        self.config['artnet']['host'] = self.host_input.text()
        self.config['artnet']['port'] = self.port_input.value()
        
        # Preserve existing universes
        if 'universes' not in self.config['artnet']:
            self.config['artnet']['universes'] = [0]  # Default
        
        # Test source settings
        if 'test_source' not in self.config:
            self.config['test_source'] = {}
        
        self.config['test_source']['enabled'] = self.test_source_enabled.isChecked()
        self.config['test_source']['pattern'] = self.pattern_combo.currentText()
        self.config['test_source']['speed'] = self.speed_input.value()
        
        # Accept the dialog
        self.accept()
    
    def get_config(self):
        """Get the current configuration."""
        return self.config
    
    def _get_default_config(self):
        """Get default configuration values."""
        return {
            'artnet': {
                'host': '0.0.0.0',
                'port': 6454,
                'universes': [0, 1]
            },
            'test_source': {
                'enabled': False,
                'pattern': 'MOVING_BAR_H',
                'speed': 1.0
            }
        }

def load_config_from_file():
    """Load configuration from the config file or return default if not found."""
    try:
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as file:
                config = yaml.safe_load(file)
            return config
        else:
            # Return None to use default config
            return None
    except Exception:
        return None 