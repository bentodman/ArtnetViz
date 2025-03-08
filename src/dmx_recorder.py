#!/usr/bin/env python3
"""
DMX Recorder module for ArtNetViz.

This module provides functionality to record ArtNet DMX data along with timecode
at a specified framerate, and play it back later with generated timecode.
"""

import os
import time
import json
import numpy as np
import threading
from datetime import datetime

class DMXRecorder:
    """
    Class for recording and playing back DMX data with timecode.
    """
    def __init__(self, artnet_source=None, frame_rate=44, recording_dir='recordings'):
        """
        Initialize the DMX recorder.
        
        Args:
            artnet_source: The ArtNet source (listener or test source) to record from
            frame_rate: Frame rate for recording (frames per second)
            recording_dir: Directory to save recordings
        """
        self.artnet_source = artnet_source
        self.frame_rate = frame_rate
        self.recording_dir = recording_dir
        self.recording = False
        self.playing = False
        self.record_thread = None
        self.playback_thread = None
        self.frame_interval = 1.0 / frame_rate
        self.current_recording = None
        self.current_playback = None
        self.playback_callback = None
        self.playback_universes = []
        self.frame_count = 0
        self.start_time = 0
        self.playback_position = 0
        self.loop_playback = False
        
        # Ensure recording directory exists
        os.makedirs(recording_dir, exist_ok=True)
    
    def set_artnet_source(self, artnet_source):
        """Set the ArtNet source to record from."""
        self.artnet_source = artnet_source
    
    def set_frame_rate(self, frame_rate):
        """Set the frame rate for recording and playback."""
        self.frame_rate = frame_rate
        self.frame_interval = 1.0 / frame_rate
    
    def start_recording(self):
        """Start recording DMX data with timecode."""
        if self.recording:
            print("Already recording")
            return False
        
        if not self.artnet_source:
            print("No ArtNet source set")
            return False
        
        self.recording = True
        self.frame_count = 0
        self.start_time = time.time()
        
        # Create a filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"dmx_recording_{timestamp}.json"
        filepath = os.path.join(self.recording_dir, filename)
        
        # Initialize recording metadata
        universes = self.artnet_source.universes
        self.current_recording = {
            'metadata': {
                'timestamp': timestamp,
                'frame_rate': self.frame_rate,
                'universes': universes
            },
            'frames': []
        }
        
        # Start recording thread
        self.record_thread = threading.Thread(target=self._record_thread)
        self.record_thread.daemon = True
        self.record_thread.start()
        
        print(f"Started recording to {filepath}")
        return True
    
    def stop_recording(self):
        """Stop recording and save the data."""
        if not self.recording:
            print("Not recording")
            return False
        
        self.recording = False
        if self.record_thread:
            self.record_thread.join(timeout=2.0)
            self.record_thread = None
        
        # Save recording to file
        if self.current_recording and len(self.current_recording['frames']) > 0:
            timestamp = self.current_recording['metadata']['timestamp']
            filename = f"dmx_recording_{timestamp}.json"
            filepath = os.path.join(self.recording_dir, filename)
            
            # Add final metadata
            self.current_recording['metadata']['frame_count'] = len(self.current_recording['frames'])
            self.current_recording['metadata']['duration'] = time.time() - self.start_time
            
            # Save to file
            with open(filepath, 'w') as f:
                json.dump(self.current_recording, f)
            
            print(f"Saved recording with {len(self.current_recording['frames'])} frames to {filepath}")
            return filepath
        else:
            print("No frames recorded")
            return False
    
    def _record_thread(self):
        """Thread function for recording DMX data."""
        last_frame_time = time.time()
        
        while self.recording:
            current_time = time.time()
            elapsed = current_time - last_frame_time
            
            # Check if it's time for the next frame
            if elapsed >= self.frame_interval:
                # Calculate timecode (in milliseconds since start)
                timecode_ms = int((current_time - self.start_time) * 1000)
                
                # Get DMX data for all universes
                frame_data = {}
                for universe in self.artnet_source.universes:
                    # Get buffer as bytes for more efficient storage
                    buffer = self.artnet_source.get_buffer(universe)
                    if buffer is not None:
                        # Convert numpy array to list of integers for JSON serialization
                        frame_data[str(universe)] = buffer.tolist()
                
                # Add frame to recording with timecode
                self.current_recording['frames'].append({
                    'timecode': timecode_ms,
                    'frame': self.frame_count,
                    'data': frame_data
                })
                
                self.frame_count += 1
                last_frame_time = current_time
            
            # Sleep a bit to avoid hogging CPU
            # Use a shorter sleep than frame interval to ensure timing accuracy
            time.sleep(min(self.frame_interval / 4, 0.01))
    
    def load_recording(self, filepath):
        """Load a DMX recording from file."""
        try:
            with open(filepath, 'r') as f:
                recording = json.load(f)
            
            # Validate recording format
            if not all(key in recording for key in ['metadata', 'frames']):
                print("Invalid recording file format")
                return False
            
            self.current_playback = recording
            self.playback_universes = [int(u) for u in recording['metadata']['universes']]
            self.playback_position = 0
            print(f"Loaded recording with {len(recording['frames'])} frames at {recording['metadata']['frame_rate']} fps")
            return True
        except Exception as e:
            print(f"Error loading recording: {e}")
            return False
    
    def start_playback(self, callback=None, loop=False):
        """
        Start playing back the loaded recording.
        
        Args:
            callback: Function to call with (universe, dmx_data) for each frame
            loop: Whether to loop the playback
        """
        if self.playing:
            print("Already playing")
            return False
        
        if not self.current_playback:
            print("No recording loaded")
            return False
        
        self.playing = True
        self.playback_callback = callback
        self.loop_playback = loop
        self.start_time = time.time()
        
        # Start playback thread
        self.playback_thread = threading.Thread(target=self._playback_thread)
        self.playback_thread.daemon = True
        self.playback_thread.start()
        
        print("Started playback")
        return True
    
    def stop_playback(self):
        """Stop the playback."""
        if not self.playing:
            print("Not playing")
            return False
        
        self.playing = False
        if self.playback_thread:
            self.playback_thread.join(timeout=2.0)
            self.playback_thread = None
        
        print("Stopped playback")
        return True
    
    def seek_playback(self, position_ms):
        """
        Seek to a specific position in the playback.
        
        Args:
            position_ms: Position in milliseconds
        """
        if not self.current_playback:
            return False
        
        # Find the closest frame to the requested position
        frames = self.current_playback['frames']
        
        # Simple linear search (could be optimized with binary search)
        closest_idx = 0
        for i, frame in enumerate(frames):
            if frame['timecode'] <= position_ms:
                closest_idx = i
            else:
                break
        
        self.playback_position = closest_idx
        return True
    
    def _playback_thread(self):
        """Thread function for playing back DMX data."""
        frames = self.current_playback['frames']
        frame_rate = self.current_playback['metadata']['frame_rate']
        frame_interval = 1.0 / frame_rate
        
        while self.playing and frames:
            if self.playback_position >= len(frames):
                if self.loop_playback:
                    # Loop back to beginning
                    self.playback_position = 0
                    self.start_time = time.time()
                else:
                    # End of playback
                    self.playing = False
                    break
            
            # Get current frame
            frame = frames[self.playback_position]
            
            # Current playback time
            current_time = time.time()
            elapsed_ms = int((current_time - self.start_time) * 1000)
            
            # Check if it's time for this frame
            if elapsed_ms >= frame['timecode']:
                # Process frame data
                if self.playback_callback:
                    frame_data = frame['data']
                    for universe_str, dmx_data in frame_data.items():
                        universe = int(universe_str)
                        # Convert list back to numpy array
                        dmx_array = np.array(dmx_data, dtype=np.uint8)
                        self.playback_callback(universe, dmx_array)
                
                # Move to next frame
                self.playback_position += 1
            
            # Sleep a bit to avoid hogging CPU
            time.sleep(min(frame_interval / 4, 0.01))
    
    def get_recording_status(self):
        """Get the current recording status."""
        if not self.recording:
            return {'recording': False}
        
        status = {
            'recording': True,
            'frame_count': self.frame_count,
            'elapsed': time.time() - self.start_time,
            'universes': self.artnet_source.universes if self.artnet_source else []
        }
        return status
    
    def get_playback_status(self):
        """Get the current playback status."""
        if not self.playing or not self.current_playback:
            return {'playing': False}
        
        frames = self.current_playback['frames']
        total_frames = len(frames)
        
        if self.playback_position < total_frames:
            current_timecode = frames[self.playback_position]['timecode']
        else:
            current_timecode = 0
        
        status = {
            'playing': True,
            'position': self.playback_position,
            'total_frames': total_frames,
            'current_timecode': current_timecode,
            'elapsed': time.time() - self.start_time,
            'frame_rate': self.current_playback['metadata']['frame_rate'],
            'universes': self.playback_universes
        }
        return status
    
    def list_recordings(self):
        """List available recordings."""
        recordings = []
        for filename in os.listdir(self.recording_dir):
            if filename.startswith("dmx_recording_") and filename.endswith(".json"):
                filepath = os.path.join(self.recording_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        recording = json.load(f)
                    
                    metadata = recording['metadata']
                    recordings.append({
                        'filename': filename,
                        'filepath': filepath,
                        'timestamp': metadata.get('timestamp', ''),
                        'frame_count': metadata.get('frame_count', 0),
                        'frame_rate': metadata.get('frame_rate', 0),
                        'duration': metadata.get('duration', 0),
                        'universes': metadata.get('universes', [])
                    })
                except Exception as e:
                    print(f"Error reading recording {filename}: {e}")
        
        return sorted(recordings, key=lambda x: x['timestamp'], reverse=True)

class ArtNetPlaybackSource:
    """
    A class that mimics the ArtNetListener interface but plays back recorded data.
    This allows direct replacement of the ArtNetListener in the main application.
    """
    def __init__(self, dmx_recorder):
        """
        Initialize the Art-Net playback source.
        
        Args:
            dmx_recorder: The DMXRecorder instance to use for playback
        """
        self.dmx_recorder = dmx_recorder
        self.universes = []
        self.buffers = {}
        self.running = False
        self.fps = dmx_recorder.frame_rate
    
    def start(self):
        """Start the playback source."""
        if not self.dmx_recorder.current_playback:
            print("No recording loaded")
            return False
        
        # If already running, stop first
        if self.running:
            self.stop()
        
        # Set universes from playback data
        self.universes = self.dmx_recorder.playback_universes
        self.running = True
        
        # Initialize buffers for each universe if not already initialized
        for universe in self.universes:
            if universe not in self.buffers:
                self.buffers[universe] = np.zeros(512, dtype=np.uint8)
        
        # Start playback with callback to update buffers
        if not self.dmx_recorder.playing:
            self.dmx_recorder.start_playback(callback=self._update_buffer)
        
        print(f"Playback source started with {len(self.universes)} universes")
        return True
    
    def stop(self):
        """Stop the playback source."""
        if self.running:
            self.running = False
            self.dmx_recorder.stop_playback()
            print("Playback source stopped")
    
    def _update_buffer(self, universe, dmx_data):
        """Callback to update DMX buffers during playback."""
        if universe in self.buffers:
            self.buffers[universe] = dmx_data
    
    def get_buffer(self, universe):
        """Get the current DMX buffer for a specific universe."""
        return self.buffers.get(universe, np.zeros(512, dtype=np.uint8))
    
    def get_all_buffers(self):
        """Get all DMX buffers in universe order."""
        return [self.get_buffer(universe) for universe in self.universes]
    
    def is_running(self):
        """Check if the source is running."""
        return self.running
    
    def set_fps(self, fps):
        """Set the frames per second for playback."""
        self.fps = fps
        self.dmx_recorder.set_frame_rate(fps)
        
    def set_universes(self, universes):
        """Set the universes to listen to, updating buffers as necessary."""
        if not universes:
            universes = [0]  # Default to universe 0 if empty
            
        universes = sorted(universes)
        
        # Check if anything changed
        if self.universes == universes:
            return False
            
        # Remove buffers for universes that are no longer needed
        for universe in list(self.buffers.keys()):
            if universe not in universes:
                del self.buffers[universe]
                
        # Add buffers for new universes
        for universe in universes:
            if universe not in self.buffers:
                self.buffers[universe] = np.zeros(512, dtype=np.uint8)
                
        # Update the universe list
        self.universes = universes
        return True 