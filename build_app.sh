#!/bin/bash
# Script to build a standalone macOS application for Art-Net Visualizer

echo "Building Art-Net Visualizer standalone application..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not found. Please install Python 3 and try again."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is required but not found. Please install pip3 and try again."
    exit 1
fi

# Ensure we have a clean environment
echo "Cleaning previous builds..."
rm -rf build dist
rm -rf venv_build

# Create a virtual environment for the build
echo "Creating a virtual environment for the build..."
python3 -m venv venv_build
source venv_build/bin/activate

# Install required dependencies
echo "Installing required dependencies..."
pip install --upgrade pip setuptools wheel
pip install PyQt6 numpy pyobjc pyyaml

# Install py2app from GitHub for latest fixes
echo "Installing py2app from GitHub..."
pip install git+https://github.com/ronaldoussoren/py2app.git

# Install syphon-python from source
echo "Installing syphon-python..."
pip install git+https://github.com/cansik/syphon-python.git

# Verify all dependencies are installed
echo "Verifying installations..."
python -c "import PyQt6; import numpy; import yaml; import syphon; print('All dependencies verified.')"

# Build the application using py2app with alias mode first for testing
echo "Building the application in alias mode for testing..."
python setup.py py2app -A

# Test the alias build
if [ -e "dist/ArtNetViz.app" ]; then
    echo "Alias build successful! Testing the app..."
    # You can add a test run here if needed
else
    echo "Alias build failed. Please check the error messages above."
    exit 1
fi

# If alias mode works, build the actual standalone app
echo "Building the standalone application..."
rm -rf build dist
python setup.py py2app

# Check if build was successful
if [ -e "dist/ArtNetViz.app" ]; then
    echo "Build successful! The application is available at: dist/ArtNetViz.app"
    echo "You can now distribute this .app bundle to other macOS users."
else
    echo "Build failed. Please check the error messages above."
    exit 1
fi

# Try an alternative build if the main one failed
if [ ! -e "dist/ArtNetViz.app" ]; then
    echo "Trying alternative build method..."
    rm -rf build dist
    
    # Try with different options
    python setup.py py2app --no-strip --no-recipes
    
    if [ -e "dist/ArtNetViz.app" ]; then
        echo "Alternative build successful! The application is available at: dist/ArtNetViz.app"
    else
        echo "All build attempts failed. Please check the error messages above."
        exit 1
    fi
fi

# Deactivate the virtual environment
deactivate

# Remove the build virtual environment
echo "Cleaning up build environment..."
rm -rf venv_build

# Create a ZIP archive for easy distribution
echo "Creating distribution ZIP file..."
cd dist
zip -r ArtNetViz.zip ArtNetViz.app
cd ..

echo "Done! Your portable application is ready in dist/ArtNetViz.app"
echo "A ZIP archive for distribution is available at dist/ArtNetViz.zip" 