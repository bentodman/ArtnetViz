#!/usr/bin/env python3
"""
PyQt6 Canvas Application with Syphon Integration

This application creates a PyQt6 drawing canvas and exposes it as a Syphon source
on macOS, allowing other applications to receive the canvas content in real-time.
"""

import sys
import time
import numpy as np
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QSlider, QLabel, QPushButton, QColorDialog)
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPen, QBrush
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, pyqtSignal

import syphon
from syphon.utils.numpy import copy_image_to_mtl_texture
from syphon.utils.raw import create_mtl_texture

class CanvasWidget(QWidget):
    """
    A custom widget that provides a drawing canvas and tracks mouse events 
    for drawing operations.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        
        # Initialize canvas settings
        self.pixmap = QPixmap(self.size())
        self.pixmap.fill(Qt.GlobalColor.white)
        
        # Drawing settings
        self.last_point = QPoint()
        self.drawing = False
        self.pen_color = QColor(0, 0, 0)
        self.pen_width = 3
        
        # Initialize Syphon-related objects
        self.init_syphon()
        
        # Start a timer to update Syphon frames
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_syphon_frame)
        self.update_timer.start(16)  # ~60 FPS
    
    def init_syphon(self):
        """Initialize Syphon server and related resources"""
        self.server = syphon.SyphonMetalServer("PyQt6 Canvas")
        # Create a texture for Syphon with initial size
        self.texture = create_mtl_texture(self.server.device, self.width(), self.height())
    
    def update_syphon_frame(self):
        """Update the Syphon frame with current canvas content"""
        # Convert QPixmap to numpy array (RGBA)
        image = self.pixmap.toImage()
        width = image.width()
        height = image.height()
        
        # Create a numpy array from the QImage data
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        arr = np.array(ptr).reshape(height, width, 4)
        
        # Flip the image vertically to correct the orientation for Syphon
        arr = np.flip(arr, axis=0)
        
        # Check if we need to resize the texture
        curr_width = self.texture.width
        curr_height = self.texture.height
        if width != curr_width or height != curr_height:
            # Create a new texture with the updated size
            self.texture = create_mtl_texture(self.server.device, width, height)
        
        # Copy the numpy array to the Metal texture
        copy_image_to_mtl_texture(arr, self.texture)
        
        # Publish the texture to Syphon
        self.server.publish_frame_texture(self.texture)
    
    def resizeEvent(self, event):
        """Handle resize events to maintain canvas size"""
        new_pixmap = QPixmap(self.size())
        new_pixmap.fill(Qt.GlobalColor.white)
        
        # Copy existing content
        painter = QPainter(new_pixmap)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.end()
        
        self.pixmap = new_pixmap
        super().resizeEvent(event)
    
    def mousePressEvent(self, event):
        """Begin drawing when mouse button is pressed"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.last_point = event.position().toPoint()
    
    def mouseMoveEvent(self, event):
        """Draw a line as the mouse moves while button is pressed"""
        if (event.buttons() & Qt.MouseButton.LeftButton) and self.drawing:
            painter = QPainter(self.pixmap)
            painter.setPen(QPen(self.pen_color, self.pen_width, 
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, 
                              Qt.PenJoinStyle.RoundJoin))
            
            current_point = event.position().toPoint()
            painter.drawLine(self.last_point, current_point)
            self.last_point = current_point
            painter.end()
            
            self.update()  # Trigger a repaint event
    
    def mouseReleaseEvent(self, event):
        """Stop drawing when mouse button is released"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False
    
    def paintEvent(self, event):
        """Paint the canvas content to the screen"""
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)
        painter.end()
    
    def clear_canvas(self):
        """Clear the canvas by filling it with white"""
        self.pixmap.fill(Qt.GlobalColor.white)
        self.update()
    
    def set_pen_color(self, color):
        """Set the pen color for drawing"""
        self.pen_color = color
    
    def set_pen_width(self, width):
        """Set the pen width for drawing"""
        self.pen_width = width
    
    def cleanup(self):
        """Clean up Syphon resources"""
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        if hasattr(self, 'server'):
            self.server.stop()

class MainWindow(QMainWindow):
    """
    The main application window containing the canvas and controls.
    """
    
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("PyQt6 Canvas with Syphon")
        self.setMinimumSize(800, 600)
        
        # Create the central widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Create the canvas
        self.canvas = CanvasWidget()
        main_layout.addWidget(self.canvas)
        
        # Create control panel
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        
        # Pen width slider
        width_layout = QVBoxLayout()
        width_label = QLabel("Pen Width")
        self.width_slider = QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(1, 20)
        self.width_slider.setValue(3)
        self.width_slider.valueChanged.connect(self.canvas.set_pen_width)
        width_layout.addWidget(width_label)
        width_layout.addWidget(self.width_slider)
        control_layout.addLayout(width_layout)
        
        # Color picker button
        self.color_button = QPushButton("Change Color")
        self.color_button.clicked.connect(self.show_color_dialog)
        control_layout.addWidget(self.color_button)
        
        # Clear button
        self.clear_button = QPushButton("Clear Canvas")
        self.clear_button.clicked.connect(self.canvas.clear_canvas)
        control_layout.addWidget(self.clear_button)
        
        # Add the control panel to main layout
        main_layout.addWidget(control_panel)
        
        # Set central widget
        self.setCentralWidget(central_widget)
    
    def show_color_dialog(self):
        """Show color picker dialog and update pen color"""
        color = QColorDialog.getColor(self.canvas.pen_color, self)
        if color.isValid():
            self.canvas.set_pen_color(color)
    
    def closeEvent(self, event):
        """Clean up resources when window is closed"""
        self.canvas.cleanup()
        super().closeEvent(event)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 