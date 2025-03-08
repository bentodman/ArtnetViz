#!/usr/bin/env python3
"""
Art-Net test pattern generator for visualizer testing.

This module provides a class that generates various test patterns that simulate
Art-Net DMX data for testing the visualizer without needing an external Art-Net controller.
"""

import threading
import time
import numpy as np
import math
from enum import Enum, auto

class PatternType(Enum):
    """Enum for different test pattern types"""
    GRADIENT_H = auto()  # Horizontal gradient
    GRADIENT_V = auto()  # Vertical gradient
    CHECKERBOARD = auto()  # Checkerboard pattern
    MOVING_BAR_H = auto()  # Horizontal moving bar
    MOVING_BAR_V = auto()  # Vertical moving bar
    PULSE = auto()  # Pulsing brightness
    RANDOM = auto()  # Random noise
    SINE_WAVE = auto()  # Sine wave

class ArtNetTestSource:
    """
    A class that generates test patterns simulating Art-Net DMX data.
    """
    
    def __init__(self, universes=None, pattern_type=PatternType.GRADIENT_H, fps=44, speed=1.0):
        """
        Initialize Art-Net test pattern generator.
        
        Args:
            universes (list): List of universes to generate
            pattern_type (PatternType): Type of pattern to generate
            fps (int): Frames per second for pattern updates
            speed (float): Speed multiplier for animations
        """
        self.universes = sorted(universes) if universes else [0]
        self.pattern_type = pattern_type
        self.fps = fps
        self.speed = speed
        self.running = False
        self.thread = None
        self.buffers = {}
        self.frame_counter = 0
        
        # Initialize a buffer for each universe with zeros
        for universe in self.universes:
            self.buffers[universe] = np.zeros(512, dtype=np.uint8)
    
    def set_pattern(self, pattern_type):
        """Set the pattern type to generate"""
        self.pattern_type = pattern_type
    
    def set_speed(self, speed):
        """Set the animation speed"""
        self.speed = speed
    
    def set_fps(self, fps):
        """Set the frames per second for pattern updates"""
        self.fps = fps
    
    def _pattern_thread(self):
        """Thread function that generates the test patterns"""
        interval = 1.0 / self.fps
        next_time = time.time() + interval
        
        while self.running:
            # Generate the pattern for this frame
            self._generate_pattern()
            
            # Increment frame counter
            self.frame_counter += 1
            
            # Sleep until the next frame
            now = time.time()
            sleep_time = next_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)
            next_time = now + interval
    
    def _generate_pattern(self):
        """Generate the test pattern for this frame"""
        # Get current time and frame for animation
        t = self.frame_counter * self.speed * 0.05
        
        # Generate pattern according to type
        if self.pattern_type == PatternType.GRADIENT_H:
            self._generate_horizontal_gradient()
        elif self.pattern_type == PatternType.GRADIENT_V:
            self._generate_vertical_gradient()
        elif self.pattern_type == PatternType.CHECKERBOARD:
            self._generate_checkerboard(t)
        elif self.pattern_type == PatternType.MOVING_BAR_H:
            self._generate_moving_bar_h(t)
        elif self.pattern_type == PatternType.MOVING_BAR_V:
            self._generate_moving_bar_v(t)
        elif self.pattern_type == PatternType.PULSE:
            self._generate_pulse(t)
        elif self.pattern_type == PatternType.RANDOM:
            self._generate_random()
        elif self.pattern_type == PatternType.SINE_WAVE:
            self._generate_sine_wave(t)
    
    def _generate_horizontal_gradient(self):
        """Generate a horizontal gradient pattern"""
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            
            # Create a gradient from 0 to 255 across the 512 channels
            for i in range(512):
                value = int((i / 511) * 255)
                buffer[i] = value
            
            self.buffers[universe] = buffer
    
    def _generate_vertical_gradient(self):
        """Generate a vertical gradient pattern"""
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            
            # All channels in this universe have the same value
            # But the value varies across universes
            value = 0
            if len(self.universes) > 1:
                value = int((universe_idx / (len(self.universes) - 1)) * 255)
            
            buffer.fill(value)
            self.buffers[universe] = buffer
    
    def _generate_checkerboard(self, t):
        """Generate a checkerboard pattern"""
        # Size of each checker square (channels)
        checker_size = 32
        # Animation shift
        shift = int(t * 20) % (checker_size * 2)
        
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            
            for i in range(512):
                # Determine if this position should be on or off
                x_checker = ((i + shift) // checker_size) % 2
                y_checker = (universe_idx // checker_size) % 2
                
                if (x_checker + y_checker) % 2 == 0:
                    buffer[i] = 255
                else:
                    buffer[i] = 0
            
            self.buffers[universe] = buffer
    
    def _generate_moving_bar_h(self, t):
        """Generate a horizontal moving bar pattern"""
        bar_width = 50  # Width of the bar in channels
        position = int((t * 200) % 562) - 50  # Position with overflow for smooth entry/exit
        
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            
            for i in range(512):
                if position <= i < position + bar_width:
                    # Inside the bar
                    buffer[i] = 255
            
            self.buffers[universe] = buffer
    
    def _generate_moving_bar_v(self, t):
        """Generate a vertical moving bar pattern"""
        if len(self.universes) <= 1:
            # Fall back to horizontal if we only have one universe
            return self._generate_moving_bar_h(t)
        
        bar_height = max(1, len(self.universes) // 4)  # Height of the bar in universes
        total_height = len(self.universes) + bar_height
        position = int((t * 100) % total_height) - bar_height  # Position with overflow
        
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            
            if position <= universe_idx < position + bar_height:
                # This universe is inside the bar
                buffer.fill(255)
            
            self.buffers[universe] = buffer
    
    def _generate_pulse(self, t):
        """Generate a pulsing brightness pattern"""
        # Value from 0 to 255 based on sine wave
        value = int(((math.sin(t * 2) + 1) / 2) * 255)
        
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            buffer.fill(value)
            self.buffers[universe] = buffer
    
    def _generate_random(self):
        """Generate random noise pattern"""
        for universe_idx, universe in enumerate(self.universes):
            # Create random values between 0 and 255
            buffer = np.random.randint(0, 256, 512, dtype=np.uint8)
            self.buffers[universe] = buffer
    
    def _generate_sine_wave(self, t):
        """Generate a sine wave pattern"""
        for universe_idx, universe in enumerate(self.universes):
            buffer = np.zeros(512, dtype=np.uint8)
            
            for i in range(512):
                # Phase shift based on position
                phase = i / 30.0 + t * 5
                # Value from 0 to 255 based on sine wave
                value = int(((math.sin(phase) + 1) / 2) * 255)
                buffer[i] = value
            
            self.buffers[universe] = buffer
    
    def start(self):
        """Start generating test patterns."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._pattern_thread)
        self.thread.daemon = True
        self.thread.start()
        print(f"Art-Net test pattern generator started with {self.pattern_type.name} pattern")
    
    def stop(self):
        """Stop generating test patterns."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
            self.thread = None
        print("Art-Net test pattern generator stopped")
    
    def get_buffer(self, universe):
        """Get the current DMX buffer for a specific universe."""
        return self.buffers.get(universe, np.zeros(512, dtype=np.uint8))
    
    def get_all_buffers(self):
        """Get all DMX buffers in universe order."""
        return [self.get_buffer(universe) for universe in self.universes]
    
    def is_running(self):
        """Check if the generator is running."""
        return self.running 