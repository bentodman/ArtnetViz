#!/usr/bin/env python3
"""
Custom Art-Net listener that properly handles port sharing with other Art-Net applications.
"""

import socket
import threading
import time
import numpy as np
import struct

class ArtNetPacket:
    """
    Simple representation of an Art-Net DMX packet.
    """
    def __init__(self):
        self.universe = None
        self.data = None
        self.sequence = None
        self.physical = None
        self.length = None

class ArtNetListener:
    """
    A class that listens to Art-Net universes and provides the DMX data.
    Properly handles port sharing with other Art-Net applications.
    
    Note: Art-Net follows the DMX512 standard which operates at a 44Hz refresh rate.
    """
    
    # Art-Net header
    ARTNET_HEADER = b'Art-Net\0'
    
    # Op-codes
    ARTNET_OPDMX = 0x5000
    
    def __init__(self, host='0.0.0.0', port=6454, universes=None):
        """
        Initialize Art-Net listener.
        
        Args:
            host (str): IP address to bind to
            port (int): UDP port to bind to (default: 6454 for Art-Net)
            universes (list): List of universes to listen to
        """
        self.host = host
        self.port = port
        self.universes = sorted(universes) if universes else [0]
        self.running = False
        self.thread = None
        self.socket = None
        self.buffers = {}
        
        # Initialize a buffer for each universe with zeros
        for universe in self.universes:
            self.buffers[universe] = np.zeros(512, dtype=np.uint8)
    
    def _create_socket(self):
        """Create a UDP socket with proper options for port sharing."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # Set socket options to allow address/port reuse
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Try to set SO_REUSEPORT if available (not available on all platforms)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            # SO_REUSEPORT not available on this platform or not supported
            pass
        
        try:
            sock.bind((self.host, self.port))
            print(f"Successfully bound to {self.host}:{self.port}")
            return sock
        except OSError as e:
            print(f"Error binding to {self.host}:{self.port}: {e}")
            print("Will try to continue anyway as Art-Net uses UDP broadcast.")
            # For Art-Net, we can often still receive data even if binding fails
            # because Art-Net typically uses broadcast packets
            return sock
    
    def _listener_thread(self):
        """Thread function that listens for Art-Net packets."""
        while self.running:
            try:
                # Try to receive data (1024 bytes buffer should be enough for Art-Net)
                data, addr = self.socket.recvfrom(1024)
                
                # Process the received packet
                self._process_packet(data)
            except OSError:
                # Socket error or closed
                if self.running:
                    print("Socket error, will retry in 1 second")
                    time.sleep(1)
            except Exception as e:
                print(f"Error processing Art-Net packet: {e}")
    
    def _process_packet(self, data):
        """Process an Art-Net packet."""
        # Check if the packet is long enough and starts with Art-Net header
        if len(data) < 18 or data[:8] != self.ARTNET_HEADER:
            return
        
        # Parse the opcode (Art-Net DMX is 0x5000, stored as little-endian)
        opcode = struct.unpack("<H", data[8:10])[0]
        
        # Check if this is an Art-Net DMX packet
        if opcode != self.ARTNET_OPDMX:
            return
        
        # Parse the rest of the packet
        sequence = data[12]
        physical = data[13]
        universe = struct.unpack("<H", data[14:16])[0]
        length = struct.unpack(">H", data[16:18])[0]  # DMX length is big-endian
        
        # Check if this is a universe we're interested in
        if universe in self.universes:
            # Extract the DMX data
            dmx_data = data[18:18+length]
            
            # Convert to numpy array and update buffer
            self.buffers[universe] = np.frombuffer(dmx_data, dtype=np.uint8)
    
    def start(self):
        """Start listening for Art-Net data."""
        if self.running:
            return
        
        self.socket = self._create_socket()
        self.running = True
        self.thread = threading.Thread(target=self._listener_thread)
        self.thread.daemon = True
        self.thread.start()
        print("Art-Net listener started")
    
    def stop(self):
        """Stop listening for Art-Net data."""
        self.running = False
        if self.thread:
            if self.socket:
                # Close the socket to unblock the recvfrom call
                self.socket.close()
            self.thread.join(timeout=1.0)
            self.thread = None
        print("Art-Net listener stopped")
    
    def get_buffer(self, universe):
        """Get the current DMX buffer for a specific universe."""
        return self.buffers.get(universe, np.zeros(512, dtype=np.uint8))
    
    def get_all_buffers(self):
        """Get all DMX buffers in universe order."""
        return [self.get_buffer(universe) for universe in self.universes]
    
    def is_running(self):
        """Check if the listener is running."""
        return self.running
        
    def set_universes(self, universes):
        """Set the universes to listen to, updating buffers as necessary.
        
        Args:
            universes (list): List of universe IDs to monitor
        """
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