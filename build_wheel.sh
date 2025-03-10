#!/bin/bash

# Function to print colored output
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "\033[32m✓ $1\033[0m"  # Green
    else
        echo -e "\033[31m✗ $1\033[0m"  # Red
        exit 1
    fi
}

echo "Building Syphon wheel..."

# Make sure we're in the right directory
if [ ! -d "syphon-python" ]; then
    echo "Please run this script from the project root directory"
    exit 1
fi

# Create a build environment
python3 -m venv build_venv
source build_venv/bin/activate

# Install build requirements
pip install --upgrade pip wheel setuptools build

# Initialize submodules if needed
cd syphon-python
if [ ! -d "vendor/Syphon/Syphon.xcodeproj" ]; then
    git submodule init
    git submodule update
fi

# Build the wheel
python -m build --wheel
print_status "Wheel built"

# Copy the wheel to the dist directory in the project root
mkdir -p ../dist
cp dist/*.whl ../dist/
print_status "Wheel copied to dist directory"

# Clean up
cd ..
deactivate
rm -rf build_venv
print_status "Build environment cleaned up"

echo "Wheel has been built and placed in the dist directory" 