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
import psutil
import tracemalloc
import gc
import traceback
import atexit
from typing import Optional, List, Dict, Tuple, Any, Union

# Disable App Nap on macOS to prevent the app from being throttled when in the background
if sys.platform == 'darwin':
    try:
        from Foundation import NSProcessInfo
        process_info = NSProcessInfo.processInfo()
        # Save activity reference as a global to prevent it from being garbage collected
        # Using NSActivityUserInitiated | NSActivityLatencyCritical for maximum prevention
        global _app_nap_activity
        _app_nap_activity = process_info.beginActivityWithOptions_reason_(
            0x00FFFFFF,  # NSActivityUserInitiated | NSActivityLatencyCritical
            "ArtNetViz requires full performance even in the background"
        )
        print("App Nap disabled successfully")
    except Exception as e:
        print(f"Could not disable App Nap: {e}")
        print("Continuing with App Nap enabled - may experience performance issues when app is in background")

# Continue with the rest of the imports
try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout,
        QWidget, QPushButton, QComboBox, QCheckBox, QTabWidget,
        QGridLayout, QSlider, QSpinBox, QDoubleSpinBox, QScrollArea,
        QSplitter, QToolBar, QStatusBar, QLineEdit, QDialog, QMenu, 
        QFileDialog, QColorDialog, QMessageBox, QGroupBox, QSizePolicy,
        QListWidget, QListWidgetItem
    )
    from PyQt6.QtGui import (
        QPixmap, QPainter, QColor, QPen, QBrush, QCursor, QFont,
        QAction, QIcon, QImage, QKeySequence, QPalette, QTransform
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QSize, QPoint, QRect, QObject, pyqtSignal, 
        QEvent, QMimeData, QBuffer, QIODevice, QByteArray,
        QMetaObject, QSettings, QUrl
    )
except ImportError:
    print("ERROR: PyQt6 is required to run this application.")
    print("Please install it with: pip install PyQt6")
    sys.exit(1)

import json
import objc
from objc import YES, NO
import Foundation
from Foundation import NSMakePoint, NSMakeSize, NSMakeRect
import Metal
import typing
import socket
import ipaddress
import re
from datetime import datetime
from enum import Enum

import syphon
from syphon.utils.numpy import copy_image_to_mtl_texture
from syphon.utils.raw import create_mtl_texture
try:
    import Metal
except ImportError:
    # Metal is not available, we'll handle this in the Syphon init
    pass

# Import our custom Art-Net listener and test source
from src.artnet_listener import ArtNetListener
from src.artnet_test_source import ArtNetTestSource, PatternType

# Import shared configuration
from src.config import DEBUG_MEMORY

# Global variables
_app_nap_activity = None  # Will hold the NSActivity reference for App Nap prevention

def cleanup_app_nap():
    """Release the App Nap activity object when the application is exiting."""
    global _app_nap_activity
    if _app_nap_activity is not None:
        try:
            # Properly end the activity before releasing the reference
            NSProcessInfo.processInfo().endActivity_(_app_nap_activity)
            _app_nap_activity = None
            print("App Nap activity released properly")
        except Exception as e:
            print(f"Error releasing App Nap activity: {e}")
            # Fallback - delete the reference
            del _app_nap_activity
            _app_nap_activity = None

# Register the cleanup function to be called on exit
atexit.register(cleanup_app_nap)

# Import our settings dialog
from src.settings_dialog import SettingsDialog, load_config_from_file

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
        
        # Initialize variables
        self.artnet_listener = artnet_listener
        self.pixel_size = pixel_size
        self.gap_x = gap_x
        self.gap_y = gap_y
        self.start_x = start_x
        self.start_y = start_y
        self.custom_canvas_width = canvas_width
        self.custom_canvas_height = canvas_height
        
        # Logging control
        self.verbose = False
        
        # Frame rate control
        self.frame_rate = 44  # Default to DMX standard ~44Hz
        
        # Memory tracking
        self._memory_tracking_enabled = True
        self._memory_check_interval = 60  # Check memory every 60 frames
        self._memory_soft_limit_mb = 180  # Perform light cleanup when over this limit
        self._memory_hard_limit_mb = 220  # Perform aggressive cleanup when over this limit
        self._memory_critical_limit_mb = 250  # Emergency cleanup when over this limit
        self._last_memory_usage_mb = 0
        self._consecutive_high_memory = 0  # Counter for consecutive memory readings above soft limit
        
        # Import psutil for memory tracking
        try:
            import psutil
            self._psutil_available = True
            self._process = psutil.Process()
        except ImportError:
            print("Warning: psutil not available, memory tracking disabled")
            self._psutil_available = False
        
        # Initialize Metal flag
        self.using_metal = False
        
        # Initialize tracking for Metal textures
        self._texture_pool = {}  # Format: {(width, height): [textures]}
        self._max_pool_size = 3  # Maximum number of textures to keep in the pool per size (reduced)
        self._texture_in_use = None  # Currently active texture
        self._texture_tracker = {}  # Track all textures created by this instance for leak detection
        self._total_textures_created = 0
        self._total_textures_released = 0
        self._last_pool_reset = 0  # Track when we last reset the pool
        self._last_texture_recreation = 0  # Track when we last recreated the texture
        self._last_syphon_restart = 0  # Track when we last restarted the Syphon server
        self._debug_memory = True  # Enable more verbose memory debugging
        
        # Cache for color objects
        self._color_cache = {}
        
        # Cache for coordinate calculations
        self._coordinate_cache = {}
        
        # Cache for Syphon frame data
        self._syphon_array = None
        self._syphon_array_dims = None
        
        # Numpy array pool for pixel data
        self._array_pool = {}  # Format: {(height, width, channels): [arrays]}
        self._max_array_pool_size = 2  # Reduced from 3 - Maximum arrays to keep per size
        self._array_in_use = {}  # Currently in-use arrays
        
        # Initialize Syphon
        self.init_syphon()
        
        # Check which Syphon methods are available (for debugging)
        self._check_syphon_methods()
        
        # Show detailed server information
        self._show_syphon_info()
        
        # Initialize pixmaps
        self.pixmap = None  # Scaled pixmap for preview
        self.full_res_pixmap = None  # Full-resolution pixmap for Syphon output
        self.max_preview_width = 1200  # Maximum width for the preview window
        self.max_preview_height = 800  # Maximum height for the preview window
        
        # Initialize painters
        self._painter = None
        self._full_res_painter = None
        
        # Frame counter for periodic cleanup
        self._frame_counter = 0
        
        # Set up the widget
        self.setMinimumSize(100, 100)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, 
            QSizePolicy.Policy.Expanding
        )
        
        # Create two timers - one for canvas updates and one for Syphon
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_canvas)
        
        # Create Syphon update timer only if we have a server
        if hasattr(self, 'server') and self.server:
            self.syphon_timer = QTimer(self)
            self.syphon_timer.timeout.connect(self.update_syphon_frame)
            self.syphon_timer.setTimerType(Qt.TimerType.PreciseTimer)
        
        # Configure timers with frame rate
        self.set_frame_rate(self.frame_rate)
        
        # Update initial canvas
        self.update_canvas()

    def init_syphon(self):
        """Initialize Syphon client for GPU-accelerated frame publishing"""
        try:
            import syphon
            
            # Store whether we have Syphon available
            self.syphon_available = True
            self.server = None  # Will be set if server creation succeeds
            self.using_metal = False  # Will be set to True if Metal is available
            
            # Check for various Syphon implementations
            self._check_syphon_methods()
            
            # Try Metal-based Syphon first (preferred)
            if hasattr(syphon, 'SyphonMetalServer'):
                try:
                    # Import needed libraries
                    import objc
                    import Metal
                    import syphon.utils.numpy
                    
                    # Verify Metal is fully available
                    if not hasattr(Metal, 'MTLCreateSystemDefaultDevice'):
                        print("Metal module found but MTLCreateSystemDefaultDevice not available")
                        raise ImportError("Metal implementation incomplete")
                    
                    # Create Metal device
                    self.metal_device = Metal.MTLCreateSystemDefaultDevice()
                    if not self.metal_device:
                        print("Could not create Metal device - hardware may not support Metal API")
                        raise RuntimeError("Could not create Metal device")
                    
                    # Create command queue
                    self.metal_command_queue = self.metal_device.newCommandQueue()
                    if not self.metal_command_queue:
                        print("Could not create Metal command queue")
                        raise RuntimeError("Could not create Metal command queue")
                    
                    # Initialize texture tracking
                    self._texture_tracker = {}  # Format: {texture_id: {size: (w, h), created_at: frame_num, last_used: frame_num}}
                    self._texture_pool = {}  # Format: {(width, height): [textures]}
                    self._texture_dimensions = (0, 0)
                    self._total_textures_created = 0
                    self._total_textures_released = 0
                    self._frame_counter = 0
                    self._debug_memory = hasattr(self, '_memory_tracking_enabled') and self._memory_tracking_enabled
                    
                    # Create server with Metal backend
                    self.server = syphon.SyphonMetalServer("ArtNetViz Syphon",
                                                      self.metal_device,
                                                      self.metal_command_queue)
                    if not self.server:
                        print("Could not create Syphon Metal server")
                        raise RuntimeError("Could not create Syphon Metal server")
                    
                    # Set flag to indicate we're using Metal
                    self.using_metal = True
                    
                    print(f"Metal-based Syphon server initialized successfully")
                    # Record the available methods on this server
                    if self.server:
                        method_list = [method for method in dir(self.server) if not method.startswith('_')]
                        print(f"Available server methods: {', '.join(method_list[:10])}...")
                    
                    # Create initial Metal texture
                    self._init_metal_texture()
                    
                except Exception as e:
                    print(f"Error initializing Metal-based Syphon: {e}")
                    self.using_metal = False
                    if hasattr(self, 'metal_device'):
                        self.metal_device = None
                    if hasattr(self, 'metal_command_queue'):
                        self.metal_command_queue = None
                    if hasattr(self, 'server'):
                        self.server = None
                    
                    # Try OpenGL fallback
                    print("Falling back to OpenGL-based Syphon...")
                    self._init_opengl_syphon()
            else:
                # No Metal support, try OpenGL
                print("Metal-based Syphon not available, trying OpenGL...")
                self._init_opengl_syphon()
                
        except ImportError as e:
            print(f"Syphon not available: {e}")
            self.syphon_available = False
        except Exception as e:
            print(f"Error initializing Syphon: {e}")
            self.syphon_available = False

    def _init_update_timer(self):
        """Initialize the update timer with proper cleanup handling"""
        # Make sure any existing timer is cleaned up first
        self._cleanup_timer()
        
        # Create a new timer
        self.update_timer = QTimer()
        self.update_timer.setTimerType(Qt.TimerType.PreciseTimer)
        
        # Set default frame rate
        self.set_frame_rate(self.frame_rate)
        
        # Connect using a direct connection that will be properly cleaned up
        self.update_timer.timeout.connect(self.update_syphon_frame)
        
        # Start the timer
        self.update_timer.start()
        
    def _cleanup_timer(self):
        """Safely clean up the update timer"""
        if hasattr(self, 'update_timer') and self.update_timer:
            try:
                # Stop the timer
                self.update_timer.stop()
                
                # Disconnect all connections
                try:
                    if hasattr(self.update_timer, 'timeout'):
                        self.update_timer.timeout.disconnect()
                except Exception as e:
                    print(f"Error disconnecting timer signals: {e}")
            except Exception as e:
                print(f"Error cleaning up timer: {e}")
                import traceback
                traceback.print_exc()

    def _init_ns_image_converter(self):
        """Initialize the NSImage converter for OpenGL mode"""
        try:
            # Import required Objective-C libraries
            from objc import objc_object
            from Foundation import NSImage, NSBitmapImageRep
            import Cocoa
            
            self._objc_utils = {
                'NSImage': NSImage,
                'NSBitmapImageRep': NSBitmapImageRep,
                'Cocoa': Cocoa
            }
            print("NSImage converter initialized successfully")
        except Exception as e:
            print(f"Error initializing NSImage converter: {str(e)}")
            self._objc_utils = None

    def _qimage_to_nsimage(self, qimage):
        """Convert a QImage to NSImage for Syphon compatibility"""
        # Initialize _objc_utils if it doesn't exist
        if not hasattr(self, '_objc_utils') or self._objc_utils is None:
            self._init_ns_image_converter()
        
        # Check again after initialization attempt
        if not self._objc_utils:
            print("No _objc_utils available, NSImage conversion failed")
            return None
        
        try:
            # Get image dimensions
            width = qimage.width()
            height = qimage.height()
            
            # Get raw image data
            bits = qimage.bits()
            bits.setsize(qimage.sizeInBytes())
            
            # Convert QImage to proper format if needed
            if qimage.format() != QImage.Format.Format_ARGB32:
                qimage = qimage.convertToFormat(QImage.Format.Format_ARGB32)
                bits = qimage.bits()
                bits.setsize(qimage.sizeInBytes())
            
            # Create NSBitmapImageRep
            NSBitmapImageRep = self._objc_utils['NSBitmapImageRep']
            bitmap = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
                None, width, height, 8, 4, True, False, 
                self._objc_utils['Cocoa'].NSDeviceRGBColorSpace, 
                width * 4, 32
            )
            
            # Copy data from QImage to bitmap with explicit size check
            bitmap_data = bitmap.bitmapData()
            buffer_size = width * height * 4
            
            # Make sure we're not trying to copy more data than QImage has
            qimage_size = qimage.sizeInBytes()
            if buffer_size > qimage_size:
                print(f"Warning: NSImage buffer size ({buffer_size}) exceeds QImage size ({qimage_size})")
                buffer_size = qimage_size
                
            # Copy ARGB data to NSBitmapImageRep
            memoryview(bitmap_data)[:buffer_size] = memoryview(bits)[:buffer_size]
            
            # Create NSImage from bitmap
            NSImage = self._objc_utils['NSImage']
            ns_image = NSImage.alloc().initWithSize_((width, height))
            ns_image.addRepresentation_(bitmap)
            
            # Log success
            if self._frame_counter % 300 == 0:
                print(f"Successfully created NSImage of size {width}x{height}")
                
            return ns_image
        except Exception as e:
            print(f"Error converting QImage to NSImage: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _init_metal_texture(self):
        """Initialize a Metal texture for Syphon frame publishing"""
        if not hasattr(self, 'using_metal') or not self.using_metal:
            return
            
        from Foundation import NSAutoreleasePool
        
        # Create an autorelease pool for texture creation
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            # Get the dimensions for the texture
            if hasattr(self, 'full_res_pixmap') and self.full_res_pixmap and not self.full_res_pixmap.isNull():
                width = self.full_res_pixmap.width()
                height = self.full_res_pixmap.height()
            else:
                # Default dimensions if no pixmap exists
                width = 512
                height = 10
                
            # Skip if dimensions are invalid
            if width <= 0 or height <= 0:
                print(f"Invalid texture dimensions: {width}x{height}")
                return
                
            # Check if we already have a valid texture with these dimensions
            if (hasattr(self, 'metal_texture') and self.metal_texture is not None and 
                hasattr(self, '_texture_dimensions') and self._texture_dimensions == (width, height)):
                # Already have a valid texture, skip recreation
                return
                
            # Check if we have a previously created texture with the same dimensions in the pool
            if hasattr(self, '_texture_pool') and (width, height) in self._texture_pool and self._texture_pool[(width, height)]:
                # Reuse a texture from the pool
                self.metal_texture = self._texture_pool[(width, height)].pop()
                texture_id = id(self.metal_texture)
                if hasattr(self, '_debug_memory') and self._debug_memory:
                    print(f"Reusing texture {texture_id} from pool for dimensions {width}x{height}")
                
                # Update dimensions
                self._texture_dimensions = (width, height)
                
                # Update tracker
                if hasattr(self, '_texture_tracker'):
                    if texture_id in self._texture_tracker:
                        self._texture_tracker[texture_id]['last_used'] = self._frame_counter
                    else:
                        # Re-register if not in tracker
                        self._texture_tracker[texture_id] = {
                            'size': (width, height),
                            'created_at': self._frame_counter,
                            'last_used': self._frame_counter
                        }
                    
                # Return early since we found a texture
                return
                
            # Before creating a new texture, release the old one properly
            if hasattr(self, 'metal_texture') and self.metal_texture is not None:
                # Get the current texture's dimensions for potential reuse
                old_dimensions = getattr(self, '_texture_dimensions', (0, 0))
                
                # Only add to pool if it's a different size (otherwise we'd be adding and removing the same size)
                if old_dimensions != (width, height):
                    self._return_texture_to_pool(self.metal_texture, old_dimensions)
                else:
                    # If same size, just release it
                    self._safely_release_texture(self.metal_texture)
                
                # Clear the reference
                self.metal_texture = None
            
            # Store dimensions for future reference
            self._texture_dimensions = (width, height)
            
            # Import Metal and create the texture
            import Metal
            descriptor = Metal.MTLTextureDescriptor.texture2DDescriptorWithPixelFormat_width_height_mipmapped_(
                Metal.MTLPixelFormatBGRA8Unorm,
                width,
                height,
                False
            )
            
            # Configure texture usage
            descriptor.setUsage_(Metal.MTLTextureUsageShaderRead | Metal.MTLTextureUsageRenderTarget)
            
            # Create the texture
            if not hasattr(self, 'metal_device') or self.metal_device is None:
                print("Metal device is not available - reinitializing...")
                self.metal_device = Metal.MTLCreateSystemDefaultDevice()
                if not self.metal_device:
                    print("Could not create Metal device")
                    return
                
                # Recreate command queue if needed
                if not hasattr(self, 'metal_command_queue') or self.metal_command_queue is None:
                    self.metal_command_queue = self.metal_device.newCommandQueue()
                    if not self.metal_command_queue:
                        print("Could not create Metal command queue")
                        return
            
            # Create the texture
            self.metal_texture = self.metal_device.newTextureWithDescriptor_(descriptor)
            
            if not self.metal_texture:
                print(f"Failed to create Metal texture with dimensions {width}x{height}")
                return
                
            # Set a label for debugging
            self.metal_texture.setLabel_(f"ArtNetViz_Texture_{width}x{height}")
            
            # Register in texture tracker
            if hasattr(self, '_texture_tracker'):
                texture_id = id(self.metal_texture)
                self._texture_tracker[texture_id] = {
                    'size': (width, height),
                    'created_at': getattr(self, '_frame_counter', 0),
                    'last_used': getattr(self, '_frame_counter', 0)
                }
            
            if hasattr(self, '_total_textures_created'):
                self._total_textures_created += 1
            
            if hasattr(self, '_debug_memory') and self._debug_memory:
                texture_id = id(self.metal_texture)
                print(f"Created new Metal texture {texture_id} with dimensions {width}x{height}")
                if hasattr(self, '_total_textures_created') and hasattr(self, '_total_textures_released'):
                    print(f"Total textures: created={self._total_textures_created}, released={self._total_textures_released}")
            
        except Exception as e:
            print(f"Error initializing Metal texture: {e}")
            if hasattr(self, 'metal_texture'):
                self.metal_texture = None
        finally:
            # Release autorelease pool
            del pool

    def _safely_release_texture(self, texture, from_pool=False):
        """Safely release a Metal texture."""
        if texture is None:
            return
            
        # Import required modules
        from Foundation import NSAutoreleasePool
        import objc
        import gc
        
        # Create an autorelease pool for texture release
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            texture_id = id(texture)
            
            # Check if texture is tracked
            is_tracked = hasattr(self, '_texture_tracker') and texture_id in self._texture_tracker
            
            # Print verbose info
            if hasattr(self, '_debug_memory') and self._debug_memory:
                print(f"Releasing texture {texture_id} - was in pool: {from_pool}, was tracked: {is_tracked}")
            
            # Check if texture is still in any pool and remove it
            if not from_pool and hasattr(self, '_texture_pool'):  # Only check if not already releasing from pool
                for size, textures in list(self._texture_pool.items()):
                    for i, pooled_texture in enumerate(textures):
                        if id(pooled_texture) == texture_id:
                            # Found in pool, remove it
                            textures.pop(i)
                            if hasattr(self, '_debug_memory') and self._debug_memory:
                                print(f"Removed texture {texture_id} from pool during release")
                            break
            
            # Remove from tracker
            if is_tracked:
                self._texture_tracker.pop(texture_id, None)
            
            # Explicitly set texture properties to nil before releasing
            try:
                # Get label for debugging
                label = texture.label()
                
                # Manually release the texture - this is a PyObjC object
                texture.setPurgeableState_(0)  # Make sure it's not purgeable
                texture.release()
                
                if hasattr(self, '_total_textures_released'):
                    self._total_textures_released += 1
                    
                if hasattr(self, '_debug_memory') and self._debug_memory:
                    print(f"Successfully released texture {texture_id} (label: {label})")
                    
            except Exception as e:
                print(f"Error during texture release of {texture_id}: {e}")
                
            # Suggest garbage collection
            gc.collect()
                
        except Exception as e:
            print(f"Error in _safely_release_texture: {e}")
        finally:
            # Always release the pool
            del pool

    def set_frame_rate(self, fps):
        """Set the frame rate for canvas updates"""
        self.frame_rate = fps
        # Calculate timer interval in milliseconds (1000ms / fps)
        interval_ms = int(1000 / fps) if fps > 0 else 1000
        
        # Update canvas timer interval if timer exists
        if hasattr(self, 'update_timer') and self.update_timer:
            try:
                self.update_timer.setInterval(interval_ms)
                if not self.update_timer.isActive():
                    self.update_timer.start()
            except Exception as e:
                print(f"Error updating canvas timer interval: {e}")
        
        # Update Syphon timer interval if it exists
        if hasattr(self, 'syphon_timer') and self.syphon_timer:
            try:
                self.syphon_timer.setInterval(interval_ms)
                if not self.syphon_timer.isActive():
                    self.syphon_timer.start()
            except Exception as e:
                print(f"Error updating Syphon timer interval: {e}")
        
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

    def _check_memory_usage(self):
        """Check current memory usage and perform cleanup if needed"""
        if not self._memory_tracking_enabled or not self._psutil_available:
            return False  # No cleanup performed
            
        try:
            # Get current memory usage
            mem_info = self._process.memory_info()
            current_usage_mb = mem_info.rss / (1024 * 1024)
            self._last_memory_usage_mb = current_usage_mb
            
            # Log memory usage periodically
            if self._frame_counter % 300 == 0:
                print(f"Memory usage: {current_usage_mb:.2f} MB")
            
            # Check if we're over limits
            cleanup_performed = False
            
            if current_usage_mb > self._memory_critical_limit_mb:
                print(f"CRITICAL: Memory usage ({current_usage_mb:.2f} MB) exceeds critical limit ({self._memory_critical_limit_mb} MB)!")
                self._perform_emergency_cleanup()
                
                # If we're still extremely high after emergency cleanup, restart the Syphon server
                if self._get_memory_usage_mb() > self._memory_critical_limit_mb * 0.9:
                    # Check if we haven't restarted too recently
                    if self._frame_counter - self._last_syphon_restart > 1000:  # About 22 seconds at 44fps
                        print("Memory still critical after cleanup, forcing Syphon server restart...")
                        self._restart_syphon_server()
                
                cleanup_performed = True
            elif current_usage_mb > self._memory_hard_limit_mb:
                print(f"WARNING: Memory usage ({current_usage_mb:.2f} MB) exceeds hard limit ({self._memory_hard_limit_mb} MB)")
                self._perform_hard_cleanup()
                
                # If memory is still high after hard cleanup, consider restarting Syphon
                if self._get_memory_usage_mb() > self._memory_hard_limit_mb * 0.9:
                    # Check if we haven't restarted too recently
                    if self._frame_counter - self._last_syphon_restart > 2000:  # About 45 seconds at 44fps
                        print("Memory still high after hard cleanup, restarting Syphon server...")
                        self._restart_syphon_server()
                
                cleanup_performed = True
            elif current_usage_mb > self._memory_soft_limit_mb:
                # Track consecutive readings over soft limit
                self._consecutive_high_memory += 1
                
                # If memory stays high for several checks, do a light cleanup
                if self._consecutive_high_memory >= 3:
                    print(f"NOTICE: Memory usage ({current_usage_mb:.2f} MB) consistently above soft limit ({self._memory_soft_limit_mb} MB)")
                    self._perform_soft_cleanup()
                    
                    # If we've had many consecutive high memory readings, force texture recreation
                    if self._consecutive_high_memory >= 5:
                        self._force_texture_recreation()
                    
                    # If memory remains consistently high for a long time, consider Syphon restart
                    if self._consecutive_high_memory >= 10 and self._frame_counter - self._last_syphon_restart > 3000:
                        print("Memory consistently high for extended period, restarting Syphon server...")
                        self._restart_syphon_server()
                    
                    self._consecutive_high_memory = 0  # Reset after taking action
                    cleanup_performed = True
            else:
                # Reset counter if memory usage is normal
                self._consecutive_high_memory = 0
                
            return cleanup_performed
            
        except Exception as e:
            print(f"Error checking memory usage: {e}")
            return False

    def _perform_soft_cleanup(self):
        """Perform a light cleanup to reduce memory usage"""
        print("Performing soft memory cleanup...")
        
        # Clear color cache
        if hasattr(self, '_color_cache'):
            self._color_cache.clear()
            
        # Clear coordinate cache
        if hasattr(self, '_coordinate_cache'):
            self._coordinate_cache.clear()
            
        # Trim array pool
        if hasattr(self, '_array_pool'):
            self._trim_array_pool()
            
        # Trigger garbage collection
        gc.collect()
        
        # Print memory status
        if self._psutil_available:
            current_usage_mb = self._get_memory_usage_mb()
            print(f"Memory usage after soft cleanup: {current_usage_mb:.2f} MB")
    
    def _perform_hard_cleanup(self):
        """Perform aggressive cleanup to reduce memory usage"""
        print("Performing hard memory cleanup...")
        
        # First do a soft cleanup
        self._perform_soft_cleanup()
        
        # Then do more aggressive cleanup:
        
        # Trim the texture pool more aggressively
        print("Trimming texture pool...")
        
        # If we have a texture pool, reduce its size
        if hasattr(self, '_texture_pool') and self._texture_pool:
            # Count before
            total_before = sum(len(textures) for textures in self._texture_pool.values())
            
            # Drop all but the most recently used texture from each pool
            for size, textures in list(self._texture_pool.items()):
                while len(textures) > 1:  # Keep only 1 per size
                    texture = textures.pop(0)
                    self._safely_release_texture(texture, from_pool=True)
            
            # Count after
            total_after = sum(len(textures) for textures in self._texture_pool.values())
            print(f"Reduced texture pool from {total_before} to {total_after} textures")
        
        # Clear all array pools
        if hasattr(self, '_array_pool') and self._array_pool:
            count = sum(len(arrays) for arrays in self._array_pool.values())
            print(f"Clearing {count} arrays from pool")
            self._cleanup_array_pool()
        
        # Force texture recreation
        self._force_texture_recreation()
        
        # Run full garbage collection
        print("Running full garbage collection...")
        import gc
        gc.collect()
        
        # Check if we need to restart Syphon server (if memory is still high and last restart was a while ago)
        mem_usage = self._get_memory_usage_mb()
        if mem_usage > self._memory_hard_limit_mb and self._frame_counter - self._last_syphon_restart > 3000:
            self._restart_syphon_server()
        
        # Print memory status
        if self._psutil_available:
            mem_info = self._process.memory_info()
            current_usage_mb = mem_info.rss / (1024 * 1024)
            print(f"Memory usage after hard cleanup: {current_usage_mb:.2f} MB")
    
    def _perform_emergency_cleanup(self):
        """Emergency cleanup when memory usage is critical"""
        print("!!!! EMERGENCY MEMORY CLEANUP TRIGGERED !!!!")
        
        # First try other cleanup methods
        self._perform_hard_cleanup()
        
        # Force release of ALL resources
        import gc
        
        # Create an autorelease pool for the emergency cleanup
        from Foundation import NSAutoreleasePool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            # Completely reset the texture pool
            self._reset_texture_pool("Emergency cleanup")
            
            # Force texture recreation
            self._force_texture_recreation()
            
            # Complete reset of the Syphon server
            self._restart_syphon_server()
            
            # Clear all Python object caches
            self._color_cache.clear()
            self._coordinate_cache.clear()
            
            # Clear all array pools
            self._cleanup_array_pool()
            
            # Run multiple garbage collections with compaction
            gc.collect(2)  # Full collection
            
            # Check if we have pympler for advanced memory debugging
            try:
                import pympler.muppy
                import pympler.summary
                
                # Perform memory leak detection
                all_objects = pympler.muppy.get_objects()
                summary = pympler.summary.summarize(all_objects)
                print("Memory usage by type:")
                pympler.summary.print_(summary, limit=20)
            except ImportError:
                pass
            
            # Force another collection after analysis
            gc.collect()
            
            # Print memory status after cleanup
            mem_usage = self._get_memory_usage_mb()
            print(f"Memory usage after emergency cleanup: {mem_usage:.2f} MB")
        except Exception as e:
            print(f"Error in emergency cleanup: {e}")
        finally:
            # Always release the pool
            del pool

    def _reset_texture_pool(self, reason="Manual reset"):
        """Reset the texture pool completely to reclaim memory."""
        from Foundation import NSAutoreleasePool
        
        # Create an autorelease pool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            print(f"Resetting texture pool ({reason})...")
            
            # Release all textures in the pool
            for size, textures in list(self._texture_pool.items()):
                for texture in textures:
                    self._safely_release_texture(texture, from_pool=True)
                # Clear the list
                self._texture_pool[size] = []
            
            # Clear empty pools
            self._texture_pool = {}
            
            # Update the last reset time
            self._last_pool_reset = self._frame_counter
            
            # Print memory status
            print(f"Memory usage after pool reset: {self._get_memory_usage_mb():.2f} MB")
            self._log_texture_stats()
        except Exception as e:
            print(f"Error resetting texture pool: {e}")
        finally:
            # Always release the pool
            del pool

    def _reduce_texture_pool_size(self):
        """Reduce the texture pool size if needed."""
        from Foundation import NSAutoreleasePool
        
        # Create an autorelease pool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            # For each size category, make sure we don't have too many textures
            for size, textures in list(self._texture_pool.items()):
                while len(textures) > self._max_pool_size:
                    # Release the excess textures
                    texture = textures.pop(0)  # Remove the oldest
                    self._safely_release_texture(texture, from_pool=True)
                    if self._debug_memory:
                        print(f"Reduced pool size for {size}: {len(textures)}")
        except Exception as e:
            print(f"Error reducing texture pool size: {e}")
        finally:
            # Always release the pool
            del pool

    def _trim_texture_pool(self):
        """Trim the texture pool to remove old unused textures."""
        from Foundation import NSAutoreleasePool
        import gc
        
        # Create an autorelease pool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            print("Trimming texture pool...")
            
            # Check for textures that haven't been used in a while
            current_frame = self._frame_counter
            old_frame_threshold = 500  # Reduced from 1000 to be more aggressive
            
            # First count how many textures we have in total
            total_textures = sum(len(textures) for textures in self._texture_pool.values())
            if self._debug_memory:
                print(f"Texture pool contains {total_textures} textures before trimming")
            
            # Always keep the most recently used texture of each size, limit others more aggressively
            for size, textures in list(self._texture_pool.items()):
                # Limit number of textures per size even further
                max_size = max(1, min(3, self._max_pool_size // 2))  # Keep at most 1-3 textures per size
                
                # If we have more than the max, remove oldest ones
                if len(textures) > max_size:
                    # Sort by last used time to ensure we keep the most recently used ones
                    textures.sort(
                        key=lambda t: self._texture_tracker.get(id(t), {}).get('last_used', 0),
                        reverse=True  # Most recently used first
                    )
                    
                    # Keep only the most recent ones
                    to_release = textures[max_size:]
                    textures[:] = textures[:max_size]
                    
                    # Release the others
                    for texture in to_release:
                        self._safely_release_texture(texture, from_pool=True)
                        if self._debug_memory:
                            print(f"Trimmed excess texture from pool (size {size})")
            
            # Now check all tracked textures for age
            for texture_id, info in list(self._texture_tracker.items()):
                last_used = info.get('last_used', 0)
                if (current_frame - last_used) > old_frame_threshold:
                    # Skip if it's the current texture
                    if hasattr(self, 'metal_texture') and id(self.metal_texture) == texture_id:
                        continue
                    
                    # Check if this texture is in any pool
                    for size, textures in list(self._texture_pool.items()):
                        for i, texture in enumerate(textures):
                            if id(texture) == texture_id:
                                # Remove from pool and release
                                textures.pop(i)
                                self._safely_release_texture(texture, from_pool=True)
                                if self._debug_memory:
                                    print(f"Trimmed old texture {texture_id} from pool")
                                break
            
            # Force garbage collection
            gc.collect()
            
            # Print updated stats
            self._log_texture_stats()
        except Exception as e:
            print(f"Error trimming texture pool: {e}")
        finally:
            # Always release the pool
            del pool

    def _force_texture_recreation(self):
        """Force texture recreation to avoid Metal texture leaks."""
        from Foundation import NSAutoreleasePool
        import gc
        
        # Create an autorelease pool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            print("Forcing texture recreation...")
            
            # Store current frame counter for later reference
            self._last_texture_recreation = getattr(self, '_frame_counter', 0)
            
            # Release the current texture if it exists
            if hasattr(self, 'metal_texture') and self.metal_texture:
                try:
                    # Get the current dimensions before releasing
                    dimensions = getattr(self, '_texture_dimensions', (0, 0))
                    
                    # Get texture ID for logging
                    texture_id = id(self.metal_texture)
                    print(f"Releasing current texture {texture_id} with dimensions {dimensions}")
                    
                    # Release the current texture
                    self._safely_release_texture(self.metal_texture)
                    self.metal_texture = None
                    
                    # Reset the texture dimensions
                    self._texture_dimensions = (0, 0)
                    
                except Exception as e:
                    print(f"Error releasing texture during recreation: {e}")
                    # Still clear the reference even if release fails
                    self.metal_texture = None
            
            # Clear out any textures that might be lingering
            gc.collect()
            
            # Also trim down the texture pool
            if hasattr(self, '_texture_pool'):
                # Count pooled textures
                pool_count = 0
                for size, textures in list(self._texture_pool.items()):
                    pool_count += len(textures)
                
                # Report the pool state
                print(f"Texture pool contains {pool_count} textures before cleanup")
                
                # Reduce the pool size significantly during recreation
                self._trim_texture_pool()
                
                # Count pooled textures after trimming
                pool_count = 0
                for size, textures in list(self._texture_pool.items()):
                    pool_count += len(textures)
                
                print(f"Texture pool contains {pool_count} textures after cleanup")
            
            print("Texture will be recreated on next frame")
            
            # Force a garbage collection pass
            gc.collect()
            
        except Exception as e:
            print(f"Error forcing texture recreation: {e}")
        finally:
            # Always release the pool
            del pool

    def _log_texture_stats(self):
        """Log texture usage statistics"""
        active_textures = len(self._texture_tracker)
        pooled_textures = sum(len(textures) for textures in self._texture_pool.values())
        print(f"Texture stats: created={self._total_textures_created}, "
              f"released={self._total_textures_released}, "
              f"active={active_textures}, pooled={pooled_textures}")

    def _return_texture_to_pool(self, texture, dimensions):
        """Return a texture to the pool for later reuse"""
        from Foundation import NSAutoreleasePool
        
        # Create an autorelease pool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            if not texture or dimensions == (0, 0):
                del pool
                return
                
            # Update texture usage tracking
            texture_id = id(texture)
            if texture_id in self._texture_tracker:
                self._texture_tracker[texture_id]['last_used'] = self._frame_counter
            
            # Initialize pool for this size if needed
            if dimensions not in self._texture_pool:
                self._texture_pool[dimensions] = []
            
            # Only add to pool if we haven't reached the max size
            if len(self._texture_pool[dimensions]) < self._max_pool_size:
                # Check if this exact texture is already in the pool (avoid duplication)
                for existing_texture in self._texture_pool[dimensions]:
                    if id(existing_texture) == texture_id:
                        # Already in pool, don't add again
                        if self._debug_memory:
                            print(f"Texture {texture_id} already in pool, not adding again")
                        del pool
                        return
                
                # Add to pool with reference count
                self._texture_pool[dimensions].append(texture)
                
                # Sort textures by last used time to ensure oldest are released first
                if texture_id in self._texture_tracker:
                    self._texture_pool[dimensions].sort(
                        key=lambda t: self._texture_tracker.get(id(t), {}).get('last_used', 0)
                    )
            else:
                # Pool is full, just release the texture
                self._safely_release_texture(texture, from_pool=True)
        except Exception as e:
            print(f"Error returning texture to pool: {e}")
        finally:
            # Always release the pool
            del pool

    def update_canvas(self):
        """Update the canvas with current DMX values"""
        try:
            # Increment frame counter
            self._frame_counter += 1
            
            # Check memory usage periodically
            if self._memory_tracking_enabled and self._frame_counter % self._memory_check_interval == 0:
                self._check_memory_usage()
            
            # Perform texture pool maintenance
            if self._frame_counter % 100 == 0:
                self._trim_texture_pool()
                
            # Reset texture pool periodically to avoid memory growth
            pool_reset_interval = 3000  # About 1 minute at 44fps (reduced from 5000)
            if self._frame_counter - self._last_pool_reset > pool_reset_interval:
                self._reset_texture_pool("Scheduled reset")
                
            # Look for orphaned texture objects periodically
            if self._frame_counter % 200 == 0:
                self._clean_orphaned_textures()
                
            # Recreate texture periodically to avoid Metal texture leaks
            texture_recreation_interval = 1500  # About 35 seconds at 44fps (reduced from 2000)
            if self._frame_counter - self._last_texture_recreation > texture_recreation_interval:
                self._force_texture_recreation()
                self._last_texture_recreation = self._frame_counter
                
            # Restart Syphon server periodically to mitigate memory leaks in the Syphon framework
            syphon_restart_interval = 7000  # About 2.5 minutes at 44fps (reduced from 10000)
            if self._frame_counter - self._last_syphon_restart > syphon_restart_interval:
                # Only restart if memory usage is above a threshold
                if self._get_memory_usage_mb() > (self._memory_soft_limit_mb * 0.8):  # 80% of soft limit
                    self._restart_syphon_server()
            
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
                
                # Calculate content dimensions - ensure at least one pixel of height for empty universes
                content_width = dmx_width * pixel_width_with_gap
                content_height = max(universe_count, 1) * pixel_height_with_gap
                
                # Determine canvas dimensions
                canvas_width = max(self.custom_canvas_width, content_width + self.start_x) if self.custom_canvas_width > 0 else content_width + self.start_x
                canvas_height = max(self.custom_canvas_height, content_height + self.start_y) if self.custom_canvas_height > 0 else content_height + self.start_y
                
                # Ensure minimum canvas dimensions
                canvas_width = max(canvas_width, 10)
                canvas_height = max(canvas_height, 10)
                
                # Check if we're creating a new pixmap or reusing existing one
                create_new_pixmap = (
                    self.full_res_pixmap is None or 
                    self.full_res_pixmap.width() != canvas_width or 
                    self.full_res_pixmap.height() != canvas_height
                )
                
                # Create or reuse the full resolution pixmap for Syphon output
                if create_new_pixmap:
                    # Create new pixmap
                    if self.full_res_pixmap is not None:
                        # Clear old pixmap first to release memory
                        del self.full_res_pixmap
                        gc.collect()  # Force garbage collection
                        
                    self.full_res_pixmap = QPixmap(canvas_width, canvas_height)
                    print(f"Created new full-res pixmap: {canvas_width}x{canvas_height}")
                else:
                    # Just clear the existing pixmap
                    self.full_res_pixmap.fill(Qt.GlobalColor.transparent)
                
                # Calculate preview dimensions with scaling if needed
                preview_width = canvas_width
                preview_height = canvas_height
                
                if preview_width > self.max_preview_width or preview_height > self.max_preview_height:
                    width_ratio = self.max_preview_width / preview_width
                    height_ratio = self.max_preview_height / preview_height
                    scale_factor = min(width_ratio, height_ratio)
                    
                    preview_width = int(preview_width * scale_factor)
                    preview_height = int(preview_height * scale_factor)
                
                # Ensure minimum preview dimensions
                preview_width = max(preview_width, 1)
                preview_height = max(preview_height, 1)
                
                # Manage preview pixmap
                create_new_preview = (
                    self.pixmap is None or 
                    self.pixmap.width() != preview_width or 
                    self.pixmap.height() != preview_height
                )
                
                if create_new_preview:
                    # Clear old pixmap first
                    if self.pixmap is not None:
                        del self.pixmap
                        gc.collect()  # Force garbage collection
                        
                    self.pixmap = QPixmap(preview_width, preview_height)
                else:
                    # Just clear the existing pixmap
                    self.pixmap.fill(Qt.GlobalColor.transparent)
                
                # Create QPainters for both pixmaps
                full_res_painter = QPainter(self.full_res_pixmap)
                preview_painter = QPainter(self.pixmap)
                
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
                            
                            # Get cached coordinates for preview
                            preview_x, preview_y, preview_size = self._get_cached_coordinates(
                                pixel_x, row_y, preview_width, canvas_width, preview_height, canvas_height
                            )
                            
                            preview_painter.fillRect(preview_x, preview_y, preview_size, preview_size, color)
                    
                    # End painters
                    full_res_painter.end()
                    preview_painter.end()
                    
                    # Clean up painter objects explicitly
                    del full_res_painter
                    del preview_painter
                    
                    # Update Syphon frame
                    self.update_syphon_frame()
                    
                    # Force update of the widget
                    self.update()
                    
                    # Periodic cleanup
                    if self._frame_counter % 60 == 0:
                        # Clear caches periodically to prevent memory growth
                        self._color_cache.clear()
                        self._coordinate_cache.clear()
                        
                        # Do a deeper cleanup every minute (60fps * 60 = 3600 frames or 44fps * 60 = 2640 frames)
                        if self._frame_counter % 3600 == 0 and self._frame_counter > 0:
                            self._do_major_cleanup()
                except Exception as e:
                    print(f"Error updating canvas: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    # Ensure painters are properly cleaned up if exception occurred
                    if 'full_res_painter' in locals() and full_res_painter.isActive():
                        full_res_painter.end()
                    if 'preview_painter' in locals() and preview_painter.isActive():
                        preview_painter.end()
            elif self.verbose:
                print("No universes found. Canvas not updated.")
        except Exception as e:
            print(f"Error updating canvas: {e}")
            import traceback
            traceback.print_exc()

    def _validate_frame_data(self, frame_width, frame_height):
        """Validate frame dimensions and check if there's actual content to display"""
        if frame_width <= 0 or frame_height <= 0:
            print(f"Invalid frame dimensions: {frame_width}x{frame_height}")
            return False
            
        # Check if there are any universes to display
        universe_count = len(self.artnet_listener.universes)
        if universe_count == 0:
            if self._frame_counter % 60 == 0:
                print("No universes to display")
            return False
            
        # Check if at least one universe has data
        has_data = False
        empty_universes = []
        for universe in self.artnet_listener.universes:
            data = self.artnet_listener.get_buffer(universe)
            if data is not None:
                has_data = True
                if len(data) == 0:
                    empty_universes.append(universe)
            else:
                empty_universes.append(universe)
                
        # Log empty universes periodically
        if empty_universes and self._frame_counter % 120 == 0:
            print(f"Empty or null universes: {empty_universes}")
            
        if not has_data and self._frame_counter % 60 == 0:
            # Print the number of universes and their sizes for debugging
            universe_info = []
            for universe in self.artnet_listener.universes:
                data = self.artnet_listener.get_buffer(universe)
                size = len(data) if data is not None else 0
                universe_info.append(f"Universe {universe}: {size} channels")
            print(f"Universe data: {universe_info}")
            print("No DMX data available in any universe")
            
        # Return true even if we have empty universes - we'll at least show the grid
        return universe_count > 0
    
    def update_syphon_frame(self):
        """Update the Syphon frame with current canvas content"""
        
        # Create an autorelease pool for this frame cycle
        import objc
        from Foundation import NSAutoreleasePool
        pool = NSAutoreleasePool.alloc().init()
        
        # Always increment frame counter whether or not server exists
        self._frame_counter += 1
        
        # Check if we need a pool reset (more frequently to avoid buildup)
        pool_reset_interval = 2000  # Reduced from 3000 frames (~45 seconds @ 44fps)
        if (self._frame_counter - self._last_pool_reset) > pool_reset_interval:
            self._reset_texture_pool("Scheduled reset")
            
        # More frequent texture trimming to remove unused textures
        trim_interval = 300  # Reduced from 500 frames
        if self._frame_counter % trim_interval == 0:
            self._trim_texture_pool()
        
        # Check if we need to force texture recreation (more frequently)
        texture_recreation_interval = 5000  # Reduced from 8800 frames (~2 minutes @ 44fps)
        if (self._frame_counter - self._last_texture_recreation) > texture_recreation_interval:
            self._force_texture_recreation()
            self._last_texture_recreation = self._frame_counter
        
        # Periodically synchronize object pools with GC
        sync_interval = 500  # Reduced from 1000 frames (~11 seconds @ 44fps)
        if self._frame_counter % sync_interval == 0:
            problem_count = self._synchronize_pools_with_gc()
            if problem_count > 0 and self._frame_counter % 2000 == 0:  # Reduced from 3000
                # If problems persist, try a harder cleanup
                self._perform_hard_cleanup()
        
        if not self.server:
            # Still drain the pool even if we didn't do anything
            del pool
            return
        
        try:
            # Skip if application is closing/closed
            if not hasattr(self, 'update_timer'):
                del pool
                return
                
            # Check which Syphon implementation we're using
            import syphon
            
            # Get pixmap dimensions
            if self.full_res_pixmap and not self.full_res_pixmap.isNull():
                width = self.full_res_pixmap.width()
                height = self.full_res_pixmap.height()
                
                # Only log occasionally to reduce console spam
                if self._frame_counter % 300 == 0:
                    print(f"Publishing frame with dimensions: {width}x{height}")
            else:
                width = 512
                height = 10
                if self._frame_counter % 60 == 0:
                    print(f"Using default dimensions: {width}x{height}")
            
            # Update texture tracker for current texture
            if hasattr(self, 'metal_texture') and self.metal_texture:
                texture_id = id(self.metal_texture)
                if texture_id in self._texture_tracker:
                    self._texture_tracker[texture_id]['last_used'] = self._frame_counter
                else:
                    # Re-register if somehow not in tracker
                    self._texture_tracker[texture_id] = {
                        'size': getattr(self, '_texture_dimensions', (0, 0)),
                        'created_at': self._frame_counter,
                        'last_used': self._frame_counter
                    }
            
            # Validate frame data
            if not self._validate_frame_data(width, height):
                # Create a very simple frame even when no data is available
                if self._frame_counter % 300 == 0:
                    print("Creating simple empty frame")
                
                # If we have no real data, we'll still send a simple frame
                # This helps keep the Syphon connection alive
                # The rest of the method will proceed with the default dimensions
            
            # More frequent memory cleanup
            cleanup_interval = 200  # frames (was 300)
            if self._frame_counter % cleanup_interval == 0 and self._frame_counter > 0:
                # Perform garbage collection
                gc.collect()
                
                # Check for orphaned textures that aren't being tracked properly
                self._clean_orphaned_textures()
                
                # Log memory usage periodically
                if self._psutil_available:
                    mem_info = self._process.memory_info()
                    current_usage_mb = mem_info.rss / (1024 * 1024)
                    print(f"Memory usage: {current_usage_mb:.2f} MB")
                    
                    # Perform texture cleanup when memory is getting high
                    if current_usage_mb > self._memory_soft_limit_mb * 0.8:
                        print(f"Memory usage approaching soft limit, cleaning texture pool")
                        self._trim_texture_pool()
            
            # Metal-based Syphon publishing
            if self.using_metal:
                try:
                    # Make sure we have a valid texture with the correct dimensions
                    current_dimensions = getattr(self, '_texture_dimensions', (0, 0))
                    if (not hasattr(self, 'metal_texture') or self.metal_texture is None or
                        current_dimensions != (width, height)):
                        # Only log when dimensions change
                        if current_dimensions != (width, height):
                            print(f"Creating new Metal texture with dimensions {width}x{height}")
                        self._init_metal_texture()
                    
                    # Skip if texture initialization failed
                    if not hasattr(self, 'metal_texture') or self.metal_texture is None:
                        if self._frame_counter % 60 == 0:
                            print("Skipping frame - no valid Metal texture")
                        del pool
                        return
                    
                    # Copy pixmap data to metal texture
                    if self.full_res_pixmap and not self.full_res_pixmap.isNull():
                        try:
                            # Convert QPixmap to QImage in RGBA format (only once)
                            image = self.full_res_pixmap.toImage()
                            if image.isNull():
                                del pool
                                return
                                
                            if image.format() != QImage.Format.Format_RGBA8888:
                                image = image.convertToFormat(QImage.Format.Format_RGBA8888)
                                if image.isNull():
                                    del pool
                                    return
                            
                            # Use most direct approach possible for copying data
                            import numpy as np
                            from syphon.utils.numpy import copy_image_to_mtl_texture
                            
                            # Get access to the raw image data
                            bytes_per_line = image.bytesPerLine()
                            bits_ptr = image.constBits()
                            if bits_ptr:
                                # Calculate total bytes needed
                                total_bytes = height * bytes_per_line
                                
                                # Set correct size for the buffer view
                                bits_ptr.setsize(total_bytes)
                                
                                # Create a numpy array directly from the QImage memory
                                buffer = np.frombuffer(bits_ptr, dtype=np.uint8, count=total_bytes)
                                
                                # Reshape the buffer to proper dimensions
                                if bytes_per_line == width * 4:  # Perfect alignment
                                    # Get a properly sized array from the pool
                                    pixel_array = self._get_array_from_pool(height, width, 4, np.uint8)
                                    
                                    # Copy data from buffer to our pooled array
                                    np.copyto(pixel_array, buffer.reshape((height, width, 4)))
                                    
                                    # Additional check for valid texture
                                    if (self.metal_texture is not None and 
                                        hasattr(self.metal_texture, 'width') and 
                                        self.metal_texture.width() == width and 
                                        self.metal_texture.height() == height):
                                        try:
                                            # Copy pixel data to Metal texture
                                            copy_image_to_mtl_texture(pixel_array, self.metal_texture)
                                        except Exception as e:
                                            print(f"Error copying data to texture: {e}")
                                            # Recreate texture next frame
                                            self._force_texture_recreation()
                                    else:
                                        if self._frame_counter % 60 == 0:
                                            print("Skipping texture update - texture dimensions mismatch")
                                            # Force texture recreation
                                            self._force_texture_recreation()
                                            
                                    # Return the array to the pool
                                    self._return_array_to_pool(pixel_array)
                                else:
                                    # With stride handling
                                    # Get a properly sized array from the pool
                                    pixel_array = self._get_array_from_pool(height, width, 4, np.uint8)
                                    
                                    # Copy data row by row respecting stride
                                    for y in range(height):
                                        row_start = y * bytes_per_line
                                        row_end = row_start + (width * 4)
                                        # Make sure we don't go past the buffer end
                                        if row_end <= total_bytes:
                                            row_data = buffer[row_start:row_end].reshape(width, 4)
                                            pixel_array[y] = row_data
                                    
                                    # Additional check for valid texture
                                    if (self.metal_texture is not None and 
                                        hasattr(self.metal_texture, 'width') and 
                                        self.metal_texture.width() == width and 
                                        self.metal_texture.height() == height):
                                        try:
                                            # Copy pixel data to Metal texture
                                            copy_image_to_mtl_texture(pixel_array, self.metal_texture)
                                        except Exception as e:
                                            print(f"Error copying data to texture: {e}")
                                            # Recreate texture next frame
                                            self._force_texture_recreation()
                                    else:
                                        if self._frame_counter % 60 == 0:
                                            print("Skipping texture update - texture dimensions mismatch")
                                            # Force texture recreation
                                            self._force_texture_recreation()
                                            
                                    # Return the array to the pool
                                    self._return_array_to_pool(pixel_array)
                            else:
                                # If direct buffer access fails, log once per session
                                if not hasattr(self, '_buffer_access_failed'):
                                    print("Warning: Failed to access QImage buffer directly")
                                    self._buffer_access_failed = True
                            
                            # Publish the frame - using the simplest API possible
                            try:
                                # Check that texture is valid and server exists
                                if (self.server is not None and hasattr(self.server, 'publish_frame_texture') and
                                    self.metal_texture is not None):
                                    # Double check texture dimensions before publishing
                                    if (hasattr(self.metal_texture, 'width') and 
                                        self.metal_texture.width() == width and 
                                        self.metal_texture.height() == height):
                                        self.server.publish_frame_texture(
                                            texture=self.metal_texture, 
                                            is_flipped=True  # Explicitly set is_flipped parameter
                                        )
                                        
                                        # Log occasionally
                                        if self._frame_counter % 300 == 0:
                                            print(f"Metal frame published: {width}x{height}")
                                    else:
                                        # Dimensions mismatch, recreate texture
                                        if self._frame_counter % 60 == 0:
                                            print(f"Texture dimensions mismatch: expected {width}x{height}, " +
                                                 f"got {self.metal_texture.width()}x{self.metal_texture.height()}")
                                        self._force_texture_recreation()
                                elif self.server is not None:
                                    # Fallback to simple publish
                                    self.server.publish()
                                    
                                    if self._frame_counter % 300 == 0:
                                        print("Using basic publish() method")
                                else:
                                    if self._frame_counter % 300 == 0:
                                        print("No server available for publishing")
                                
                            except Exception as e:
                                print(f"Error in frame publishing: {e}")
                                
                            # Clean up the QImage
                            del image
                            
                        except Exception as e:
                            print(f"Error in Metal texture data handling: {e}")
                            
                except Exception as e:
                    print(f"Error in Metal publishing: {e}")
                    
            # OpenGL publishing handled elsewhere...
            
        except Exception as e:
            print(f"Error in update_syphon_frame: {e}")
        finally:
            # Always release the pool
            del pool

    def _clean_orphaned_textures(self):
        """Find and clean up orphaned textures not properly tracked"""
        import gc
        
        # Create an autorelease pool
        from Foundation import NSAutoreleasePool
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            # Force a full garbage collection first
            gc.collect(2)  # Full collection
            
            # Get all Metal texture objects from gc
            metal_objects = []
            for obj in gc.get_objects():
                # Check for Metal texture objects by their class name
                class_name = obj.__class__.__name__ if hasattr(obj, '__class__') else ""
                if "MTLTexture" in class_name:
                    metal_objects.append(obj)
            
            # Count how many aren't in our tracker
            orphaned = 0
            for obj in metal_objects:
                obj_id = id(obj)
                if obj_id not in self._texture_tracker:
                    orphaned += 1
                    # Try to force release this object
                    if hasattr(obj, 'release'):
                        try:
                            obj.release()
                            # Set to None to help garbage collection
                            obj = None
                        except Exception as e:
                            print(f"Error releasing orphaned texture: {e}")
            
            if orphaned > 0:
                print(f"Found and cleaned {orphaned} orphaned texture objects")
                # Force garbage collection after cleanup
                gc.collect()
                
                # Check memory usage after cleanup
                mem_usage = self._get_memory_usage_mb()
                print(f"Memory usage: {mem_usage:.2f} MB")
                
                # If memory is still high after cleaning orphaned textures,
                # consider more aggressive cleanup
                if mem_usage > self._memory_soft_limit_mb:
                    print("Memory usage approaching soft limit, cleaning texture pool")
                    self._trim_texture_pool()
                    
                    # If we're still high after trimming, check if we should restart the server
                    if mem_usage > self._memory_hard_limit_mb and self._frame_counter - self._last_syphon_restart > 3000:
                        self._restart_syphon_server()
            
            return orphaned
        except Exception as e:
            print(f"Error in _clean_orphaned_textures: {e}")
            return 0
        finally:
            # Always release the pool
            del pool

    def _restart_syphon_server(self):
        """Perform cleanup without restarting the Syphon server."""
        from Foundation import NSAutoreleasePool
        
        # Create autorelease pool for the cleanup operation
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            print("Performing memory cleanup without restarting Syphon server (client doesn't like restarts)...")
            
            # Record the last restart time to prevent too frequent cleanup attempts
            self._last_syphon_restart = self._frame_counter
            
            # Force cleanup of texture resources but don't touch the server
            self._reset_texture_pool("Memory cleanup")
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Reset texture tracking variables but keep server
            if self.using_metal:
                try:
                    # Force texture recreation without server restart
                    self.metal_texture = None
                    self._texture_dimensions = (0, 0)
                    
                    print("Memory cleanup completed without server restart")
                except Exception as e:
                    print(f"Error during memory cleanup: {e}")
            
            # Force another garbage collection
            gc.collect()
            
            # Check memory after cleanup
            mem_usage = self._get_memory_usage_mb()
            print(f"Memory usage after cleanup: {mem_usage:.2f} MB")
            
        except Exception as e:
            print(f"Error in memory cleanup: {e}")
        finally:
            # Always release the pool
            del pool

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
        """Clean up all resources before the application exits."""
        print("Starting full application cleanup...")
        
        # Create an autorelease pool
        from Foundation import NSAutoreleasePool
        import gc
        pool = NSAutoreleasePool.alloc().init()
        
        try:
            # Stop Syphon server
            if hasattr(self, 'server') and self.server:
                print("Stopping Syphon server...")
                self.server.stop()
                self.server = None
                
            # Stop update timer
            if hasattr(self, 'update_timer') and self.update_timer:
                print("Stopping update timer...")
                self.update_timer.stop()
                self.update_timer = None
                
            # Stop Syphon timer
            if hasattr(self, 'syphon_timer') and self.syphon_timer:
                print("Stopping Syphon timer...")
                self.syphon_timer.stop()
                self.syphon_timer = None
                
            # Clean up Metal resources
            if hasattr(self, 'using_metal') and self.using_metal:
                print("Cleaning up Metal resources...")
                
                # Clean up texture pool
                if hasattr(self, '_texture_pool'):
                    pool_count = sum(len(textures) for textures in self._texture_pool.values())
                    print(f"Cleaning up texture pool with {pool_count} textures")
                    
                    for size, textures in list(self._texture_pool.items()):
                        while textures:
                            texture = textures.pop()
                            self._safely_release_texture(texture)
                    
                    self._texture_pool.clear()
                
                # Release the current texture
                if hasattr(self, 'metal_texture') and self.metal_texture:
                    print(f"Releasing texture {id(self.metal_texture)} - was tracked: {id(self.metal_texture) in self._texture_tracker}")
                    self._safely_release_texture(self.metal_texture)
                    self.metal_texture = None
                    
                # Clear any remaining tracked textures
                if hasattr(self, '_texture_tracker'):
                    for texture_id in list(self._texture_tracker.keys()):
                        print(f"Cleaning up tracked texture {texture_id}")
                        del self._texture_tracker[texture_id]
                    self._texture_tracker.clear()
                
                # Release Metal device and command queue if needed
                if hasattr(self, 'metal_command_queue'):
                    self.metal_command_queue = None
                
                if hasattr(self, 'metal_device'):
                    self.metal_device = None
            
            # Clean up numpy array pool
            if hasattr(self, '_array_pool'):
                array_count = sum(len(arrays) for arrays in self._array_pool.values())
                print(f"Cleaning up array pool with {array_count} arrays")
                self._cleanup_array_pool()
                
            # Clean up in-use array tracking
            if hasattr(self, '_array_in_use'):
                print(f"Clearing {len(self._array_in_use)} in-use array references")
                self._array_in_use.clear()
            
            # Clean up pixmaps
            print("Cleaning up pixmaps...")
            if hasattr(self, 'pixmap') and self.pixmap:
                self.pixmap = None
            if hasattr(self, 'full_res_pixmap') and self.full_res_pixmap:
                self.full_res_pixmap = None
            
            # Clean up Syphon
            if hasattr(self, 'syphon_available') and self.syphon_available:
                print("Cleaning up Syphon resources...")
                self.syphon_available = False
                self.server = None
                self.syphon_timer = None
                
                # Clean up Syphon client
                if hasattr(self, 'syphon_client'):
                    self.syphon_client.stop()
                    self.syphon_client = None
                
                # Clean up Syphon server
                if hasattr(self, 'syphon_server'):
                    self.syphon_server.stop()
                    self.syphon_server = None
                
                # Clean up Syphon connection
                if hasattr(self, 'syphon_connection'):
                    self.syphon_connection.close()
                    self.syphon_connection = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
                # Clean up Syphon frame data
                self._syphon_array = None
                self._syphon_array_dims = None
                
        except Exception as e:
            print(f"Error during cleanup: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Always release the pool
            del pool
            
        # Check if current texture is being properly tracked
        if (hasattr(self, 'metal_texture') and self.metal_texture and 
            id(self.metal_texture) not in self._texture_tracker):
            # Re-register the current texture
            print("Re-registering current texture in tracker")
            texture_id = id(self.metal_texture)
            self._texture_tracker[texture_id] = {
                'size': getattr(self, '_texture_dimensions', (0, 0)),
                'created_at': self._frame_counter,
                'last_used': self._frame_counter
            }
        
        # Perform a full memory analysis every 5 major cleanups (roughly every 5 minutes)
        if self._frame_counter % (5 * 2640) < 60:  # 2640 frames = 60 seconds at 44fps
            self._analyze_memory()
                    
        # Force garbage collection
        gc.collect()
        
        # Log memory usage after cleanup
        if self._psutil_available:
            mem_info = self._process.memory_info()
            current_usage_mb = mem_info.rss / (1024 * 1024)
            print(f"Memory usage after cleanup: {current_usage_mb:.2f} MB")

    def _analyze_memory(self):
        """Perform a full memory analysis to diagnose memory issues"""
        print("============== MEMORY ANALYSIS ==============")
        
        # Print current memory usage
        if self._psutil_available:
            mem_info = self._process.memory_info()
            current_usage_mb = mem_info.rss / (1024 * 1024)
            print(f"Current memory usage: {current_usage_mb:.2f} MB")
        
        # Print texture stats
        if hasattr(self, '_texture_tracker'):
            active_textures = len(self._texture_tracker)
            pooled_textures = sum(len(textures) for textures in self._texture_pool.values())
            print(f"Texture stats: created={self._total_textures_created}, "
                  f"released={self._total_textures_released}, "
                  f"active={active_textures}, pooled={pooled_textures}")
            
            # Print details of all tracked textures
            if active_textures > 0:
                print("Active textures:")
                for texture_id, info in self._texture_tracker.items():
                    created_frame = info.get('created_at', 0)
                    last_used_frame = info.get('last_used', 0)
                    frames_since_use = self._frame_counter - last_used_frame
                    size = info.get('size', (0, 0))
                    print(f"  - ID: {texture_id}, Size: {size[0]}x{size[1]}, "
                          f"Created at frame: {created_frame}, "
                          f"Last used: {last_used_frame} ({frames_since_use} frames ago)")
            
            # Print pool details
            if self._texture_pool:
                print("Texture pools:")
                for size, textures in self._texture_pool.items():
                    print(f"  - Size {size[0]}x{size[1]}: {len(textures)} textures")
        
        # Check if current texture is properly tracked
        if hasattr(self, 'metal_texture') and self.metal_texture:
            texture_id = id(self.metal_texture)
            is_tracked = texture_id in self._texture_tracker
            print(f"Current texture (ID: {texture_id}) is {'tracked' if is_tracked else 'NOT TRACKED'}")
        else:
            print("No current metal texture")
        
        # Print GC stats
        import gc
        gc_stats = gc.get_stats()
        print("Garbage collector stats:")
        for i, stats in enumerate(gc_stats):
            print(f"  - Generation {i}: collections={stats['collections']}, "
                  f"collected={stats.get('collected', 'N/A')}, "
                  f"uncollectable={stats.get('uncollectable', 'N/A')}")
        
        # Run garbage collection and measure memory change
        if self._psutil_available:
            before_gc = current_usage_mb
            gc.collect()
            mem_info = self._process.memory_info()
            after_gc = mem_info.rss / (1024 * 1024)
            print(f"Memory before GC: {before_gc:.2f} MB")
            print(f"Memory after GC:  {after_gc:.2f} MB")
            print(f"Memory freed:     {(before_gc - after_gc):.2f} MB")
        
        print("=========== END MEMORY ANALYSIS ============")

    def _get_array_from_pool(self, height, width, channels=4, dtype=None):
        """Get a numpy array from the pool or create a new one if needed"""
        import numpy as np
        
        # Default to uint8 if not specified
        if dtype is None:
            dtype = np.uint8
            
        # Create the key for this array size
        key = (height, width, channels, dtype)
        
        # Check if we have an array of this size in the pool
        if key in self._array_pool and self._array_pool[key]:
            # Get array from pool
            array = self._array_pool[key].pop()
            if self._debug_memory and self._frame_counter % 500 == 0:
                print(f"Reusing array from pool: {key}")
                
            # Mark as in use
            self._array_in_use[id(array)] = key
            return array
        else:
            # Create a new array
            array = np.zeros((height, width, channels), dtype=dtype)
            
            # Mark as in use
            self._array_in_use[id(array)] = key
            
            if self._debug_memory and self._frame_counter % 500 == 0:
                print(f"Created new array: {key}")
            return array
    
    def _return_array_to_pool(self, array):
        """Return a numpy array to the pool for reuse"""
        if array is None:
            return
            
        # Get the array ID
        array_id = id(array)
        
        # Check if this array is marked as in use
        if array_id in self._array_in_use:
            # Get the array dimensions
            key = self._array_in_use[array_id]
            
            # Remove from in-use tracking
            del self._array_in_use[array_id]
            
            # Initialize pool for this size if needed
            if key not in self._array_pool:
                self._array_pool[key] = []
                
            # Check if we're under the pool size limit
            if len(self._array_pool[key]) < self._max_array_pool_size:
                # Zero the array to ensure we're not keeping references to old data
                array.fill(0)
                
                # Add to pool
                self._array_pool[key].append(array)
                
                if self._debug_memory and self._frame_counter % 500 == 0:
                    print(f"Returned array to pool: {key}")
            else:
                # Just let it be garbage collected
                if self._debug_memory and self._frame_counter % 500 == 0:
                    print(f"Pool full, releasing array: {key}")
    
    def _trim_array_pool(self):
        """Trim the array pool to remove excess arrays"""
        # Remove excess arrays from the pool
        for key, arrays in list(self._array_pool.items()):
            # Keep only the maximum allowed number of arrays per size
            while len(arrays) > self._max_array_pool_size:
                arrays.pop(0)  # Remove the oldest array
                
        # Log pool status
        if self._debug_memory:
            total_arrays = sum(len(arrays) for arrays in self._array_pool.values())
            in_use = len(self._array_in_use)
            print(f"Array pool stats: pooled={total_arrays}, in_use={in_use}")
    
    def _cleanup_array_pool(self):
        """Clear the entire array pool"""
        self._array_pool.clear()
        # Don't clear _array_in_use as those arrays are still being referenced

    def _synchronize_pools_with_gc(self):
        """Synchronize object pools with the garbage collector to prevent leaks"""
        import gc
        
        # Force a garbage collection first to reduce reference counts
        gc.collect()
        
        # Get current reference counts for objects
        texture_refs = {}
        array_refs = {}
        
        # Check texture references
        for size, textures in list(self._texture_pool.items()):
            for texture in textures:
                texture_id = id(texture)
                texture_refs[texture_id] = sys.getrefcount(texture) - 3  # Account for this function's refs
                
        # Check array references
        for key, arrays in list(self._array_pool.items()):
            for array in arrays:
                array_id = id(array)
                array_refs[array_id] = sys.getrefcount(array) - 3  # Account for this function's refs
        
        # Log any objects with unexpected reference counts
        problematic_textures = []
        for texture_id, ref_count in texture_refs.items():
            if ref_count > 1:  # Should only have one reference (in our pool)
                problematic_textures.append(texture_id)
                if self._debug_memory:
                    print(f"WARNING: Texture {texture_id} has {ref_count} references")
                
        problematic_arrays = []
        for array_id, ref_count in array_refs.items():
            if ref_count > 1:  # Should only have one reference (in our pool)
                problematic_arrays.append(array_id)
                if self._debug_memory:
                    print(f"WARNING: Array {array_id} has {ref_count} references")
                
        if problematic_textures:
            print(f"WARNING: Found {len(problematic_textures)} textures with multiple references")
            
        if problematic_arrays:
            print(f"WARNING: Found {len(problematic_arrays)} arrays with multiple references")
        
        # Immediately clean up problematic textures - don't wait for periodic cleanup
        if problematic_textures:
            for size, textures in list(self._texture_pool.items()):
                # Find and remove problematic textures
                i = 0
                while i < len(textures):
                    if id(textures[i]) in problematic_textures:
                        # Release this problematic texture
                        texture = textures.pop(i)
                        self._safely_release_texture(texture, from_pool=True)
                        print(f"Removed problematic texture from pool")
                    else:
                        i += 1
            
        # Clean up problematic arrays
        if problematic_arrays:
            for key, arrays in list(self._array_pool.items()):
                # Find and remove problematic arrays
                i = 0
                while i < len(arrays):
                    if id(arrays[i]) in problematic_arrays:
                        # Just remove from pool, don't need explicit release for numpy arrays
                        arrays.pop(i)
                        print(f"Removed problematic array from pool")
                    else:
                        i += 1
        
        # If using Metal, do an orphaned texture check
        if hasattr(self, 'using_metal') and self.using_metal:
            orphaned = self._clean_orphaned_textures()
            if orphaned > 0:
                # Add these to our problem count
                return len(problematic_textures) + len(problematic_arrays) + orphaned
        
        # Every 10 minutes, do a deeper check and cleanup
        if self._frame_counter % 26400 == 0:  # ~10 minutes at 44fps
            print("Performing deep pool synchronization...")
            
            # Clean up texture pool entries that have problematic reference counts
            for size, textures in list(self._texture_pool.items()):
                self._texture_pool[size] = [t for t in textures if id(t) not in problematic_textures]
                
            # Clean up array pool entries that have problematic reference counts  
            for key, arrays in list(self._array_pool.items()):
                self._array_pool[key] = [a for a in arrays if id(a) not in problematic_arrays]
        
        # Return number of problematic objects found
        return len(problematic_textures) + len(problematic_arrays)

    def _check_syphon_methods(self):
        """Check which methods are available on the Syphon server object"""
        if not hasattr(self, 'server') or self.server is None:
            print("No Syphon server available")
            return
            
        try:
            # Log the server class type
            server_class = self.server.__class__.__name__
            print(f"Syphon server class: {server_class}")
            
            # Get all methods on the server object
            methods = [method for method in dir(self.server) if not method.startswith('_')]
            print(f"Available Syphon methods: {', '.join(methods)}")
            
            # Check for specific publishing methods
            publish_methods = [m for m in methods if 'publish' in m.lower()]
            if publish_methods:
                print(f"Publishing methods: {', '.join(publish_methods)}")
                for method in publish_methods:
                    try:
                        # Get method signature if possible
                        import inspect
                        signature = inspect.signature(getattr(self.server, method))
                        print(f"  - {method}{signature}")
                    except:
                        print(f"  - {method} (signature unknown)")
            else:
                print("No publishing methods found!")
                
        except Exception as e:
            print(f"Error checking Syphon methods: {str(e)}")

    def _show_syphon_info(self):
        """Show detailed information about the Syphon server for debugging"""
        if not hasattr(self, 'server') or self.server is None:
            print("No Syphon server available")
            return
            
        try:
            # Output header
            print("\n=== SYPHON SERVER INFORMATION ===")
            
            # Server type
            server_class = self.server.__class__.__name__
            print(f"Server class: {server_class}")
            
            # Server details
            if hasattr(self.server, 'serverName'):
                print(f"Server name: {self.server.serverName}")
            if hasattr(self.server, 'description'):
                print(f"Description: {self.server.description}")
                
            # List all attributes
            print("\nAll attributes:")
            for attr in dir(self.server):
                if not attr.startswith('__'):
                    value = getattr(self.server, attr)
                    if callable(value):
                        print(f"  {attr}() [method]")
                    else:
                        print(f"  {attr} = {value}")
            
            # Try to get information about publish methods
            print("\nDetailed publish methods:")
            publish_methods = [m for m in dir(self.server) if 'publish' in m.lower() and callable(getattr(self.server, m))]
            
            if publish_methods:
                import inspect
                for method in publish_methods:
                    try:
                        func = getattr(self.server, method)
                        sig = inspect.signature(func)
                        print(f"  {method}{sig}")
                        
                        # Try to get docstring
                        if func.__doc__:
                            print(f"    Documentation: {func.__doc__.strip()}")
                    except Exception as e:
                        print(f"  {method} - Error getting details: {e}")
            else:
                print("  No publish methods found")
                
            # Test publish method directly
            try:
                print("\nTesting publish method...")
                if hasattr(self.server, 'publish') and callable(self.server.publish):
                    self.server.publish()
                    print("Server publish() method called successfully")
            except Exception as e:
                print(f"Error calling publish() method: {e}")
                import traceback
                traceback.print_exc()
                
            print("=================================")
        except Exception as e:
            print(f"Error showing Syphon info: {e}")
            import traceback
            traceback.print_exc()

    def _get_memory_usage_mb(self):
        """Get current memory usage in MB"""
        if self._psutil_available:
            mem_info = self._process.memory_info()
            return mem_info.rss / (1024 * 1024)
        else:
            return 0

    def _init_opengl_syphon(self):
        """Initialize OpenGL-based Syphon as a fallback when Metal isn't available"""
        try:
            import syphon
            
            # Initialize NSImage conversion if needed for OpenGL mode
            if not hasattr(self, 'nsimage_context'):
                self._init_ns_image_converter()
            
            # Try legacy OpenGL-based Syphon classes
            if hasattr(syphon, 'SyphonServer'):
                print("Using legacy SyphonServer class")
                self.server = syphon.SyphonServer("ArtNetViz Syphon")
            elif hasattr(syphon, 'Server'):
                print("Using Server class")
                self.server = syphon.Server("ArtNetViz Syphon")
            else:
                print("No suitable Syphon server class found")
                return False
                
            print("OpenGL-based Syphon server initialized successfully")
            return True
            
        except Exception as e:
            print(f"Failed to initialize OpenGL-based Syphon: {e}")
            self.server = None
            return False

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
    mem_mb = process.memory_info().rss / (1024 * 1024)
    print(f"[MEMORY] {message}: {mem_mb:.2f} MB") 