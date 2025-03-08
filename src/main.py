#!/usr/bin/env python3
"""
PyQt6 Canvas Application with Syphon Integration and Art-Net Listener

This application creates a simple PyQt6 canvas that receives Art-Net DMX data
and displays it as pixels. It also exposes itself as a Syphon source on macOS,
allowing other applications to receive the canvas content in real-time.
"""

import sys
import os
import time
import numpy as np
import yaml
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QMessageBox, QLabel
from PyQt6.QtGui import QPainter, QColor, QPixmap
from PyQt6.QtCore import Qt, QTimer, QRect

import syphon
from syphon.utils.numpy import copy_image_to_mtl_texture
from syphon.utils.raw import create_mtl_texture

# Import our custom Art-Net listener and test source
from artnet_listener import ArtNetListener
from artnet_test_source import ArtNetTestSource, PatternType

# Determine if we're running as a standalone app or not
def get_resource_path(relative_path):
    """Get the correct resource path whether running as script or frozen app"""
    if getattr(sys, 'frozen', False):
        # Running as a bundled app
        base_path = os.path.dirname(sys.executable)
        if sys.platform == 'darwin' and '.app' in base_path:
            # macOS .app bundle
            base_path = os.path.join(os.path.dirname(os.path.dirname(base_path)), 'Resources')
    else:
        # Running as a script
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    return os.path.join(base_path, relative_path)

class CanvasWidget(QWidget):
    """
    A custom widget that provides a simple canvas that visualizes Art-Net DMX data
    and acts as a Syphon source.
    """
    
    def __init__(self, artnet_listener, pixel_size=1, gap_x=0, gap_y=0, 
                 canvas_width=0, canvas_height=0, start_x=0, start_y=0, parent=None):
        super().__init__(parent)
        self.artnet_listener = artnet_listener
        self.universe_count = len(artnet_listener.universes)
        
        # Pixel sizing parameters
        self.pixel_size = max(1, pixel_size)  # Ensure minimum size of 1
        self.gap_x = max(0, gap_x)  # Ensure non-negative gap
        self.gap_y = max(0, gap_y)  # Ensure non-negative gap
        
        # Visualization position
        self.start_x = max(0, start_x)
        self.start_y = max(0, start_y)
        
        # Calculate content area width and height
        content_width = 512 * (self.pixel_size + self.gap_x) - self.gap_x  # No gap after last column
        content_height = self.universe_count * (self.pixel_size + self.gap_y) - self.gap_y  # No gap after last row
        
        # Determine canvas size (either auto-sized based on content or fixed size from config)
        if canvas_width > 0:
            self.setFixedWidth(canvas_width)
        else:
            self.setFixedWidth(content_width + self.start_x)
            
        if canvas_height > 0:
            self.setFixedHeight(canvas_height)
        else:
            self.setFixedHeight(content_height + self.start_y)
        
        # Initialize canvas with black background
        self.pixmap = QPixmap(self.size())
        self.pixmap.fill(Qt.GlobalColor.black)
        
        # Performance monitoring
        self.last_update_time = time.time()
        self.frame_times = []
        self.actual_fps = 0
        
        # Initialize Syphon-related objects
        self.init_syphon()
        
        # Start a timer to update the canvas and Syphon frame
        # Set timer for standard Art-Net refresh rate of 44Hz
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_canvas)
        self.update_timer.start(10)  # 23ms interval (~43.5 FPS target) for standard Art-Net rate
    
    def init_syphon(self):
        """Initialize Syphon server and related resources"""
        self.server = syphon.SyphonMetalServer("ArtNet Visualizer")
        # Create a texture for Syphon with initial size
        self.texture = create_mtl_texture(self.server.device, self.width(), self.height())
    
    def update_canvas(self):
        """Update the canvas with current Art-Net DMX data"""

        # Get all DMX buffers
        all_buffers = self.artnet_listener.get_all_buffers()
        
        # Create new pixmap with black background
        self.pixmap.fill(Qt.GlobalColor.black)
        painter = QPainter(self.pixmap)
        
        # Pre-calculate positions to avoid repeated calculations in the loop
        y_positions = [self.start_y + y * (self.pixel_size + self.gap_y) for y in range(len(all_buffers))]
        x_positions = [self.start_x + x * (self.pixel_size + self.gap_x) for x in range(512)]
        
        # Draw each universe as a row of pixels, starting at the specified position
        for y, buffer in enumerate(all_buffers):
            y_pos = y_positions[y]
            
            for x, value in enumerate(buffer):
                if value == 0:  # Skip drawing completely black pixels to improve performance
                    continue
                    
                x_pos = x_positions[x]
                
                # Map DMX value (0-255) to grayscale color
                color = QColor(value, value, value)
                painter.fillRect(
                    QRect(x_pos, y_pos, self.pixel_size, self.pixel_size),
                    color
                )
        
        painter.end()
        
        # Update the widget
        self.update()
        
        # Update Syphon frame
        self.update_syphon_frame()
    
    def update_syphon_frame(self):
        """Update the Syphon frame with current canvas content"""
        # Convert QPixmap to numpy array (RGBA) only if needed
        image = self.pixmap.toImage()
        width = image.width()
        height = image.height()
        
        # Check if we need to resize the texture
        curr_width = self.texture.width
        curr_height = self.texture.height
        
        texture_resize_needed = width != curr_width or height != curr_height
        
        if texture_resize_needed:
            # Create a new texture with the updated size
            self.texture = create_mtl_texture(self.server.device, width, height)
        
        # Create a numpy array from the QImage data
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        arr = np.array(ptr).reshape(height, width, 4)
        
        # Flip the image vertically to correct the orientation for Syphon
        arr = np.flip(arr, axis=0)
        
        # Copy the numpy array to the Metal texture
        copy_image_to_mtl_texture(arr, self.texture)
        
        # Publish the texture to Syphon
        self.server.publish_frame_texture(self.texture)
    
    def paintEvent(self, event):
        """Paint the canvas content to the screen"""
        painter = QPainter(self)
        # Scale the pixmap to fill the widget while maintaining aspect ratio
        scaled_pixmap = self.pixmap.scaled(
            self.width(), 
            self.height(), 
            Qt.AspectRatioMode.IgnoreAspectRatio, 
            Qt.TransformationMode.FastTransformation
        )
        painter.drawPixmap(0, 0, scaled_pixmap)
        painter.end()
    
    def cleanup(self):
        """Clean up Syphon resources"""
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        if hasattr(self, 'server'):
            self.server.stop()

class MainWindow(QMainWindow):
    """
    The main application window containing the canvas.
    """
    
    def __init__(self, artnet_listener, viz_config=None):
        super().__init__()
        
        self.setWindowTitle("Art-Net Visualizer")
        
        # Apply visualization configuration with defaults
        viz_config = viz_config or {}
        pixel_size = viz_config.get('pixel_size', 1)
        gap_x = viz_config.get('gap_x', 0)
        gap_y = viz_config.get('gap_y', 0)
        canvas_width = viz_config.get('canvas_width', 0)
        canvas_height = viz_config.get('canvas_height', 0)
        start_x = viz_config.get('start_x', 0)
        start_y = viz_config.get('start_y', 0)
        
        # Create the central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Create the canvas with Art-Net listener and visualization settings
        self.canvas = CanvasWidget(
            artnet_listener,
            pixel_size=pixel_size,
            gap_x=gap_x,
            gap_y=gap_y,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            start_x=start_x,
            start_y=start_y
        )
        main_layout.addWidget(self.canvas)
        
        # Set central widget
        self.setCentralWidget(central_widget)
        
        # Resize window to match the canvas size
        self.resize(self.canvas.width(), self.canvas.height())
    
    def closeEvent(self, event):
        """Clean up resources when window is closed"""
        self.canvas.cleanup()
        super().closeEvent(event)

def load_config():
    """Load configuration from YAML file"""
    config_path = get_resource_path('config.yaml')
    
    # Default config
    default_config = {
        'artnet': {
            'host': '0.0.0.0',
            'port': 6454,
            'universes': [0]
        },
        'test_source': {
            'enabled': False,
            'pattern': 'MOVING_BAR_H',
            'speed': 1.0
        },
        'visualization': {
            'pixel_size': 1,
            'gap_x': 0,
            'gap_y': 0,
            'canvas_width': 0,
            'canvas_height': 0,
            'start_x': 0,
            'start_y': 0
        }
    }
    
    # Try to load the config file
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                return config
        except Exception as e:
            print(f"Error loading config file: {e}")
            print("Using default configuration")
            return default_config
    else:
        print(f"Config file not found at {config_path}")
        print("Using default configuration")
        return default_config

def get_pattern_type_from_string(pattern_str):
    """Convert pattern string from config to PatternType enum"""
    try:
        return PatternType[pattern_str]
    except (KeyError, ValueError):
        print(f"Unknown pattern type: {pattern_str}, using default MOVING_BAR_H")
        return PatternType.MOVING_BAR_H

def main():
    # Load configuration
    config = load_config()
    artnet_config = config.get('artnet', {})
    test_config = config.get('test_source', {})
    viz_config = config.get('visualization', {})
    
    # Determine whether to use test source or real Art-Net listener
    use_test_source = test_config.get('enabled', False)
    
    # Universe list is shared between test source and Art-Net listener
    universes = artnet_config.get('universes', [0])
    
    # Create the appropriate data source
    if use_test_source:
        # Get pattern configuration
        pattern_str = test_config.get('pattern', 'MOVING_BAR_H')
        pattern_type = get_pattern_type_from_string(pattern_str)
        speed = float(test_config.get('speed', 1.0))
        
        # Create and start test source
        data_source = ArtNetTestSource(
            universes=universes,
            pattern_type=pattern_type,
            speed=speed
        )
        print(f"Using Art-Net test source with pattern: {pattern_str}")
    else:
        # Create standard Art-Net listener
        data_source = ArtNetListener(
            host=artnet_config.get('host', '0.0.0.0'),
            port=artnet_config.get('port', 6454),
            universes=universes
        )
        print("Using standard Art-Net listener")
    
    # Start the data source
    data_source.start()
    
    # Create and run the application
    app = QApplication(sys.argv)
    window = MainWindow(data_source, viz_config)
    window.show()
    
    # Run the application
    exit_code = app.exec()
    
    # Stop the data source before exiting
    data_source.stop()
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main() 