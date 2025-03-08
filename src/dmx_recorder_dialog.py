#!/usr/bin/env python3
"""
DMX Recorder Dialog for ArtNetViz.

This module provides a PyQt dialog for controlling the DMX recorder functionality.
"""

import os
import time
from datetime import timedelta
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QCheckBox, QGroupBox, QFileDialog, QProgressBar, QListWidget, QListWidgetItem,
    QSpinBox, QGridLayout, QSizePolicy, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QSettings
import numpy as np

from dmx_recorder import DMXRecorder, ArtNetPlaybackSource

class DMXRecorderDialog(QDialog):
    """
    Dialog for controlling DMX recording and playback.
    """
    def __init__(self, artnet_source, parent=None):
        super().__init__(parent)
        self.setWindowTitle("DMX Recorder")
        self.setMinimumWidth(500)
        
        # Load settings
        self.settings = QSettings()
        recording_dir = self.settings.value("dmx_recorder/recording_dir", "recordings")
        
        # Get the current frame rate from the source if possible
        frame_rate = 44  # Default
        if hasattr(artnet_source, 'fps'):
            frame_rate = artnet_source.fps
        
        # Create DMX Recorder
        self.recorder = DMXRecorder(artnet_source, frame_rate=frame_rate, recording_dir=recording_dir)
        
        # Create playback source (for when we switch to playback mode)
        self.playback_source = ArtNetPlaybackSource(self.recorder)
        
        # Keep track of the original source
        self.original_source = artnet_source
        self.current_source = artnet_source
        
        # Keep track of what mode we're in
        self.in_playback_mode = False
        
        # Create UI layout
        self.init_ui()
        
        # Set initial frame rate in UI
        self.frame_rate_spin.setValue(frame_rate)
        
        # Status update timer
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(100)  # Update every 100ms
        
        # Initial status update
        self.update_status()
        self.update_recordings_list()
    
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout(self)
        
        # Mode selection
        mode_group = QGroupBox("Mode")
        mode_layout = QHBoxLayout(mode_group)
        
        self.live_mode_btn = QPushButton("Live Monitoring")
        self.live_mode_btn.setCheckable(True)
        self.live_mode_btn.setChecked(True)
        self.live_mode_btn.clicked.connect(self.set_live_mode)
        
        self.playback_mode_btn = QPushButton("Playback")
        self.playback_mode_btn.setCheckable(True)
        self.playback_mode_btn.clicked.connect(self.set_playback_mode)
        
        mode_layout.addWidget(self.live_mode_btn)
        mode_layout.addWidget(self.playback_mode_btn)
        main_layout.addWidget(mode_group)
        
        # Recording controls
        record_group = QGroupBox("Recording")
        record_layout = QVBoxLayout(record_group)
        
        # Recording status
        status_layout = QHBoxLayout()
        self.recording_status_label = QLabel("Not recording")
        status_layout.addWidget(self.recording_status_label)
        
        # Recording progress bar
        self.recording_progress = QProgressBar()
        self.recording_progress.setRange(0, 100)
        self.recording_progress.setValue(0)
        self.recording_progress.setTextVisible(True)
        self.recording_progress.setFormat("%v frames | %p% | %vs")
        status_layout.addWidget(self.recording_progress)
        
        record_layout.addLayout(status_layout)
        
        # Recording controls
        controls_layout = QHBoxLayout()
        
        self.record_btn = QPushButton("Start Recording")
        self.record_btn.clicked.connect(self.toggle_recording)
        controls_layout.addWidget(self.record_btn)
        
        self.frame_rate_spin = QSpinBox()
        self.frame_rate_spin.setRange(1, 120)
        self.frame_rate_spin.setValue(44)
        self.frame_rate_spin.setSuffix(" fps")
        self.frame_rate_spin.valueChanged.connect(self.set_frame_rate)
        controls_layout.addWidget(QLabel("Frame Rate:"))
        controls_layout.addWidget(self.frame_rate_spin)
        
        record_layout.addLayout(controls_layout)
        main_layout.addWidget(record_group)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(line)
        
        # Playback controls
        playback_group = QGroupBox("Playback")
        playback_layout = QVBoxLayout(playback_group)
        
        # Playback status
        playback_status_layout = QHBoxLayout()
        self.playback_status_label = QLabel("No recording loaded")
        playback_status_layout.addWidget(self.playback_status_label)
        
        # Playback progress bar
        self.playback_progress = QProgressBar()
        self.playback_progress.setRange(0, 100)
        self.playback_progress.setValue(0)
        self.playback_progress.setTextVisible(True)
        self.playback_progress.setFormat("Frame %v of %m | %p% | %vs")
        playback_status_layout.addWidget(self.playback_progress)
        
        playback_layout.addLayout(playback_status_layout)
        
        # Playback controls
        playback_controls_layout = QHBoxLayout()
        
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_playback)
        self.play_btn.setEnabled(False)
        playback_controls_layout.addWidget(self.play_btn)
        
        self.loop_checkbox = QCheckBox("Loop")
        playback_controls_layout.addWidget(self.loop_checkbox)
        
        playback_layout.addLayout(playback_controls_layout)
        
        # Recordings list
        list_layout = QHBoxLayout()
        
        self.recordings_list = QListWidget()
        self.recordings_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.recordings_list.itemSelectionChanged.connect(self.on_recording_selected)
        list_layout.addWidget(self.recordings_list)
        
        # List controls
        list_controls_layout = QVBoxLayout()
        
        self.load_btn = QPushButton("Load Selected")
        self.load_btn.clicked.connect(self.load_selected_recording)
        self.load_btn.setEnabled(False)
        list_controls_layout.addWidget(self.load_btn)
        
        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.clicked.connect(self.update_recordings_list)
        list_controls_layout.addWidget(self.refresh_btn)
        
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.clicked.connect(self.delete_selected_recording)
        self.delete_btn.setEnabled(False)
        list_controls_layout.addWidget(self.delete_btn)
        
        list_layout.addLayout(list_controls_layout)
        playback_layout.addLayout(list_layout)
        
        main_layout.addWidget(playback_group)
        
        # Button row at bottom
        button_layout = QHBoxLayout()
        
        self.select_dir_btn = QPushButton("Change Recording Directory")
        self.select_dir_btn.clicked.connect(self.select_recording_directory)
        button_layout.addWidget(self.select_dir_btn)
        
        button_layout.addStretch()
        
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        button_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(button_layout)
    
    def select_recording_directory(self):
        """Open a dialog to select a recording directory."""
        directory = QFileDialog.getExistingDirectory(
            self, "Select Recording Directory", self.recorder.recording_dir
        )
        
        if directory:
            self.recorder.recording_dir = directory
            self.settings.setValue("dmx_recorder/recording_dir", directory)
            self.update_recordings_list()
    
    def update_recordings_list(self):
        """Update the list of available recordings."""
        self.recordings_list.clear()
        
        recordings = self.recorder.list_recordings()
        
        for rec in recordings:
            # Format duration as MM:SS
            duration_str = str(timedelta(seconds=int(rec['duration'])))
            
            # Create item text
            item_text = (f"{rec['timestamp']} - {rec['frame_count']} frames - "
                         f"{rec['frame_rate']} fps - {duration_str}")
            
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self.recordings_list.addItem(item)
    
    def on_recording_selected(self):
        """Handle selection of a recording in the list."""
        selected_items = self.recordings_list.selectedItems()
        if selected_items:
            self.load_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)
        else:
            self.load_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
    
    def load_selected_recording(self):
        """Load the selected recording."""
        selected_items = self.recordings_list.selectedItems()
        if not selected_items:
            return
        
        recording = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # If we're playing, stop first
        if self.recorder.playing:
            self.recorder.stop_playback()
            if self.in_playback_mode:
                self.playback_source.stop()
            self.update_play_button()
        
        # Load the recording
        success = self.recorder.load_recording(recording['filepath'])
        if success:
            self.playback_status_label.setText(f"Loaded: {recording['timestamp']}")
            self.play_btn.setEnabled(True)
            
            # Update the playback progress max value
            self.playback_progress.setMaximum(recording['frame_count'])
            
            # Initialize playback source buffers
            self.playback_source.universes = self.recorder.playback_universes
            self.playback_source.buffers = {}
            for universe in self.playback_source.universes:
                self.playback_source.buffers[universe] = np.zeros(512, dtype=np.uint8)
            
            # If we're in playback mode, update the playback source universes
            if self.in_playback_mode:
                self.switch_to_playback_source()
        else:
            self.playback_status_label.setText("Failed to load recording")
            self.play_btn.setEnabled(False)
    
    def delete_selected_recording(self):
        """Delete the selected recording."""
        selected_items = self.recordings_list.selectedItems()
        if not selected_items:
            return
        
        recording = selected_items[0].data(Qt.ItemDataRole.UserRole)
        
        # Confirm deletion
        confirm = QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete the recording from {recording['timestamp']}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.Yes:
            try:
                os.remove(recording['filepath'])
                self.update_recordings_list()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete recording: {e}")
    
    def set_frame_rate(self, fps):
        """Set the frame rate for recording."""
        self.recorder.set_frame_rate(fps)
        
        # Update source if it supports setting fps
        source = self.current_source
        if hasattr(source, 'set_fps'):
            source.set_fps(fps)
    
    def toggle_recording(self):
        """Start or stop recording."""
        if self.recorder.recording:
            # Stop recording
            filepath = self.recorder.stop_recording()
            self.record_btn.setText("Start Recording")
            if filepath:
                self.update_recordings_list()
        else:
            # Start recording
            success = self.recorder.start_recording()
            if success:
                self.record_btn.setText("Stop Recording")
    
    def toggle_playback(self):
        """Start or stop playback."""
        if self.recorder.playing:
            # Stop playback
            self.recorder.stop_playback()
            
            # If we're in playback mode, also stop the playback source
            if self.in_playback_mode:
                self.playback_source.stop()
                
                # Force a canvas update to show blank screen
                main_window = self.parent()
                if main_window and hasattr(main_window, 'canvas'):
                    main_window.canvas.update_canvas()
                
            self.update_play_button()
        else:
            # Start playback
            loop = self.loop_checkbox.isChecked()
            
            # If we're in playback mode, make sure the playback source is running
            if self.in_playback_mode:
                # Start the playback source if we have a loaded recording
                if self.recorder.current_playback:
                    success = self.playback_source.start()
                    if success:
                        self.update_play_button()
                        # Force a canvas update to start showing playback
                        main_window = self.parent()
                        if main_window and hasattr(main_window, 'canvas'):
                            main_window.canvas.update_canvas()
            else:
                # Just play the recording without updating the visualization
                success = self.recorder.start_playback(loop=loop)
                if success:
                    self.update_play_button()
    
    def update_play_button(self):
        """Update the play button text based on playback state."""
        if self.recorder.playing:
            self.play_btn.setText("Stop")
        else:
            self.play_btn.setText("Play")
    
    def set_live_mode(self):
        """Switch to live monitoring mode."""
        if not self.in_playback_mode:
            return
        
        # Update buttons
        self.live_mode_btn.setChecked(True)
        self.playback_mode_btn.setChecked(False)
        
        # Stop playback if active
        if self.recorder.playing:
            self.recorder.stop_playback()
            self.playback_source.stop()
            self.update_play_button()
        
        # Switch back to original source
        self.switch_to_original_source()
        
        self.in_playback_mode = False
        self.update_status()
        
        # Force canvas update to refresh with live data
        main_window = self.parent()
        if main_window and hasattr(main_window, 'canvas'):
            main_window.canvas.update_canvas()
    
    def set_playback_mode(self):
        """Switch to playback mode."""
        if self.in_playback_mode:
            return
        
        # Stop recording if active
        if self.recorder.recording:
            self.recorder.stop_recording()
            self.record_btn.setText("Start Recording")
        
        # Update buttons
        self.live_mode_btn.setChecked(False)
        self.playback_mode_btn.setChecked(True)
        
        # Switch to playback source
        self.switch_to_playback_source()
        
        self.in_playback_mode = True
        self.update_status()
    
    def switch_to_original_source(self):
        """Switch the main application to use the original Art-Net source."""
        if self.current_source != self.original_source:
            # Get parent window (main window)
            main_window = self.parent()
            if main_window:
                # Replace the canvas's Art-Net source with the original
                canvas = main_window.canvas
                canvas.artnet_listener = self.original_source
                
                # Make sure universes are set correctly
                main_window._update_universes()
                
                self.current_source = self.original_source
    
    def switch_to_playback_source(self):
        """Switch the main application to use the playback source."""
        if self.current_source != self.playback_source:
            # Get parent window (main window)
            main_window = self.parent()
            if main_window:
                # Make sure we have universes set up correctly
                if self.recorder.current_playback:
                    self.playback_source.universes = self.recorder.playback_universes
                else:
                    # If no recording loaded, use the original source universes
                    self.playback_source.universes = self.original_source.universes.copy() if hasattr(self.original_source, 'universes') else [0]
                    
                # Initialize buffers with zeros for each universe (completely blank screen)
                self.playback_source.buffers = {}
                for universe in self.playback_source.universes:
                    self.playback_source.buffers[universe] = np.zeros(512, dtype=np.uint8)
                
                # Replace the canvas's Art-Net source with the playback source
                canvas = main_window.canvas
                canvas.artnet_listener = self.playback_source
                
                # Make sure universes are set correctly in the main window
                main_window._update_universes()
                
                # Set status
                self.current_source = self.playback_source
                
                # Force a canvas update to show blank screen
                canvas.update_canvas()
    
    def update_status(self):
        """Update the status displays."""
        # Update recording status
        if self.recorder.recording:
            status = self.recorder.get_recording_status()
            
            # Update label
            elapsed = status['elapsed']
            elapsed_str = str(timedelta(seconds=int(elapsed)))
            self.recording_status_label.setText(f"Recording: {elapsed_str}")
            
            # Update progress bar
            self.recording_progress.setValue(status['frame_count'])
            self.recording_progress.setFormat(f"{status['frame_count']} frames | {elapsed_str}")
        else:
            self.recording_status_label.setText("Not recording")
            self.recording_progress.setValue(0)
        
        # Update playback status
        if self.recorder.playing:
            status = self.recorder.get_playback_status()
            
            # Update label
            elapsed = status['elapsed']
            elapsed_str = str(timedelta(seconds=int(elapsed)))
            position_str = f"Frame {status['position']}/{status['total_frames']}"
            self.playback_status_label.setText(f"Playing: {position_str} | {elapsed_str}")
            
            # Update progress bar
            self.playback_progress.setValue(status['position'])
            self.playback_progress.setMaximum(status['total_frames'])
            self.playback_progress.setFormat(f"{position_str} | {elapsed_str}")
        elif self.recorder.current_playback:
            self.playback_status_label.setText("Ready to play")
        else:
            self.playback_status_label.setText("No recording loaded")
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        # If we're in playback mode, switch back to live mode
        if self.in_playback_mode:
            self.set_live_mode()
        
        # Stop recording if active
        if self.recorder.recording:
            self.recorder.stop_recording()
        
        # Stop playback if active
        if self.recorder.playing:
            self.recorder.stop_playback()
        
        # Stop the status timer
        self.status_timer.stop()
        
        # Accept the close event
        event.accept() 