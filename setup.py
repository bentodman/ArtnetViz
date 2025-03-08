"""
Setup script for building a standalone macOS application using py2app.
This will create a portable .app bundle that includes all dependencies.
"""

from setuptools import setup
import os
import shutil
import sys

# Clean any previous build artifacts
if os.path.exists('build'):
    print("Cleaning previous build directory...")
    shutil.rmtree('build')
if os.path.exists('dist'):
    print("Cleaning previous dist directory...")
    shutil.rmtree('dist')

APP = ['src/main.py']
DATA_FILES = [
    'config.yaml',  # Include default configuration
    'start.sh',     # Include start script
    'README.md'     # Include documentation
]

OPTIONS = {
    'argv_emulation': False,
    'packages': ['PyQt6', 'numpy', 'yaml', 'syphon'],
    # Only include the icon file if it exists
    'iconfile': 'app_icon.icns' if os.path.exists('app_icon.icns') else None,
    'plist': {
        'CFBundleName': 'ArtNetViz',
        'CFBundleDisplayName': 'Art-Net Visualizer',
        'CFBundleIdentifier': 'com.artnetviz',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHumanReadableCopyright': 'MIT License',
        'NSHighResolutionCapable': True,
    },
    'includes': ['syphon.utils.numpy', 'syphon.utils.raw'],
    # Handle duplicates and exclude problematic packages
    'excludes': ['setuptools', 'pkg_resources', 'pip'],
    # Don't include dist-info directories to avoid conflicts
    'strip': True,  
    # Use semi-standalone mode to resolve some conflicts
    'semi_standalone': False,
    # Don't copy python libraries
    'use_pythonpath': False,
    # Tell py2app to not get confused by setuptools' vendored packages
    'recipe_append': {
        'setuptools': ['_vendor', 'extern'],
    }
}

setup(
    name='ArtNetViz',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
) 