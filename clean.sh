#!/bin/bash
# Script to clean up build artifacts and temporary files

# Define colors for messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}   ArtNetViz Cleanup                    ${NC}"
echo -e "${BLUE}=========================================${NC}"

# Display options
echo -e "${YELLOW}Cleanup options:${NC}"
echo -e "${YELLOW}1. Basic cleanup (remove build artifacts and caches)${NC}"
echo -e "${YELLOW}2. Deep cleanup (remove all temporary files and virtual environment)${NC}"
echo -e "${YELLOW}3. Fix dependencies (repair virtual environment without deleting it)${NC}"
echo -e "${YELLOW}4. Exit${NC}"
echo -e "${YELLOW}Enter your choice [1-4]:${NC}"
read -r choice

case $choice in
    1)
        echo -e "${YELLOW}Performing basic cleanup...${NC}"
        
        # Remove build directories
        echo -e "${YELLOW}Removing build directories...${NC}"
        rm -rf build/ dist/ build_*/ dist_*/ venv_build/
        
        # Remove Python cache files
        echo -e "${YELLOW}Removing Python cache files...${NC}"
        find . -name "*.pyc" -delete
        find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
        find . -name "*.egg-info" -exec rm -rf {} + 2>/dev/null
        find . -name "*.egg" -delete
        find . -name "*.so" -delete
        
        # Remove other temporary files
        echo -e "${YELLOW}Removing temporary files...${NC}"
        rm -rf .DS_Store
        find . -name ".DS_Store" -delete
        
        echo -e "${GREEN}Basic cleanup complete!${NC}"
        ;;
        
    2)
        echo -e "${YELLOW}Performing deep cleanup...${NC}"
        
        # Remove build directories
        echo -e "${YELLOW}Removing build directories...${NC}"
        rm -rf build/ dist/ build_*/ dist_*/ venv_build/
        
        # Remove Python cache files
        echo -e "${YELLOW}Removing Python cache files...${NC}"
        find . -name "*.pyc" -delete
        find . -name "__pycache__" -exec rm -rf {} + 2>/dev/null
        find . -name "*.egg-info" -exec rm -rf {} + 2>/dev/null
        find . -name "*.egg" -delete
        find . -name "*.so" -delete
        
        # Remove other temporary files
        echo -e "${YELLOW}Removing temporary files...${NC}"
        rm -rf .DS_Store
        find . -name ".DS_Store" -delete
        
        # Remove virtual environment
        if [ -d "venv" ]; then
            echo -e "${YELLOW}Removing virtual environment...${NC}"
            rm -rf venv
            echo -e "${GREEN}Virtual environment removed.${NC}"
        fi
        
        echo -e "${GREEN}Deep cleanup complete!${NC}"
        echo -e "${YELLOW}Remember to run setup.sh to recreate the virtual environment.${NC}"
        ;;
        
    3)
        echo -e "${YELLOW}Fixing dependencies...${NC}"
        
        if [ ! -d "venv" ]; then
            echo -e "${RED}Virtual environment not found. Running setup script...${NC}"
            ./setup.sh
            exit 0
        fi
        
        # Activate virtual environment
        source venv/bin/activate
        
        # Upgrade pip, setuptools, wheel
        echo -e "${YELLOW}Upgrading pip, setuptools, and wheel...${NC}"
        pip install --upgrade pip setuptools wheel
        
        # Create optimized requirements
        echo -e "${YELLOW}Creating optimized requirements file...${NC}"
        cat > requirements.txt << EOF
PyQt6>=6.4.0
numpy>=1.23.0
PyYAML>=6.0
pyobjc>=10.0,<11.0  # Ensure compatible version for syphon-python
pyopengl>=3.1.7
EOF
        
        # Reinstall requirements
        echo -e "${YELLOW}Reinstalling requirements...${NC}"
        pip install -r requirements.txt --upgrade
        
        # Fix syphon-python
        if [ -d "syphon-python" ]; then
            echo -e "${YELLOW}Reinstalling syphon-python...${NC}"
            pip uninstall -y syphon-python
            pip install -e syphon-python --no-deps
        else
            echo -e "${RED}syphon-python directory not found.${NC}"
            echo -e "${RED}Please run setup.sh to properly set up the environment.${NC}"
            deactivate
            exit 1
        fi
        
        # Check for dependency conflicts
        echo -e "${YELLOW}Checking for dependency conflicts...${NC}"
        pip check
        if [ $? -ne 0 ]; then
            echo -e "${RED}Dependency conflicts still exist.${NC}"
            echo -e "${RED}You may need to run deep cleanup and setup again.${NC}"
        else
            echo -e "${GREEN}No dependency conflicts detected!${NC}"
        fi
        
        # Deactivate virtual environment
        deactivate
        
        echo -e "${GREEN}Dependency fixing complete!${NC}"
        ;;
        
    4)
        echo -e "${YELLOW}Exiting without cleanup.${NC}"
        exit 0
        ;;
        
    *)
        echo -e "${RED}Invalid choice. Exiting.${NC}"
        exit 1
        ;;
esac

echo -e "${BLUE}=========================================${NC}"
echo -e "${GREEN}You can run the setup script again with:${NC}"
echo -e "${YELLOW}./setup.sh${NC}"
echo -e "${GREEN}or${NC}"
echo -e "${YELLOW}npm run setup${NC}"
echo -e "${BLUE}=========================================${NC}" 