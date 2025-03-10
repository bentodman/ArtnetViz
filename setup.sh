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
EOF
echo -e "${GREEN}Requirements file created.${NC}"

# Install requirements
echo -e "${YELLOW}Installing required dependencies from requirements file...${NC}"
pip install -r requirements.txt
echo -e "${GREEN}Dependencies installed.${NC}"

# Install syphon-python from source
echo -e "${YELLOW}Installing syphon-python from source...${NC}"

# Uninstall syphon first if it exists to avoid conflicts
if python -c "import syphon" 2>/dev/null; then
    echo -e "${YELLOW}Found existing syphon-python installation. Removing to avoid conflicts...${NC}"
    pip uninstall -y syphon-python
    echo -e "${GREEN}Existing syphon-python removed.${NC}"
fi

# Check if syphon-python repo exists
if [ ! -d "syphon-python" ]; then
    echo -e "${YELLOW}Cloning syphon-python repository...${NC}"
    git clone https://github.com/cansik/syphon-python.git
    echo -e "${GREEN}syphon-python repository cloned.${NC}"
else
    echo -e "${YELLOW}Updating syphon-python repository...${NC}"
    cd syphon-python
    git pull
    cd ..
    echo -e "${GREEN}syphon-python repository updated.${NC}"
fi

# Install syphon-python in development mode
echo -e "${YELLOW}Installing syphon-python in development mode...${NC}"
pip install -e syphon-python --no-deps  # Install without dependencies to avoid conflicts
echo -e "${GREEN}syphon-python installed.${NC}"

# List outdated packages
echo -e "${YELLOW}Checking for outdated packages...${NC}"
outdated_packages=$(pip list --outdated --format=freeze | cut -d= -f1)
if [ -n "$outdated_packages" ]; then
    echo -e "${YELLOW}The following packages are outdated:${NC}"
    pip list --outdated
    
    # Ask if user wants to update outdated packages
    echo -e "${YELLOW}Do you want to update outdated packages? (y/n)${NC}"
    read -r update_response
    if [[ "$update_response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo -e "${YELLOW}Updating outdated packages...${NC}"
        pip list --outdated --format=freeze | grep -v '^\-e' | cut -d = -f 1 | xargs -n1 pip install -U
        echo -e "${GREEN}Packages updated.${NC}"
    else
        echo -e "${YELLOW}Skipping package updates.${NC}"
    fi
else
    echo -e "${GREEN}All packages are up to date.${NC}"
fi

# Make sure resources directories exist
echo -e "${YELLOW}Checking resources directories...${NC}"
mkdir -p resources/icons
echo -e "${GREEN}Resources directories created/verified.${NC}"

# Verify all dependencies
echo -e "${YELLOW}Verifying dependencies...${NC}"
DEPS_OK=true

# Check each required dependency
for pkg in PyQt6 numpy yaml syphon; do
    if ! python -c "import $pkg" 2>/dev/null; then
        echo -e "${RED}Package '$pkg' is not installed correctly.${NC}"
        DEPS_OK=false
    fi
done

# Check if pyobjc is installed (imported as 'objc')
if ! python -c "import objc" 2>/dev/null; then
    echo -e "${RED}Package 'pyobjc' is not installed correctly.${NC}"
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
    pip install -e syphon-python --no-deps  # Reinstall syphon without deps
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

# Function to print colored output
print_status() {
    if [ $? -eq 0 ]; then
        echo -e "\033[32m✓ $1\033[0m"  # Green
    else
        echo -e "\033[31m✗ $1\033[0m"  # Red
        exit 1
    fi
}

# Check if we're in the right directory
if [ ! -f "setup.sh" ]; then
    echo "Please run this script from the project root directory"
    exit 1
fi

echo "Setting up ArtNet Visualizer..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    print_status "Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
print_status "Virtual environment activated"

# Install/upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip
print_status "Pip upgraded"

# Install requirements
echo "Installing requirements..."
pip install -r requirements.txt
print_status "Requirements installed"

# Install syphon-python
echo "Installing syphon-python..."

# Check if we have a pre-built wheel
if [ -d "dist" ] && [ "$(ls -A dist/*.whl 2>/dev/null)" ]; then
    echo "Found pre-built wheel, installing..."
    pip install dist/*.whl
    print_status "syphon-python installed from wheel"
else
    # No wheel available, try to build from source
    echo "No pre-built wheel found, attempting to build from source..."
    
    # Check if we have Xcode Command Line Tools
    if ! xcode-select -p &>/dev/null; then
        echo -e "\033[31mError: Xcode Command Line Tools not found\033[0m"
        echo "To install Xcode Command Line Tools, run: xcode-select --install"
        echo "Or download a pre-built version of this application."
        exit 1
    fi
    
    # Initialize Syphon submodules if needed
    if [ ! -d "syphon-python/vendor/Syphon/Syphon.xcodeproj" ]; then
        echo "Initializing Syphon submodules..."
        (cd syphon-python && git submodule init && git submodule update)
        print_status "Syphon submodules initialized"
    fi
    
    # Install from source
    pip install -e syphon-python
    print_status "syphon-python installed from source"
fi

# Check for outdated packages
echo "Checking for outdated packages..."
pip list --outdated
print_status "Package check completed"

# Create resources directories if they don't exist
echo "Checking resources directories..."
mkdir -p resources/icons
print_status "Resources directories created/verified"

# Verify dependencies
echo "Verifying dependencies..."
python -c "import syphon" 2>/dev/null
if [ $? -eq 0 ]; then
    print_status "Package 'syphon' is installed correctly"
else
    echo -e "\033[31m✗ Package 'syphon' is not installed correctly\033[0m"
    echo "Some dependencies are missing or not installed correctly."
    echo "Please check the error messages above."
    exit 1
fi

echo -e "\033[32m✓ Setup completed successfully\033[0m" 