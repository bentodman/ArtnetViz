#!/bin/bash
# Simple script to run ArtNetViz directly without building a standalone app

# Define colors for messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   ArtNetViz Runner                     ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python 3 is required but not found. Please install Python 3 and try again.${NC}"
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo -e "${RED}pip3 is required but not found. Please install pip3 and try again.${NC}"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${RED}Virtual environment not found. Please run the setup script first:${NC}"
    echo -e "${YELLOW}./setup.sh${NC}"
    echo -e "${YELLOW}or${NC}"
    echo -e "${YELLOW}npm run setup${NC}"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Quick dependency check
echo -e "${YELLOW}Checking dependencies...${NC}"
MISSING_DEPS=false

check_dependency() {
    if ! python -c "import $1" 2>/dev/null; then
        echo -e "${RED}Package '$1' is not installed correctly.${NC}"
        MISSING_DEPS=true
    fi
}

# Check required dependencies
check_dependency PyQt6
check_dependency numpy
check_dependency yaml
check_dependency syphon
check_dependency objc

if [ "$MISSING_DEPS" = true ]; then
    echo -e "${RED}Some dependencies are missing. Please run the setup script to install them:${NC}"
    echo -e "${YELLOW}./setup.sh${NC}"
    echo -e "${YELLOW}or${NC}"
    echo -e "${YELLOW}npm run setup${NC}"
    deactivate
    exit 1
fi

# Print informational message
echo -e "${GREEN}Starting Art-Net Visualizer...${NC}"
echo -e "${YELLOW}Note: If you see 'Address already in use' errors, this is normal when other Art-Net applications are running.${NC}"
echo -e "${YELLOW}The visualizer will still work as it shares the UDP port with other applications.${NC}"
echo ""

# Run the application
python src/main.py

# Capture exit code
EXIT_CODE=$?

# Deactivate virtual environment
deactivate

# Handle exit code
if [ $EXIT_CODE -ne 0 ]; then
    echo -e "${RED}Application exited with error code: $EXIT_CODE${NC}"
    echo -e "${YELLOW}Check the error messages above for more information.${NC}"
    
    # Provide additional troubleshooting tips
    echo -e "${YELLOW}Troubleshooting tips:${NC}"
    echo -e "${YELLOW}1. Run the setup script again: ./setup.sh${NC}"
    echo -e "${YELLOW}2. Check for dependency conflicts: source venv/bin/activate && pip check${NC}"
    echo -e "${YELLOW}3. Make sure all required hardware is connected${NC}"
    echo -e "${YELLOW}4. Configure Art-Net parameters through the application UI${NC}"
    echo -e "${YELLOW}   - Universe selection directly in the main window${NC}"
    echo -e "${YELLOW}   - Network settings via Settings > Settings menu${NC}"
else
    echo -e "${GREEN}Application exited successfully.${NC}"
fi

exit $EXIT_CODE 