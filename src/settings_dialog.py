#!/usr/bin/env python3
"""
Settings Dialog for ArtNetViz

This module provides a UI dialog for configuring the application, replacing
the need for manual editing of the config.yaml file.
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
    Settings dialog for configuring ArtNetViz without needing a config file.
    """
    
    def __init__(self, config=None, parent=None):
        """Initialize the settings dialog with existing config if available."""
        super().__init__(parent)
        self.setWindowTitle("ArtNetViz Settings")
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
        
        # ArtNet settings
        self.host_input = QLineEdit()
        artnet_layout.addRow("Host (IP Address):", self.host_input)
        
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(6454)  # Default ArtNet port
        artnet_layout.addRow("Port:", self.port_input)
        
        # Universes list
        universes_group = QGroupBox("Universes")
        universes_layout = QVBoxLayout(universes_group)
        
        self.universes_list = QListWidget()
        universes_layout.addWidget(self.universes_list)
        
        universe_control_layout = QHBoxLayout()
        self.add_universe_input = QSpinBox()
        self.add_universe_input.setRange(0, 32767)  # DMX universe range
        universe_control_layout.addWidget(self.add_universe_input)
        
        add_universe_button = QPushButton("Add")
        add_universe_button.clicked.connect(self._add_universe)
        universe_control_layout.addWidget(add_universe_button)
        
        remove_universe_button = QPushButton("Remove")
        remove_universe_button.clicked.connect(self._remove_universe)
        universe_control_layout.addWidget(remove_universe_button)
        
        universes_layout.addLayout(universe_control_layout)
        artnet_layout.addRow("", universes_group)
        
        tabs.addTab(artnet_tab, "ArtNet")
        
        # Test Source tab
        test_tab = QWidget()
        test_layout = QFormLayout(test_tab)
        
        self.test_source_enabled = QCheckBox("Enable Test Source")
        test_layout.addRow("", self.test_source_enabled)
        
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
        
        # Visualization tab
        viz_tab = QWidget()
        viz_layout = QFormLayout(viz_tab)
        
        self.pixel_size_input = QSpinBox()
        self.pixel_size_input.setRange(1, 100)
        self.pixel_size_input.setValue(1)
        viz_layout.addRow("Pixel Size:", self.pixel_size_input)
        
        self.gap_x_input = QSpinBox()
        self.gap_x_input.setRange(0, 100)
        viz_layout.addRow("Horizontal Gap:", self.gap_x_input)
        
        self.gap_y_input = QSpinBox()
        self.gap_y_input.setRange(0, 100)
        viz_layout.addRow("Vertical Gap:", self.gap_y_input)
        
        self.canvas_width_input = QSpinBox()
        self.canvas_width_input.setRange(0, 10000)
        self.canvas_width_input.setSpecialValueText("Auto")
        viz_layout.addRow("Canvas Width:", self.canvas_width_input)
        
        self.canvas_height_input = QSpinBox()
        self.canvas_height_input.setRange(0, 10000)
        self.canvas_height_input.setSpecialValueText("Auto")
        viz_layout.addRow("Canvas Height:", self.canvas_height_input)
        
        self.start_x_input = QSpinBox()
        self.start_x_input.setRange(0, 10000)
        viz_layout.addRow("Start X:", self.start_x_input)
        
        self.start_y_input = QSpinBox()
        self.start_y_input.setRange(0, 10000)
        viz_layout.addRow("Start Y:", self.start_y_input)
        
        tabs.addTab(viz_tab, "Visualization")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        save_button = QPushButton("Save")
        save_button.clicked.connect(self._save_settings)
        button_layout.addWidget(save_button)
        
        save_file_button = QPushButton("Save to File")
        save_file_button.clicked.connect(self._save_to_file)
        button_layout.addWidget(save_file_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
    
    def _add_universe(self):
        """Add a universe to the list."""
        universe = self.add_universe_input.value()
        
        # Check if already exists
        for i in range(self.universes_list.count()):
            if self.universes_list.item(i).text() == str(universe):
                return
        
        # Add to list
        self.universes_list.addItem(QListWidgetItem(str(universe)))
    
    def _remove_universe(self):
        """Remove the selected universe from the list."""
        selected_items = self.universes_list.selectedItems()
        if selected_items:
            for item in selected_items:
                self.universes_list.takeItem(self.universes_list.row(item))
    
    def _load_config_into_ui(self):
        """Load the config values into the UI elements."""
        # ArtNet settings
        self.host_input.setText(self.config.get('artnet', {}).get('host', '0.0.0.0'))
        self.port_input.setValue(self.config.get('artnet', {}).get('port', 6454))
        
        # Universes
        universes = self.config.get('artnet', {}).get('universes', [0, 1])
        self.universes_list.clear()
        for universe in universes:
            self.universes_list.addItem(QListWidgetItem(str(universe)))
        
        # Test source settings
        test_enabled = self.config.get('test_source', {}).get('enabled', False)
        self.test_source_enabled.setChecked(test_enabled)
        
        pattern = self.config.get('test_source', {}).get('pattern', 'MOVING_BAR_H')
        index = self.pattern_combo.findText(pattern)
        if index >= 0:
            self.pattern_combo.setCurrentIndex(index)
        
        self.speed_input.setValue(self.config.get('test_source', {}).get('speed', 1.0))
        
        # Visualization settings
        viz_config = self.config.get('visualization', {})
        self.pixel_size_input.setValue(viz_config.get('pixel_size', 1))
        self.gap_x_input.setValue(viz_config.get('gap_x', 0))
        self.gap_y_input.setValue(viz_config.get('gap_y', 0))
        self.canvas_width_input.setValue(viz_config.get('canvas_width', 0))
        self.canvas_height_input.setValue(viz_config.get('canvas_height', 0))
        self.start_x_input.setValue(viz_config.get('start_x', 0))
        self.start_y_input.setValue(viz_config.get('start_y', 0))
    
    def _save_settings(self):
        """Save the settings from UI to the config dictionary."""
        # ArtNet settings
        if 'artnet' not in self.config:
            self.config['artnet'] = {}
        
        self.config['artnet']['host'] = self.host_input.text()
        self.config['artnet']['port'] = self.port_input.value()
        
        # Universes
        universes = []
        for i in range(self.universes_list.count()):
            universes.append(int(self.universes_list.item(i).text()))
        self.config['artnet']['universes'] = universes
        
        # Test source settings
        if 'test_source' not in self.config:
            self.config['test_source'] = {}
        
        self.config['test_source']['enabled'] = self.test_source_enabled.isChecked()
        self.config['test_source']['pattern'] = self.pattern_combo.currentText()
        self.config['test_source']['speed'] = self.speed_input.value()
        
        # Visualization settings
        if 'visualization' not in self.config:
            self.config['visualization'] = {}
        
        self.config['visualization']['pixel_size'] = self.pixel_size_input.value()
        self.config['visualization']['gap_x'] = self.gap_x_input.value()
        self.config['visualization']['gap_y'] = self.gap_y_input.value()
        self.config['visualization']['canvas_width'] = self.canvas_width_input.value()
        self.config['visualization']['canvas_height'] = self.canvas_height_input.value()
        self.config['visualization']['start_x'] = self.start_x_input.value()
        self.config['visualization']['start_y'] = self.start_y_input.value()
        
        # Accept the dialog
        self.accept()
    
    def _save_to_file(self):
        """Save the config to a YAML file."""
        try:
            # First save settings to config dict
            self._save_settings()
            
            # Then save to file
            with open('config.yaml', 'w') as file:
                yaml.dump(self.config, file, default_flow_style=False)
            
            QMessageBox.information(
                self, 
                "Settings Saved", 
                "Settings have been saved to config.yaml file."
            )
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error Saving Settings", 
                f"Failed to save settings: {str(e)}"
            )
    
    def get_config(self):
        """Get the current configuration."""
        return self.config
    
    def _get_default_config(self):
        """Get the default configuration."""
        return {
            'artnet': {
                'host': '0.0.0.0',
                'port': 6454,
                'universes': [0, 1]
            },
            'test_source': {
                'enabled': True,
                'pattern': 'MOVING_BAR_H',
                'speed': 1.0
            },
            'visualization': {
                'pixel_size': 2,
                'gap_x': 0,
                'gap_y': 1,
                'canvas_width': 0,
                'canvas_height': 0,
                'start_x': 0,
                'start_y': 0
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