#!/bin/bash
# Setup script for ArtNetViz
# This script ensures all dependencies are installed and everything is ready to run the application.

# Define colors for messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   ArtNetViz Setup                      ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Function to print colored output
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1${NC}"
        exit 1
    fi
}

# Function to detect Mac architecture
detect_mac_architecture() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        ARCH=$(uname -m)
        if [ "$ARCH" = "arm64" ]; then
            echo "apple-silicon"
        elif [ "$ARCH" = "x86_64" ]; then
            echo "intel"
        else
            echo "unknown"
        fi
    else
        echo "not-mac"
    fi
}

# Function to verify Python package installation
verify_package() {
    local pkg=$1
    local import_name=$2
    if [ -z "$import_name" ]; then
        import_name=$pkg
    fi
    
    if python -c "import $import_name" 2>/dev/null; then
        echo -e "${GREEN}✓ $pkg is installed correctly${NC}"
        return 0
    else
        echo -e "${RED}✗ $pkg is not installed correctly${NC}"
        return 1
    fi
}

# Check if we're in the right directory
if [ ! -f "setup.sh" ]; then
    echo -e "${RED}Please run this script from the project root directory${NC}"
    exit 1
fi

# Check if Python is installed
echo -e "${YELLOW}Checking for Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is required but not found.${NC}"
    echo -e "${RED}Please install Python 3 and try again.${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d ' ' -f 2)
echo -e "${GREEN}Python $PYTHON_VERSION found.${NC}"

# Check if pip is installed
echo -e "${YELLOW}Checking for pip...${NC}"
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}pip3 is required but not found.${NC}"
    echo -e "${RED}Please install pip3 and try again.${NC}"
    exit 1
fi
PIP_VERSION=$(pip3 --version | cut -d ' ' -f 2)
echo -e "${GREEN}pip $PIP_VERSION found.${NC}"

# Check for Git
echo -e "${YELLOW}Checking for Git...${NC}"
if ! command -v git &> /dev/null; then
    echo -e "${RED}Git is required but not found.${NC}"
    echo -e "${RED}Please install Git and try again.${NC}"
    exit 1
fi
GIT_VERSION=$(git --version | cut -d ' ' -f 3)
echo -e "${GREEN}Git $GIT_VERSION found.${NC}"

# Check for system dependencies on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}Checking for macOS system dependencies...${NC}"
    
    # Detect Mac architecture
    MAC_ARCH=$(detect_mac_architecture)
    echo -e "${GREEN}Detected Mac architecture: $MAC_ARCH${NC}"
    
    # Check macOS version (Syphon-python requires macOS 10.9 or above)
    MACOS_VERSION=$(sw_vers -productVersion)
    if [[ "$(printf '%s\n' "10.9" "$MACOS_VERSION" | sort -V | head -n1)" != "10.9" ]]; then
        echo -e "${RED}Syphon-python requires macOS 10.9 or above.${NC}"
        echo -e "${RED}Current macOS version: $MACOS_VERSION${NC}"
        exit 1
    fi
    
    # Check for Xcode Command Line Tools
    if ! command -v xcode-select &> /dev/null; then
        echo -e "${RED}Xcode Command Line Tools are required but not found.${NC}"
        echo -e "${YELLOW}Installing Xcode Command Line Tools...${NC}"
        xcode-select --install
        print_status "Xcode Command Line Tools installed"
    fi
    
    # Check for Metal framework
    if [ ! -d "/System/Library/Frameworks/Metal.framework" ]; then
        echo -e "${RED}Metal framework is required but not found.${NC}"
        echo -e "${RED}Please ensure you're running macOS 10.9 or later.${NC}"
        exit 1
    fi
    
    # Check for OpenGL framework (needed for Intel Macs)
    if [ "$MAC_ARCH" = "intel" ]; then
        if [ ! -d "/System/Library/Frameworks/OpenGL.framework" ]; then
            echo -e "${RED}OpenGL framework is required for Intel Macs but not found.${NC}"
            echo -e "${RED}Please ensure you're running macOS 10.9 or later.${NC}"
            exit 1
        fi
    fi
fi

# Clean any existing virtual environment
echo -e "${YELLOW}Checking for existing virtual environment...${NC}"
if [ -d "venv" ]; then
    echo -e "${YELLOW}Existing virtual environment found. Do you want to recreate it? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}Removing existing virtual environment...${NC}"
        rm -rf venv
        echo -e "${GREEN}Existing virtual environment removed.${NC}"
    else
        echo -e "${YELLOW}Using existing virtual environment.${NC}"
    fi
fi

# Create a virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
    if [ ! -d "venv" ]; then
        echo -e "${RED}Failed to create virtual environment.${NC}"
        echo -e "${RED}Please check your Python installation.${NC}"
        exit 1
    fi
    echo -e "${GREEN}Virtual environment created successfully.${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source venv/bin/activate
echo -e "${GREEN}Virtual environment activated.${NC}"

# Upgrade pip, setuptools, and wheel
echo -e "${YELLOW}Upgrading pip, setuptools, and wheel...${NC}"
pip install --upgrade pip setuptools wheel
echo -e "${GREEN}Upgraded pip, setuptools, and wheel.${NC}"

# Create a fresh requirements file for consistent dependency management
echo -e "${YELLOW}Creating requirements file...${NC}"
cat > requirements.txt << EOF
PyQt6>=6.4.0
numpy>=1.23.0
PyYAML>=6.0
pyobjc>=10.0,<11.0  # Ensure compatible version for syphon-python
pyopengl>=3.1.7
psutil>=5.9.0  # For memory monitoring
opencv-python>=4.8.0  # Required for Syphon examples
EOF
echo -e "${GREEN}Requirements file created.${NC}"

# Install requirements
echo -e "${YELLOW}Installing required dependencies from requirements file...${NC}"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}Failed to install dependencies.${NC}"
    echo -e "${YELLOW}Trying alternative installation method...${NC}"
    
    # Try installing packages one by one
    pip install PyQt6>=6.4.0
    pip install numpy>=1.23.0
    pip install PyYAML>=6.0
    pip install "pyobjc>=10.0,<11.0"
    pip install pyopengl>=3.1.7
    pip install psutil>=5.9.0
    pip install opencv-python>=4.8.0
fi

# Install syphon-python
echo -e "${YELLOW}Installing syphon-python...${NC}"

# First try installing from PyPI
echo -e "${YELLOW}Attempting to install syphon-python from PyPI...${NC}"
pip install syphon-python
if [ $? -eq 0 ]; then
    echo -e "${GREEN}syphon-python installed successfully from PyPI.${NC}"
else
    echo -e "${YELLOW}PyPI installation failed, building from source...${NC}"
    
    # Clone the repository if it doesn't exist
    if [ ! -d "syphon-python" ]; then
        echo -e "${YELLOW}Cloning syphon-python repository...${NC}"
        git clone https://github.com/cansik/syphon-python.git
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to clone syphon-python repository.${NC}"
            echo -e "${YELLOW}Please check your internet connection and try again.${NC}"
            deactivate
            exit 1
        fi
    fi

    # Navigate to the syphon-python directory
    cd syphon-python

    # Build the wheel
    echo -e "${YELLOW}Building syphon-python wheel...${NC}"
    pip install build
    python -m build --wheel
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to build syphon-python wheel.${NC}"
        echo -e "${YELLOW}Please check the build logs for more information.${NC}"
        cd ..
        deactivate
        exit 1
    fi

    # Find and install the wheel
    echo -e "${YELLOW}Installing syphon-python wheel...${NC}"
    WHEEL_FILE=$(ls dist/syphon_python-0.1.1-*.whl)
    if [ -z "$WHEEL_FILE" ]; then
        echo -e "${RED}No wheel file found in dist directory.${NC}"
        cd ..
        deactivate
        exit 1
    fi

    # Copy wheel to project root for future use
    cp "$WHEEL_FILE" ../syphon_python_wheel.whl
    echo -e "${YELLOW}Wheel file saved as syphon_python_wheel.whl for future use${NC}"

    # Install the wheel
    pip install "$WHEEL_FILE"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to install syphon-python wheel.${NC}"
        echo -e "${YELLOW}Please check the installation logs for more information.${NC}"
        cd ..
        deactivate
        exit 1
    fi

    # Return to the project root
    cd ..
    echo -e "${GREEN}syphon-python built and installed successfully from wheel.${NC}"
    echo -e "${YELLOW}Note: If you encounter memory issues, you can try reinstalling the wheel:${NC}"
    echo -e "${YELLOW}source venv/bin/activate && pip install syphon_python_wheel.whl && deactivate${NC}"
fi

# Make sure resources directories exist
echo -e "${YELLOW}Checking resources directories...${NC}"
mkdir -p resources/icons
echo -e "${GREEN}Resources directories created/verified.${NC}"

# Verify all dependencies
echo -e "${YELLOW}Verifying dependencies...${NC}"
DEPS_OK=true

# Check each required dependency with proper import names
verify_package "PyQt6" "PyQt6" || DEPS_OK=false
verify_package "numpy" "numpy" || DEPS_OK=false
verify_package "PyYAML" "yaml" || DEPS_OK=false
verify_package "syphon-python" "syphon" || DEPS_OK=false
verify_package "psutil" "psutil" || DEPS_OK=false
verify_package "pyobjc" "objc" || DEPS_OK=false
verify_package "opencv-python" "cv2" || DEPS_OK=false

# Check tracemalloc (built-in module)
if python -c "import tracemalloc" 2>/dev/null; then
    echo -e "${GREEN}✓ tracemalloc is available (built-in module)${NC}"
else
    echo -e "${RED}✗ tracemalloc is not available${NC}"
    DEPS_OK=false
fi

if [ "$DEPS_OK" = true ]; then
    echo -e "${GREEN}All dependencies are installed and verified.${NC}"
else
    echo -e "${RED}Some dependencies are missing or not installed correctly.${NC}"
    echo -e "${RED}Please check the error messages above.${NC}"
    deactivate
    exit 1
fi

# Fix dependency conflicts
echo -e "${YELLOW}Checking for dependency conflicts...${NC}"
pip check
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Dependency conflicts detected. Attempting to fix...${NC}"
    echo -e "${YELLOW}This might take a few minutes and may require manual intervention later.${NC}"
    
    # This is a simplified attempt to fix conflicts - in complex cases, manual intervention might be needed
    echo -e "${YELLOW}Running pip install to resolve dependencies...${NC}"
    pip install -r requirements.txt --upgrade
else
    echo -e "${GREEN}No dependency conflicts detected.${NC}"
fi

# Deactivate virtual environment
deactivate

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}Setup completed successfully!${NC}"
echo -e "${GREEN}You can now run the application with:${NC}"
echo -e "${YELLOW}./run.sh${NC}"
echo -e "${GREEN}or${NC}"
echo -e "${YELLOW}npm run run${NC}"
echo -e "${BLUE}=========================================${NC}"

# Note for dependency conflicts
echo -e "${YELLOW}Note: If you encounter any dependency conflicts when running the application,${NC}"
echo -e "${YELLOW}you may need to modify the requirements.txt file and rerun this setup script.${NC}"
echo -e "${YELLOW}Alternatively, you can try running:${NC}"
echo -e "${YELLOW}source venv/bin/activate && pip install <specific-package-version> && deactivate${NC}"

# Additional notes for Intel Mac users
if [[ "$OSTYPE" == "darwin"* ]] && [ "$MAC_ARCH" = "intel" ]; then
    echo -e "${YELLOW}Note for Intel Mac users:${NC}"
    echo -e "${YELLOW}1. The application uses OpenGL for rendering on Intel Macs${NC}"
    echo -e "${YELLOW}2. Performance may vary depending on your graphics card${NC}"
    echo -e "${YELLOW}3. If you experience any graphics issues, try updating your graphics drivers${NC}"
fi 