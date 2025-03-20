def cleanup_template(self):
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
        
        # Clean up caches
        print("Cleaning up caches...")
        if hasattr(self, '_color_cache'):
            self._color_cache.clear()
        if hasattr(self, '_coordinate_cache'):
            self._coordinate_cache.clear()
            
        # Force garbage collection
        print("Forcing final garbage collection...")
        gc.collect(2)  # Full collection
        
        # Print memory usage
        mem_usage = self._get_memory_usage_mb()
        print(f"Final memory usage: {mem_usage:.2f} MB")
        
        # Final cleanup message
        print("Cleanup completed")
    except Exception as e:
        print(f"Error during cleanup: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always release the pool
        del pool
