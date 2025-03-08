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

# Check for config file
if [ ! -f "config.yaml" ]; then
    echo -e "${RED}Config file (config.yaml) not found.${NC}"
    echo -e "${YELLOW}Creating a default config file...${NC}"
    
    cat > config.yaml << EOF
# Art-Net Configuration
artnet:
  # IP address to bind to (0.0.0.0 for all interfaces)
  host: "0.0.0.0"
  # Port (standard Art-Net port is 6454)
  port: 6454
  # List of universes to listen to
  universes:
    - 0  # Universe 0
    - 1  # Universe 1

# Test Source Configuration
test_source:
  # Enable test source instead of Art-Net listener
  enabled: true
  # Pattern type to generate
  pattern: "MOVING_BAR_H"
  # Animation speed multiplier
  speed: 1.0

# Visualization Configuration
visualization:
  # Size of each pixel (width and height in screen pixels)
  pixel_size: 2
  # Horizontal gap between pixels (in screen pixels)
  gap_x: 0
  # Vertical gap between pixels (in screen pixels)
  gap_y: 1
  # Overall canvas width (0 = auto-size based on content)
  canvas_width: 0
  # Overall canvas height (0 = auto-size based on content)
  canvas_height: 0
  # X position of visualization from top-left of canvas
  start_x: 0
  # Y position of visualization from top-left of canvas
  start_y: 0
EOF
    
    echo -e "${GREEN}Default config file created.${NC}"
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
    echo -e "${YELLOW}4. Try enabling the test mode in config.yaml (set test_source.enabled to true)${NC}"
else
    echo -e "${GREEN}Application exited successfully.${NC}"
fi

exit $EXIT_CODE 