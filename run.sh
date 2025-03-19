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

# Install memory monitoring tools if needed
if [ "$1" == "--monitor" ]; then
    echo -e "${YELLOW}Installing memory monitoring tools...${NC}"
    pip install psutil
fi

# Print informational message
echo -e "${GREEN}Starting Art-Net Visualizer...${NC}"
echo -e "${YELLOW}Note: If you see 'Address already in use' errors, this is normal when other Art-Net applications are running.${NC}"
echo -e "${YELLOW}The visualizer will still work as it shares the UDP port with other applications.${NC}"
echo ""

# Run the application based on mode
if [ "$1" == "--monitor" ]; then
    echo -e "${YELLOW}Running with memory monitoring in background...${NC}"
    
    # Create a temp script for monitoring
    cat > monitor_memory.py << 'EOF'
import psutil
import time
import os
import sys
import datetime

pid = int(sys.argv[1])
log_file = sys.argv[2]
interval = 1.0  # seconds

with open(log_file, 'w') as f:
    f.write("Timestamp,Memory (MB)\n")
    
    while True:
        try:
            process = psutil.Process(pid)
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            
            print(f"{timestamp}: Memory usage: {memory_mb:.2f} MB")
            f.write(f"{timestamp},{memory_mb:.2f}\n")
            f.flush()
            
            time.sleep(interval)
        except psutil.NoSuchProcess:
            print("Application has terminated.")
            break
        except KeyboardInterrupt:
            print("Monitoring stopped.")
            break
EOF
    
    # Run the app normally
    python src/main.py &
    APP_PID=$!
    
    # Run the monitor in background
    LOG_FILE="memory_usage_$(date +%Y%m%d_%H%M%S).csv"
    python monitor_memory.py $APP_PID $LOG_FILE &
    MONITOR_PID=$!
    
    # Wait for the app to finish
    wait $APP_PID
    EXIT_CODE=$?
    
    # Kill the monitor
    kill $MONITOR_PID 2>/dev/null
    
    echo -e "${GREEN}Memory usage log saved to: ${LOG_FILE}${NC}"
    
elif [ "$1" == "--debug-script" ]; then
    # Create a modified main.py with extra debugging
    TEMP_FILE=$(mktemp)
    
    cat > $TEMP_FILE << 'EOF'
import gc
import sys
import tracemalloc
import os
import signal
import time

# Enable GC debugging and memory tracking
gc.set_debug(gc.DEBUG_LEAK)
tracemalloc.start(25)

# Import the actual application
sys.path.insert(0, os.path.abspath('.'))
from src import main

# Add signal handler for memory snapshots
def signal_handler(sig, frame):
    print("\n=== Memory Usage Snapshot ===")
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    for stat in top_stats[:20]:
        print(stat)
    print("===========================\n")

signal.signal(signal.SIGUSR1, signal_handler)

print(f"Memory debugging enabled. Send SIGUSR1 to PID {os.getpid()} for a snapshot")
print(f"Example: kill -SIGUSR1 {os.getpid()}")

# Run the original main function
if hasattr(main, 'main'):
    main.main()
elif hasattr(main, '__main__'):
    # Already executed via import
    pass
else:
    print("Warning: Could not find main entry point")
EOF
    
    # Execute the temporary script
    python $TEMP_FILE
    EXIT_CODE=$?
    
    # Clean up
    rm $TEMP_FILE
else
    # Run the application normally
    python src/main.py
    EXIT_CODE=$?
fi

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
    echo -e "${YELLOW}5. Run with memory monitoring: ./run.sh --monitor${NC}"
    echo -e "${YELLOW}6. Run with debug hooks: ./run.sh --debug-script${NC}"
else
    echo -e "${GREEN}Application exited successfully.${NC}"
fi

exit $EXIT_CODE 