#!/usr/bin/env python3
"""
Debug utilities for tracking object allocations and memory usage.
"""

import gc
import sys
import tracemalloc
import psutil
import os
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
        print(f"Memory usage: {memory_mb:.2f} MB")
    
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

# Create a global instance for use throughout the application
memory_tracker = MemoryTracker()

def setup_memory_tracking(app):
    """Set up periodic memory tracking in the application."""
    memory_tracker.start()
    
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