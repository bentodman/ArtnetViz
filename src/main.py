#!/usr/bin/env python3
"""
Art-Net Visualizer with Syphon Integration

This application creates a PyQt6-based interface for visualizing Art-Net DMX data
as pixels on a canvas. It displays each universe as a row of 512 pixels where each
pixel represents one DMX channel's value (0-255).

Features:
- Intuitive UI with direct universe management
- Configurable visualization settings (pixel size, gaps, position, etc.)
- Real-time DMX data display at configurable frame rates
- Exposes itself as a Syphon source for integration with other applications
- Built-in test pattern generator for testing without external Art-Net sources
- Persistent settings and window state between sessions

The application allows both real-time adjustment via the UI and configuration
through a YAML file.
"""

import sys
import os
import time
import signal
import yaml
import numpy as np
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QMessageBox, QLabel,
    QToolBar, QStatusBar, QMenuBar, QMenu, QDialog, QSizePolicy, QGroupBox, QHBoxLayout,
    QSpinBox, QPushButton, QCheckBox, QListWidget, QListWidgetItem
)
from PyQt6.QtGui import QPainter, QColor, QPixmap, QAction
from PyQt6.QtCore import Qt, QTimer, QRect, QByteArray, QSize, QSettings
import gc
import psutil
import tracemalloc

import syphon
from syphon.utils.numpy import copy_image_to_mtl_texture
from syphon.utils.raw import create_mtl_texture
try:
    import Metal
except ImportError:
    # Metal is not available, we'll handle this in the Syphon init
    pass

# Import our custom Art-Net listener and test source
from artnet_listener import ArtNetListener
from artnet_test_source import ArtNetTestSource, PatternType

# Import shared configuration
from config import DEBUG_MEMORY

# Import our settings dialog
from settings_dialog import SettingsDialog, load_config_from_file

# Import memory tracking utilities
try:
    from debug_objects import memory_tracker, setup_memory_tracking, memory_snapshot
    MEMORY_TRACKING_AVAILABLE = True
except ImportError:
    MEMORY_TRACKING_AVAILABLE = False
    
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
        
        # Store the Art-Net listener
        self.artnet_listener = artnet_listener
        
        # Store visualization parameters
        self.pixel_size = pixel_size
        self.gap_x = gap_x
        self.gap_y = gap_y
        self.custom_canvas_width = canvas_width
        self.custom_canvas_height = canvas_height
        self.start_x = start_x
        self.start_y = start_y
        
        # Logging control
        self.verbose = False
        
        # Frame rate control
        self.frame_rate = 44  # Default to DMX standard ~44Hz
        
        # Memory tracking
        self._last_memory_check = 0
        self._memory_check_interval = 10  # Check memory every 10 frames
        
        # Initialize Syphon
        self.init_syphon()
        
        # Create canvas update timer
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_canvas)
        self.set_frame_rate(self.frame_rate)
        
        # Set up the widget
        self.setMinimumSize(100, 100)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, 
            QSizePolicy.Policy.Expanding
        )
        
        # Initialize the pixmaps
        self.pixmap = None  # Scaled pixmap for preview
        self.full_res_pixmap = None  # Full-resolution pixmap for Syphon output
        self.max_preview_width = 1200  # Maximum width for the preview window
        self.max_preview_height = 800  # Maximum height for the preview window
        
        # Initialize painters
        self._painter = None
        self._full_res_painter = None
        
        # Frame counter for periodic cleanup
        self._frame_counter = 0
        
        # Cache for color objects
        self._color_cache = {}
        
        # Cache for coordinate calculations
        self._coordinate_cache = {}
        
        # Cache for Syphon frame data
        self._syphon_array = None
        self._syphon_array_dims = None
        
        self.update_canvas()

    def init_syphon(self):
        """Initialize the Syphon server"""
        try:
            # Check if Metal is available
            metal_available = 'Metal' in sys.modules
            
            # Create and start Syphon server
            if metal_available and hasattr(syphon, 'SyphonMetalServer'):
                try:
                    # Create Metal device first and validate
                    self.metal_device = Metal.MTLCreateSystemDefaultDevice()
                    if not self.metal_device:
                        print("Warning: Failed to create Metal device, falling back to legacy server")
                        raise RuntimeError("Failed to create Metal device")
                    
                    # Create Syphon server with error checking
                    self.server = syphon.SyphonMetalServer("ArtNet Visualizer")
                    if not self.server:
                        print("Warning: Failed to create Metal Syphon server, falling back to legacy server")
                        raise RuntimeError("Failed to create Syphon server")
                        
                    print("Syphon server started (Metal interface)")
                    self.using_metal = True
                except Exception as metal_error:
                    print(f"Metal initialization failed: {metal_error}")
                    # Fall back to legacy server if Metal fails
                    if hasattr(syphon, 'SyphonServer'):
                        self.server = syphon.SyphonServer()
                        self.server.start(name="ArtNet Visualizer", dimensions=(512, 10))
                        print("Syphon server started (legacy interface)")
                        self.using_metal = False
                    else:
                        print("Warning: No supported Syphon implementation available")
                        self.server = None
                        self.using_metal = False
            elif hasattr(syphon, 'SyphonServer'):
                # Use legacy Syphon server
                self.server = syphon.SyphonServer()
                self.server.start(name="ArtNet Visualizer", dimensions=(512, 10))
                print("Syphon server started (legacy interface)")
                self.using_metal = False
            else:
                print("Warning: No supported Syphon implementation found")
                self.server = None
                self.using_metal = False
        except Exception as e:
            print(f"Error initializing Syphon: {e}")
            self.server = None
            self.using_metal = False
            # Don't raise the exception - allow the app to continue without Syphon

    def set_frame_rate(self, fps):
        """Set the frame rate for canvas updates"""
        self.frame_rate = fps
        # Calculate timer interval in milliseconds (1000ms / fps)
        interval_ms = int(1000 / fps) if fps > 0 else 1000
        
        # Stop the timer if it's running
        if self.update_timer.isActive():
            self.update_timer.stop()
            
        # Set the new interval and restart
        self.update_timer.setInterval(interval_ms)
        self.update_timer.start()
        
        if self.verbose:
            print(f"Frame rate set to {fps} FPS (interval: {interval_ms}ms)")

    def _get_cached_color(self, value):
        """Get a cached QColor object for the given DMX value"""
        if value not in self._color_cache:
            self._color_cache[value] = QColor(value, value, value)
        return self._color_cache[value]

    def _get_cached_coordinates(self, pixel_x, row_y, preview_width, canvas_width, preview_height, canvas_height):
        """Get cached coordinates for preview scaling"""
        key = (pixel_x, row_y, preview_width, canvas_width, preview_height, canvas_height)
        if key not in self._coordinate_cache:
            preview_x = int(pixel_x * (preview_width / canvas_width))
            preview_y = int(row_y * (preview_height / canvas_height))
            preview_size = int(self.pixel_size * (preview_width / canvas_width))
            self._coordinate_cache[key] = (preview_x, preview_y, preview_size)
        return self._coordinate_cache[key]

    def update_canvas(self):
        """Update the canvas with the current Art-Net DMX data"""
        # Get DMX data for all universes
        universes = self.artnet_listener.universes
        universe_count = len(universes)
        
        if self.verbose:
            print(f"Updating canvas with {universe_count} universes")
        
        if universe_count > 0:
            # Calculate canvas dimensions based on visualization parameters
            dmx_width = 512
            
            # Calculate pixel dimensions including gaps
            pixel_width_with_gap = self.pixel_size + self.gap_x
            pixel_height_with_gap = self.pixel_size + self.gap_y
            
            # Calculate content dimensions
            content_width = dmx_width * pixel_width_with_gap
            content_height = universe_count * pixel_height_with_gap
            
            # Determine canvas dimensions
            canvas_width = max(self.custom_canvas_width, content_width + self.start_x) if self.custom_canvas_width > 0 else content_width + self.start_x
            canvas_height = max(self.custom_canvas_height, content_height + self.start_y) if self.custom_canvas_height > 0 else content_height + self.start_y
            
            if self.verbose:
                print(f"Canvas dimensions: {canvas_width}x{canvas_height}")
            
            # Create or resize the full resolution pixmap for Syphon output
            if self.full_res_pixmap is None or self.full_res_pixmap.width() != canvas_width or self.full_res_pixmap.height() != canvas_height:
                if self.full_res_pixmap is not None:
                    del self.full_res_pixmap
                self.full_res_pixmap = QPixmap(canvas_width, canvas_height)
                print(f"Created new full-res pixmap: {canvas_width}x{canvas_height}")
            else:
                self.full_res_pixmap.fill(Qt.GlobalColor.transparent)
            
            # Check if we need to resize the preview pixmap
            preview_width = canvas_width
            preview_height = canvas_height
            
            if preview_width > self.max_preview_width or preview_height > self.max_preview_height:
                width_ratio = self.max_preview_width / preview_width
                height_ratio = self.max_preview_height / preview_height
                scale_factor = min(width_ratio, height_ratio)
                
                preview_width = int(preview_width * scale_factor)
                preview_height = int(preview_height * scale_factor)
                if self.verbose:
                    print(f"Preview dimensions scaled to: {preview_width}x{preview_height}")
            
            # Create or resize the preview pixmap as needed
            if self.pixmap is None or self.pixmap.width() != preview_width or self.pixmap.height() != preview_height:
                if self.pixmap is not None:
                    del self.pixmap
                self.pixmap = QPixmap(preview_width, preview_height)
            else:
                self.pixmap.fill(Qt.GlobalColor.transparent)
            
            # Create local QPainter objects
            full_res_painter = QPainter(self.full_res_pixmap)
            painter = QPainter(self.pixmap)
            
            try:
                # Draw DMX data
                for i, universe in enumerate(universes):
                    dmx_data = self.artnet_listener.get_buffer(universe)
                    if dmx_data is None:
                        continue
                    
                    # Calculate row position
                    row_y = self.start_y + (i * pixel_height_with_gap)
                    
                    # Draw each DMX channel as a pixel
                    for j in range(min(len(dmx_data), 512)):
                        # Calculate pixel position
                        pixel_x = self.start_x + (j * pixel_width_with_gap)
                        
                        # Get DMX value (0-255)
                        value = dmx_data[j]
                        
                        # Get cached color
                        color = self._get_cached_color(value)
                        
                        # Draw on both pixmaps
                        full_res_painter.fillRect(pixel_x, row_y, self.pixel_size, self.pixel_size, color)
                        
                        # Get cached coordinates
                        preview_x, preview_y, preview_size = self._get_cached_coordinates(
                            pixel_x, row_y, preview_width, canvas_width, preview_height, canvas_height
                        )
                        
                        painter.fillRect(preview_x, preview_y, preview_size, preview_size, color)
                
                # End painters
                full_res_painter.end()
                painter.end()
                
                # Update Syphon frame
                self.update_syphon_frame()
                
                # Force update of the widget
                self.update()
                
                # Periodic cleanup and memory check
                self._frame_counter += 1
                if self._frame_counter % 60 == 0:
                    # Clear caches periodically to prevent memory growth
                    self._color_cache.clear()
                    self._coordinate_cache.clear()
                    gc.collect()
                    
                    # Log memory usage every 60 frames
                    if DEBUG_MEMORY:
                        process = psutil.Process()
                        memory_info = process.memory_info()
                        memory_mb = memory_info.rss / (1024 * 1024)
                        print(f"[DEBUG-MEM] Memory usage at frame {self._frame_counter}: {memory_mb:.2f} MB")
                        if tracemalloc.is_tracing():
                            snapshot = tracemalloc.take_snapshot()
                            top_stats = snapshot.statistics('lineno')
                            print(f"[DEBUG-MEM] Top 5 memory allocations at frame {self._frame_counter}:")
                            for stat in top_stats[:5]:
                                print(f"[DEBUG-MEM] {stat}")
            finally:
                # Ensure painters are properly cleaned up
                if full_res_painter.isActive():
                    full_res_painter.end()
                if painter.isActive():
                    painter.end()
                del full_res_painter
                del painter
                gc.collect()
        elif self.verbose:
            print("No universes found. Canvas not updated.")
    
    def update_syphon_frame(self):
        """Update Syphon server with full-resolution pixmap content"""
        if not self.server or not self.full_res_pixmap:
            return
        
        try:
            # Always use the full resolution pixmap for Syphon output
            image = self.full_res_pixmap.toImage()
            if not image:
                print("Warning: Failed to convert pixmap to image")
                return
                
            # Verify dimensions will work with Metal texture limits (16384 max)
            width = min(image.width(), 16384)  # Limit to max Metal texture size
            height = min(image.height(), 16384)  # Limit to max Metal texture size
            
            # If image is larger than Metal texture limits, create a scaled version
            if width < image.width() or height < image.height():
                print(f"WARNING: Image dimensions ({image.width()}x{image.height()}) exceed Metal texture limits. Scaling to {width}x{height}")
                image = image.scaled(width, height, aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio)
            
            # Check if we need to update the cached array
            if (self._syphon_array is None or 
                self._syphon_array_dims != (width, height)):
                
                # Convert QImage to NumPy array for Syphon
                ptr = image.bits()
                if not ptr:
                    print("Warning: Failed to get image bits")
                    return
                    
                ptr.setsize(height * width * 4)
                self._syphon_array = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
                self._syphon_array_dims = (width, height)
                
                # Flip the image vertically for Syphon (corrects the upside-down issue)
                self._syphon_array = np.flip(self._syphon_array, axis=0)
            else:
                # Update existing array with new data
                ptr = image.bits()
                if not ptr:
                    print("Warning: Failed to get image bits")
                    return
                    
                ptr.setsize(height * width * 4)
                np.copyto(self._syphon_array, np.frombuffer(ptr, np.uint8).reshape((height, width, 4)))
                self._syphon_array = np.flip(self._syphon_array, axis=0)
            
            if self.using_metal:
                # Metal-based Syphon server with texture caching
                try:
                    if (not hasattr(self, 'cached_mtl_texture') or self.cached_mtl_texture is None or
                        not hasattr(self, 'cached_mtl_texture_dims') or self.cached_mtl_texture_dims != (width, height)):
                        if hasattr(self, 'cached_mtl_texture') and self.cached_mtl_texture is not None:
                            try:
                                del self.cached_mtl_texture
                            except:
                                pass
                                
                        # Validate Metal device before creating texture
                        if not hasattr(self, 'metal_device') or not self.metal_device:
                            print("Warning: Metal device not available")
                            return
                            
                        self.cached_mtl_texture = create_mtl_texture(device=self.metal_device, width=width, height=height)
                        if not self.cached_mtl_texture:
                            print("Warning: Failed to create Metal texture")
                            return
                            
                        self.cached_mtl_texture_dims = (width, height)
                        
                    # Copy image data to texture
                    try:
                        copy_image_to_mtl_texture(self._syphon_array, self.cached_mtl_texture)
                    except Exception as copy_error:
                        print(f"Error copying image to Metal texture: {copy_error}")
                        return
                        
                    # Publish frame
                    try:
                        self.server.publish_frame_texture(self.cached_mtl_texture)
                    except Exception as publish_error:
                        print(f"Error publishing frame: {publish_error}")
                        return
                        
                except Exception as e:
                    print(f"Error in Metal Syphon update: {e}")
                    # Try fallback to legacy mode if Metal fails
                    self.using_metal = False
                    if hasattr(self.server, 'publish_frame_nparray'):
                        try:
                            self.server.publish_frame_nparray(self._syphon_array, (width, height))
                        except Exception as legacy_error:
                            print(f"Legacy fallback also failed: {legacy_error}")
            else:
                # Legacy Syphon server
                try:
                    self.server.publish_frame_nparray(self._syphon_array, (width, height))
                except Exception as e:
                    print(f"Error updating legacy Syphon: {e}")
                    # Try fallback using texture creation
                    try:
                        if hasattr(self.server, 'device'):
                            texture = create_mtl_texture(device=self.server.device, width=width, height=height)
                            if texture:
                                copy_image_to_mtl_texture(self._syphon_array, texture)
                                self.server.publish_frame_texture(texture)
                                del texture  # Free texture reference
                    except Exception as fallback_e:
                        print(f"Fallback Syphon update also failed: {fallback_e}")
        except Exception as e:
            print(f"Error in update_syphon_frame: {e}")
        finally:
            # Clean up temporary objects
            if 'image' in locals():
                del image
            if 'ptr' in locals():
                del ptr
            gc.collect()
    
    def paintEvent(self, event):
        """Paint the canvas on the widget"""
        if self.pixmap:
            painter = QPainter(self)
            
            # Get the widget dimensions
            widget_width = self.width()
            widget_height = self.height()
            
            # Get the pixmap dimensions
            pixmap_width = self.pixmap.width()
            pixmap_height = self.pixmap.height()
            
            # Calculate scaling for aspect ratio preservation if needed
            scale_x = widget_width / pixmap_width
            scale_y = widget_height / pixmap_height
            
            # Use the smaller scale to maintain aspect ratio
            # or 1.0 if no scaling is needed
            scale = min(scale_x, scale_y, 1.0)
            
            # Calculate the destination rectangle centered in the widget
            dest_width = int(pixmap_width * scale)
            dest_height = int(pixmap_height * scale)
            dest_x = (widget_width - dest_width) // 2
            dest_y = (widget_height - dest_height) // 2
            
            # Create the destination rectangle
            dest_rect = QRect(dest_x, dest_y, dest_width, dest_height)
            
            # Draw the pixmap in the destination rectangle
            painter.drawPixmap(dest_rect, self.pixmap, self.pixmap.rect())
            
            # Draw a border around the pixmap for clarity
            painter.setPen(Qt.GlobalColor.white)
            painter.drawRect(dest_rect)
            
            # Display information about dimensions
            info_text = (f"Preview: {pixmap_width}x{pixmap_height}, "
                       f"Full: {self.full_res_pixmap.width() if self.full_res_pixmap else 0}x"
                       f"{self.full_res_pixmap.height() if self.full_res_pixmap else 0}")
            painter.drawText(dest_x, dest_y - 5, info_text)
            
            painter.end()
    
    def cleanup(self):
        """Clean up resources"""
        # Safely stop the timer
        if hasattr(self, 'update_timer') and self.update_timer is not None:
            try:
                if self.update_timer.isActive():
                    self.update_timer.stop()
            except RuntimeError:
                # Ignore RuntimeError if the timer has already been deleted
                pass
            except Exception as e:
                print(f"Error stopping timer: {e}")
            finally:
                del self.update_timer
        
        # Clean up painters
        if self._painter is not None:
            try:
                self._painter.end()
            except:
                pass
            del self._painter
        
        if self._full_res_painter is not None:
            try:
                self._full_res_painter.end()
            except:
                pass
            del self._full_res_painter
        
        # Clean up pixmaps
        if hasattr(self, '_full_res_pixmap'):
            del self._full_res_pixmap
        
        if hasattr(self, 'full_res_pixmap'):
            del self.full_res_pixmap
        
        if hasattr(self, 'pixmap'):
            del self.pixmap
            
        # Clean up Metal textures
        if hasattr(self, 'cached_mtl_texture') and self.cached_mtl_texture is not None:
            try:
                del self.cached_mtl_texture
            except:
                pass
                
        if hasattr(self, 'cached_mtl_texture_dims'):
            del self.cached_mtl_texture_dims
            
        # Clean up Metal device
        if hasattr(self, 'metal_device'):
            del self.metal_device
        
        # Force a garbage collection
        gc.collect()
        
        if self.server:
            try:
                if hasattr(self.server, 'stop'):
                    self.server.stop()
                print("Syphon server stopped")
            except Exception as e:
                print(f"Error stopping Syphon server: {e}")
                
        # Final cleanup
        gc.collect()

    def __del__(self):
        """Clean up resources when object is deleted"""
        self.cleanup()

class MainWindow(QMainWindow):
    """
    The main application window containing the canvas.
    """
    
    def __init__(self, artnet_listener, config=None):
        super().__init__()
        
        self.setWindowTitle("Art-Net Visualizer")
        self.config = config or {}
        self.artnet_listener = artnet_listener
        
        # Apply visualization configuration with defaults
        pixel_size = self.config.get('pixel_size', 1)
        gap_x = self.config.get('gap_x', 0)
        gap_y = self.config.get('gap_y', 0)
        canvas_width = self.config.get('canvas_width', 0)
        canvas_height = self.config.get('canvas_height', 0)
        start_x = self.config.get('start_x', 0)
        start_y = self.config.get('start_y', 0)
        frame_rate = self.config.get('frame_rate', 44)
        
        # Create the central widget and layout - store as instance variables for later use
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        
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
        
        # Apply frame rate from config
        self.canvas.frame_rate = frame_rate
        self.canvas.set_frame_rate(frame_rate)
        
        # Add the canvas to the main layout
        self.main_layout.addWidget(self.canvas, 1)  # Give it stretch factor of 1
        
        # Create and add control panel
        self._create_control_panel()
        
        # Create menu bar
        self._create_menus()
        
        # Set initial window size (wider than tall to accommodate DMX visualizer)
        self.resize(900, 400)
    
    def _create_control_panel(self):
        """Create a control panel with visualization settings controls"""
        # Create the control panel widget and layout
        self.control_panel = QWidget()
        control_layout = QVBoxLayout(self.control_panel)  # Change to vertical layout
        control_layout.setContentsMargins(10, 5, 10, 10)
        control_layout.setSpacing(8)
        
        # Create horizontal layout for all controls
        settings_layout = QHBoxLayout()
        settings_layout.setSpacing(10)
        
        # --- VISUALIZATION SETTINGS GROUP ---
        viz_group = QGroupBox("Visualization Settings")
        viz_layout = QHBoxLayout(viz_group)
        viz_layout.setSpacing(6)
        
        # Left column - Pixel settings
        pixel_col = QVBoxLayout()
        pixel_col.setSpacing(4)
        
        # Create pixel size controls
        pixel_size_layout = QHBoxLayout()
        pixel_size_layout.addWidget(QLabel("Pixel Size:"))
        self.pixel_size_spinner = QSpinBox()
        self.pixel_size_spinner.setRange(1, 100)
        self.pixel_size_spinner.setValue(self.canvas.pixel_size)
        self.pixel_size_spinner.valueChanged.connect(self._on_pixel_size_changed)
        pixel_size_layout.addWidget(self.pixel_size_spinner)
        pixel_col.addLayout(pixel_size_layout)
        
        # Create horizontal gap controls
        gap_x_layout = QHBoxLayout()
        gap_x_layout.addWidget(QLabel("H-Gap:"))
        self.gap_x_spinner = QSpinBox()
        self.gap_x_spinner.setRange(0, 100)
        self.gap_x_spinner.setValue(self.canvas.gap_x)
        self.gap_x_spinner.valueChanged.connect(self._on_gap_x_changed)
        gap_x_layout.addWidget(self.gap_x_spinner)
        pixel_col.addLayout(gap_x_layout)
        
        # Create vertical gap controls
        gap_y_layout = QHBoxLayout()
        gap_y_layout.addWidget(QLabel("V-Gap:"))
        self.gap_y_spinner = QSpinBox()
        self.gap_y_spinner.setRange(0, 100)
        self.gap_y_spinner.setValue(self.canvas.gap_y)
        self.gap_y_spinner.valueChanged.connect(self._on_gap_y_changed)
        gap_y_layout.addWidget(self.gap_y_spinner)
        pixel_col.addLayout(gap_y_layout)
        
        # Add fps controls
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("FPS:"))
        self.fps_spinner = QSpinBox()
        self.fps_spinner.setRange(1, 120)
        self.fps_spinner.setValue(self.canvas.frame_rate)
        self.fps_spinner.valueChanged.connect(self._on_framerate_changed)
        fps_layout.addWidget(self.fps_spinner)
        pixel_col.addLayout(fps_layout)
        
        viz_layout.addLayout(pixel_col)
        
        # Middle column - Position settings
        pos_col = QVBoxLayout()
        pos_col.setSpacing(4)
        
        # Create start X controls
        start_x_layout = QHBoxLayout()
        start_x_layout.addWidget(QLabel("Start X:"))
        self.start_x_spinner = QSpinBox()
        self.start_x_spinner.setRange(0, 1000)
        self.start_x_spinner.setValue(self.canvas.start_x)
        self.start_x_spinner.valueChanged.connect(self._on_start_x_changed)
        start_x_layout.addWidget(self.start_x_spinner)
        pos_col.addLayout(start_x_layout)
        
        # Create start Y controls
        start_y_layout = QHBoxLayout()
        start_y_layout.addWidget(QLabel("Start Y:"))
        self.start_y_spinner = QSpinBox()
        self.start_y_spinner.setRange(0, 1000)
        self.start_y_spinner.setValue(self.canvas.start_y)
        self.start_y_spinner.valueChanged.connect(self._on_start_y_changed)
        start_y_layout.addWidget(self.start_y_spinner)
        pos_col.addLayout(start_y_layout)
        
        # Create canvas width controls
        canvas_width_layout = QHBoxLayout()
        canvas_width_layout.addWidget(QLabel("Width:"))
        self.canvas_width_spinner = QSpinBox()
        self.canvas_width_spinner.setRange(0, 16384)  # Max Metal texture size
        self.canvas_width_spinner.setValue(self.canvas.custom_canvas_width)
        self.canvas_width_spinner.setSpecialValueText("Auto")  # 0 = Auto
        self.canvas_width_spinner.valueChanged.connect(self._on_canvas_width_changed)
        canvas_width_layout.addWidget(self.canvas_width_spinner)
        pos_col.addLayout(canvas_width_layout)
        
        # Create canvas height controls
        canvas_height_layout = QHBoxLayout()
        canvas_height_layout.addWidget(QLabel("Height:"))
        self.canvas_height_spinner = QSpinBox()
        self.canvas_height_spinner.setRange(0, 16384)  # Max Metal texture size
        self.canvas_height_spinner.setValue(self.canvas.custom_canvas_height)
        self.canvas_height_spinner.setSpecialValueText("Auto")  # 0 = Auto
        self.canvas_height_spinner.valueChanged.connect(self._on_canvas_height_changed)
        canvas_height_layout.addWidget(self.canvas_height_spinner)
        pos_col.addLayout(canvas_height_layout)
        
        viz_layout.addLayout(pos_col)
        settings_layout.addWidget(viz_group, 3)  # Give it 3 parts of horizontal space
        
        # --- ART-NET SETTINGS GROUP ---
        artnet_group = QGroupBox("Art-Net Settings")
        artnet_layout = QVBoxLayout(artnet_group)
        
        # Create universes controls with label
        artnet_layout.addWidget(QLabel("Monitored Universes:"))
        
        # List of current universes
        self.universe_list = QListWidget()
        self.universe_list.setFixedHeight(80)
        self.universe_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        
        # Populate the list with current universes
        for universe in self.artnet_listener.universes:
            self.universe_list.addItem(QListWidgetItem(str(universe)))
            
        artnet_layout.addWidget(self.universe_list)
        
        # Universe controls (add/remove)
        universe_controls = QHBoxLayout()
        
        universe_controls.addWidget(QLabel("Universe:"))
        
        # Universe input for adding
        self.add_universe_spinner = QSpinBox()
        self.add_universe_spinner.setRange(0, 32767)  # Maximum Art-Net universe
        universe_controls.addWidget(self.add_universe_spinner)
        
        # Add universe button
        add_universe_btn = QPushButton("Add")
        add_universe_btn.clicked.connect(self._add_universe)
        add_universe_btn.setFixedWidth(60)
        universe_controls.addWidget(add_universe_btn)
        
        # Remove universe button
        remove_universe_btn = QPushButton("Remove")
        remove_universe_btn.clicked.connect(self._remove_universe)
        remove_universe_btn.setFixedWidth(60)
        universe_controls.addWidget(remove_universe_btn)
        
        artnet_layout.addLayout(universe_controls)
        settings_layout.addWidget(artnet_group, 2)  # Give it 2 parts of horizontal space
        
        # Add settings layout to main control layout
        control_layout.addLayout(settings_layout)
        
        # Create "Save to Config" button in its own row
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)  # Push button to the right
        save_button = QPushButton("Save Settings to Config")
        save_button.setFixedWidth(200)
        save_button.clicked.connect(self._save_viz_settings_to_config)
        button_layout.addWidget(save_button)
        control_layout.addLayout(button_layout)
        
        # Add the control panel to the main layout
        self.main_layout.addWidget(self.control_panel)
    
    def _on_pixel_size_changed(self, value):
        """Handle pixel size change"""
        # Update canvas directly
        self.canvas.pixel_size = value
        
        # Update config
        self.config["pixel_size"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Pixel size changed to {value}")
    
    def _on_gap_x_changed(self, value):
        """Handle horizontal gap change"""
        # Update canvas directly
        self.canvas.gap_x = value
        
        # Update config
        self.config["gap_x"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Horizontal gap changed to {value}")
    
    def _on_gap_y_changed(self, value):
        """Handle vertical gap change"""
        # Update canvas directly
        self.canvas.gap_y = value
        
        # Update config
        self.config["gap_y"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Vertical gap changed to {value}")
    
    def _on_start_x_changed(self, value):
        """Handle start X change"""
        # Update canvas directly
        self.canvas.start_x = value
        
        # Update config
        self.config["start_x"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Start X changed to {value}")
    
    def _on_start_y_changed(self, value):
        """Handle start Y change"""
        # Update canvas directly
        self.canvas.start_y = value
        
        # Update config
        self.config["start_y"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Start Y changed to {value}")
    
    def _on_canvas_width_changed(self, value):
        """Handle canvas width change"""
        # Update canvas directly
        self.canvas.custom_canvas_width = value
        
        # Update config
        self.config["canvas_width"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Canvas width changed to {value}")
    
    def _on_canvas_height_changed(self, value):
        """Handle canvas height change"""
        # Update canvas directly
        self.canvas.custom_canvas_height = value
        
        # Update config
        self.config["canvas_height"] = value
        
        # Force a redraw
        self.canvas.update_canvas()
        
        # If verbose is enabled, log the change
        if self.canvas.verbose:
            print(f"Canvas height changed to {value}")
    
    def _on_framerate_changed(self, value):
        """Handle frame rate change"""
        # Set frame rate for canvas updates
        self.canvas.set_frame_rate(value)
        
        # If we're using the test source, update its frame rate too
        if hasattr(self.artnet_listener, 'set_fps'):
            self.artnet_listener.set_fps(value)
            if self.canvas.verbose:
                print(f"Updated test source FPS to {value}")
    
    def _save_viz_settings_to_config(self):
        """Save current visualization settings to configuration file"""
        # Update config with current visualization settings
        self.config["pixel_size"] = self.canvas.pixel_size
        self.config["gap_x"] = self.canvas.gap_x
        self.config["gap_y"] = self.canvas.gap_y
        self.config["start_x"] = self.canvas.start_x
        self.config["start_y"] = self.canvas.start_y
        self.config["canvas_width"] = self.canvas.custom_canvas_width
        self.config["canvas_height"] = self.canvas.custom_canvas_height
        self.config["frame_rate"] = self.canvas.frame_rate
        self.config["verbose"] = False  # Always set verbose to False since we removed the control
        
        # Get the universe list from the UI
        universes = []
        for i in range(self.universe_list.count()):
            universes.append(int(self.universe_list.item(i).text()))
            
        # Update the universes in the config
        if 'artnet' not in self.config:
            self.config['artnet'] = {}
        self.config['artnet']['universes'] = universes
        
        # Save the configuration to file
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config.yaml")
        try:
            with open(config_path, "w") as f:
                yaml.dump(self.config, f)
            print(f"Visualization settings saved to {config_path}")
            
            restart_artnet = hasattr(self.artnet_listener, 'set_universes')
            if restart_artnet:
                msg = "Configuration saved successfully. Any universe changes may require a restart to fully take effect."
            else:
                msg = "Configuration saved successfully."
                
            QMessageBox.information(self, "Settings Saved", msg)
        except Exception as e:
            QMessageBox.warning(self, "Error Saving Settings", f"Could not save configuration: {e}")
    
    def _create_menus(self):
        """Create the application menus"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('&File')
        
        # Settings action
        settings_action = QAction('&Settings...', self)
        settings_action.setShortcut('Ctrl+,')
        settings_action.setStatusTip('Configure application settings')
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        
        # Exit action
        exit_action = QAction('E&xit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.setStatusTip('Exit application')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu('&Help')
        
        # About action
        about_action = QAction('&About', self)
        about_action.setStatusTip('Show About dialog')
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _open_settings(self):
        """Open the advanced settings dialog for network and test source settings"""
        # Create settings dialog with current config
        dialog = SettingsDialog(config=self.config, parent=self)
        
        # Show the dialog and check if user accepted
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Get the new config
            new_config = dialog.get_config()
            
            # Preserve universes from current config
            current_universes = self.config.get('artnet', {}).get('universes', [])
            if 'artnet' in new_config:
                new_config['artnet']['universes'] = current_universes
            
            # Check if we need to restart the data source
            restart_needed = self._check_restart_needed(new_config)
            
            # Update the config
            self.config = new_config
            
            # Update UI controls to match new settings (if any are still in both places)
            self._update_control_values()
            
            if restart_needed:
                # Show message to restart
                QMessageBox.information(
                    self,
                    "Restart Required",
                    "The changes you made require restarting the application to take effect."
                )
    
    def _update_control_values(self):
        """Update control values based on current configuration without triggering change events"""
        # Temporarily disconnect signals to avoid triggering updates
        self.pixel_size_spinner.blockSignals(True)
        self.gap_x_spinner.blockSignals(True)
        self.gap_y_spinner.blockSignals(True)
        self.start_x_spinner.blockSignals(True)
        self.start_y_spinner.blockSignals(True)
        self.canvas_width_spinner.blockSignals(True)
        self.canvas_height_spinner.blockSignals(True)
        self.fps_spinner.blockSignals(True)
        
        # Update control values
        self.pixel_size_spinner.setValue(self.canvas.pixel_size)
        self.gap_x_spinner.setValue(self.canvas.gap_x)
        self.gap_y_spinner.setValue(self.canvas.gap_y)
        self.start_x_spinner.setValue(self.canvas.start_x)
        self.start_y_spinner.setValue(self.canvas.start_y)
        self.canvas_width_spinner.setValue(self.canvas.custom_canvas_width)
        self.canvas_height_spinner.setValue(self.canvas.custom_canvas_height)
        self.fps_spinner.setValue(self.canvas.frame_rate)
        
        # Re-enable signals
        self.pixel_size_spinner.blockSignals(False)
        self.gap_x_spinner.blockSignals(False)
        self.gap_y_spinner.blockSignals(False)
        self.start_x_spinner.blockSignals(False)
        self.start_y_spinner.blockSignals(False)
        self.canvas_width_spinner.blockSignals(False)
        self.canvas_height_spinner.blockSignals(False)
        self.fps_spinner.blockSignals(False)
        
        # Update the universe list
        universes = []
        if 'artnet' in self.config and 'universes' in self.config['artnet']:
            universes = self.config['artnet']['universes']
        
        # Clear and repopulate the universe list
        self.universe_list.clear()
        for universe in universes:
            self.universe_list.addItem(QListWidgetItem(str(universe)))
    
    def _check_restart_needed(self, new_config):
        """Check if we need to restart the application to apply changes"""
        old_artnet = self.config.get('artnet', {})
        new_artnet = new_config.get('artnet', {})
        
        old_test = self.config.get('test_source', {})
        new_test = new_config.get('test_source', {})
        
        # Check if any settings that require restart have changed
        return (
            old_artnet.get('host') != new_artnet.get('host') or
            old_artnet.get('port') != new_artnet.get('port') or
            old_artnet.get('universes') != new_artnet.get('universes') or
            old_test.get('enabled') != new_test.get('enabled') or
            old_test.get('pattern') != new_test.get('pattern') or
            old_test.get('speed') != new_test.get('speed')
        )
    
    def _apply_viz_settings(self):
        """Apply visualization settings from config to canvas"""
        # Update canvas parameters
        self.canvas.pixel_size = self.config.get("pixel_size", 1)
        self.canvas.gap_x = self.config.get("gap_x", 0)
        self.canvas.gap_y = self.config.get("gap_y", 0)
        self.canvas.start_x = self.config.get("start_x", 0)
        self.canvas.start_y = self.config.get("start_y", 0)
        self.canvas.custom_canvas_width = self.config.get("canvas_width", 0)
        self.canvas.custom_canvas_height = self.config.get("canvas_height", 0)
        self.canvas.frame_rate = self.config.get("frame_rate", 44)
        self.canvas.verbose = False  # Always set verbose to False since we removed the control
        
        # Update timer with current frame rate
        self.canvas.set_frame_rate(self.canvas.frame_rate)
        
        # If using test source, update its frame rate too
        if hasattr(self.artnet_listener, 'set_fps'):
            self.artnet_listener.set_fps(self.canvas.frame_rate)
        
        # Force a complete redraw
        self.canvas.update_canvas()
        
        # Update UI controls to match
        self._update_control_values()
    
    def _show_about(self):
        """Show the about dialog"""
        QMessageBox.about(
            self,
            "About Art-Net Visualizer",
            """<h1>Art-Net Visualizer</h1>
            <p>A visualization application that listens to Art-Net DMX data,
            visualizes channels as pixels, and exposes itself as a Syphon
            source on macOS.</p>
            
            <p><b>Features:</b></p>
            <ul>
                <li>Direct universe management in the UI</li>
                <li>Customizable visualization settings</li>
                <li>Persistent window state and settings</li>
                <li>Syphon integration for macOS</li>
                <li>Built-in test pattern generator</li>
            </ul>
            
            <p>Created by <a href="https://github.com/bentodman">Ben Todman</a></p>
            <p>Version 1.1.0</p>
            <p>MIT License</p>"""
        )
    
    def closeEvent(self, event):
        """Handle window close event"""
        # Save window geometry to QSettings
        settings = QSettings()
        settings.setValue("geometry", self.saveGeometry())
        
        # Cleanup canvas before exit
        self.canvas.cleanup()
        event.accept()

    def _add_universe(self):
        """Add a universe to the listener list"""
        universe = self.add_universe_spinner.value()
        
        # Check if this universe is already in the list
        for i in range(self.universe_list.count()):
            if int(self.universe_list.item(i).text()) == universe:
                return  # Universe already in list
        
        # Add to the UI list
        self.universe_list.addItem(QListWidgetItem(str(universe)))
        
        # Update the universes in the Art-Net listener
        self._update_universes()
        
    def _remove_universe(self):
        """Remove selected universes from the list"""
        selected_items = self.universe_list.selectedItems()
        if not selected_items:
            return
            
        # Remove each selected item
        for item in selected_items:
            self.universe_list.takeItem(self.universe_list.row(item))
            
        # Update the universes in the Art-Net listener
        self._update_universes()
    
    def _update_universes(self):
        """Update the universes in the Art-Net listener"""
        # Get all universes from the list
        universes = []
        for i in range(self.universe_list.count()):
            universes.append(int(self.universe_list.item(i).text()))
            
        # Update the universes in the listener
        # Note: Updating universes dynamically might not have an immediate effect
        # for all Art-Net sources. The application restart message will still show
        # when saving to config, but this allows for dynamic testing.
        if hasattr(self.artnet_listener, 'set_universes'):
            self.artnet_listener.set_universes(universes)

def get_pattern_type_from_string(pattern_str):
    """Convert pattern string from config to PatternType enum"""
    try:
        return PatternType[pattern_str]
    except (KeyError, ValueError):
        print(f"Unknown pattern type: {pattern_str}, using default MOVING_BAR_H")
        return PatternType.MOVING_BAR_H

def main():
    # Load configuration (will try from file but use defaults if not found)
    config = load_config_from_file() or {}
    
    # Migrate any 'visualization' settings to root level for backward compatibility
    if 'visualization' in config:
        viz_config = config.pop('visualization')
        for key, value in viz_config.items():
            if key not in config:  # Don't overwrite existing root keys
                config[key] = value
    
    artnet_config = config.get('artnet', {})
    test_config = config.get('test_source', {})
    
    # Check for debug flags
    global DEBUG_MEMORY
    DEBUG_MEMORY = "--debug-memory" in sys.argv
    if DEBUG_MEMORY:
        print("Memory debugging enabled")
    
    # Determine whether to use test source or real Art-Net listener
    use_test_source = test_config.get('enabled', False)
    
    # Universe list is shared between test source and Art-Net listener
    universes = artnet_config.get('universes', [0])
    
    # Get frame rate from config
    frame_rate = config.get("frame_rate", 44)
    
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
            fps=frame_rate,  # Use the frame rate from config
            speed=speed
        )
        if DEBUG_MEMORY:
            print(f"Using Art-Net test source with pattern: {pattern_str}")
    else:
        # Create standard Art-Net listener
        data_source = ArtNetListener(
            host=artnet_config.get('host', '0.0.0.0'),
            port=artnet_config.get('port', 6454),
            universes=universes
        )
        if DEBUG_MEMORY:
            print("Using standard Art-Net listener")
    
    # Start the data source
    data_source.start()
    
    # Create and run the application
    app = QApplication(sys.argv)
    
    # Set up memory tracking if needed and available
    if DEBUG_MEMORY and MEMORY_TRACKING_AVAILABLE:
        setup_memory_tracking(app)
    
    # Set organization and application names for QSettings
    app.setOrganizationName("ArtNetViz")
    app.setOrganizationDomain("artnetviz.local")
    app.setApplicationName("ArtNetViz")
    
    window = MainWindow(data_source, config)
    
    # Restore window geometry from QSettings
    settings = QSettings()
    if settings.contains("geometry"):
        window.restoreGeometry(settings.value("geometry"))
    else:
        window.resize(900, 400)
        
    window.show()
    
    # Run the application
    exit_code = app.exec()
    
    # Stop the data source before exiting
    data_source.stop()
    
    # Perform final memory check if needed
    if DEBUG_MEMORY and MEMORY_TRACKING_AVAILABLE:
        print("\n=== Final Memory Analysis ===")
        memory_snapshot()
        memory_tracker.stop()
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

# Add this to your main app loop or a timer function
def periodic_cleanup():
    gc.collect()

def log_memory_usage():
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_mb = memory_info.rss / (1024 * 1024)
    print(f"Memory usage: {memory_mb:.2f} MB")

# Start at application beginning
tracemalloc.start()

# Add this to a debug menu option
def show_memory_snapshot():
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    for stat in top_stats[:10]:
        print(stat)

def log_memory(message=""):
    process = psutil.Process()
    mem_mb = process.memory_info().rss / (1024*1024)
    print(f"[MEMORY] {message}: {mem_mb:.2f} MB") 