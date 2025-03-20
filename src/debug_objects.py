#!/usr/bin/env python3
"""
Debug utilities for tracking object allocations and memory usage.
"""

import gc
import sys
import tracemalloc
import psutil
import os
import time
from collections import Counter
from PyQt6.QtGui import QPainter, QPixmap
from PyQt6.QtCore import QTimer, Qt
import numpy as np

class MemoryTracker:
    """Track memory usage and object counts."""
    
    def __init__(self):
        """Initialize the memory tracker."""
        self.enabled = False
        self.previous_counts = None
        self.start_snapshot = None
        self.memory_history = []  # Track memory usage over time
        self.last_check_time = 0
        self.leak_detection_enabled = False
        self.tracked_types = [
            QPainter, 
            QPixmap, 
            np.ndarray,
            bytes,
            bytearray
        ]
        self.tracked_type_names = [t.__name__ for t in self.tracked_types]
    
    def start(self):
        """Start tracking memory."""
        if self.enabled:
            return
        
        self.enabled = True
        tracemalloc.start()
        self.start_snapshot = tracemalloc.take_snapshot()
        self.previous_counts = self._count_objects()
        self.last_check_time = time.time()
        print("Memory tracking started")
    
    def stop(self):
        """Stop tracking memory."""
        if not self.enabled:
            return
        
        self.enabled = False
        tracemalloc.stop()
        print("Memory tracking stopped")
    
    def print_memory_usage(self):
        """Print current memory usage."""
        if not self.enabled:
            print("Memory tracking not enabled")
            return
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)
        
        # Track history
        now = time.time()
        self.memory_history.append((now, memory_mb))
        
        # Keep only the last 100 entries
        if len(self.memory_history) > 100:
            self.memory_history = self.memory_history[-100:]
        
        # Check for leaks - memory steadily increasing
        if self.leak_detection_enabled and len(self.memory_history) > 10:
            time_diff = now - self.last_check_time
            if time_diff > 30:  # Check every 30 seconds
                self.last_check_time = now
                self._check_for_leaks()
                
        print(f"Memory usage: {memory_mb:.2f} MB")
    
    def _check_for_leaks(self):
        """Check for possible memory leaks based on history."""
        if len(self.memory_history) < 10:
            return
            
        # Check if memory has been consistently increasing
        first_10_avg = sum(mem for _, mem in self.memory_history[:10]) / 10
        last_10_avg = sum(mem for _, mem in self.memory_history[-10:]) / 10
        
        # If memory increased by more than 20% in the monitoring period, warn about potential leak
        if last_10_avg > first_10_avg * 1.2:
            print("WARNING: Possible memory leak detected!")
            print(f"Memory increased from {first_10_avg:.2f} MB to {last_10_avg:.2f} MB")
            self.print_object_diff()
            
            # Get details about large objects
            self._print_large_objects()
    
    def _print_large_objects(self):
        """Print information about the largest objects in memory."""
        print("\nLargest objects in memory:")
        
        # Get all objects
        all_objects = gc.get_objects()
        
        # Filter for objects that support sys.getsizeof
        try:
            objects_with_size = [(obj, sys.getsizeof(obj)) for obj in all_objects 
                                if hasattr(obj, '__class__')]
        except:
            objects_with_size = []
            
        # Sort by size (largest first)
        objects_with_size.sort(key=lambda x: x[1], reverse=True)
        
        # Print top 10
        for i, (obj, size) in enumerate(objects_with_size[:10]):
            try:
                type_name = obj.__class__.__name__
                print(f"  {i+1}. {type_name}: {size/1024:.1f} KB")
            except:
                pass
    
    def _count_objects(self):
        """Count objects by type."""
        result = {}
        for tracked_type in self.tracked_types:
            count = sum(1 for obj in gc.get_objects() if isinstance(obj, tracked_type))
            result[tracked_type.__name__] = count
        return result
    
    def print_object_diff(self):
        """Print difference in object counts since last call."""
        if not self.enabled:
            print("Memory tracking not enabled")
            return
        
        current_counts = self._count_objects()
        
        print("Object count changes:")
        for type_name, count in current_counts.items():
            prev_count = self.previous_counts.get(type_name, 0)
            diff = count - prev_count
            print(f"  {type_name}: {prev_count} -> {count} ({diff:+d})")
        
        self.previous_counts = current_counts
    
    def print_memory_diff(self):
        """Print memory difference since tracking started."""
        if not self.enabled or not self.start_snapshot:
            print("Memory tracking not enabled or no start snapshot")
            return
        
        current_snapshot = tracemalloc.take_snapshot()
        
        print("Top memory allocations since start:")
        top_stats = current_snapshot.compare_to(self.start_snapshot, 'lineno')
        for stat in top_stats[:10]:
            print(f"  {stat}")
    
    def enable_leak_detection(self, enabled=True):
        """Enable or disable automatic memory leak detection."""
        self.leak_detection_enabled = enabled
        print(f"Memory leak detection {'enabled' if enabled else 'disabled'}")

# Create a global instance for use throughout the application
memory_tracker = MemoryTracker()

def setup_memory_tracking(app):
    """Set up periodic memory tracking in the application."""
    memory_tracker.start()
    memory_tracker.enable_leak_detection(True)
    
    # Create a timer for periodic tracking
    timer = QTimer()
    timer.timeout.connect(periodic_check)
    timer.start(5000)  # Check every 5 seconds
    
    # Store timer as an attribute of app to keep it alive
    app._memory_timer = timer
    
    return timer

def periodic_check():
    """Periodic memory and object count check."""
    print("\n--- Memory Check ---")
    memory_tracker.print_memory_usage()
    memory_tracker.print_object_diff()
    print("-------------------\n")

def memory_snapshot():
    """Take a memory snapshot and print top allocations."""
    print("\n--- Memory Snapshot ---")
    memory_tracker.print_memory_diff()
    print("----------------------\n")

if __name__ == "__main__":
    print("This is a utility module, not meant to be run directly.") 