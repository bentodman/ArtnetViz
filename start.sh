#!/bin/bash

# Check if we're running from the standalone app bundle
if [[ "$BASH_SOURCE" == *"ArtNetViz.app"* ]]; then
    # Running from the app bundle
    APP_DIR=$(dirname "$BASH_SOURCE")
    
    echo "Starting Art-Net Visualizer..."
    echo "Note: If you see 'Address already in use' errors, this is normal when other Art-Net applications are running."
    echo "The visualizer will still work as it shares the UDP port with other applications."
    echo ""
    
    # Run the bundled Python executable
    "$APP_DIR/Contents/MacOS/ArtNetViz"
else
    # Running in development mode
    # Check if virtual environment exists
    if [ -d "venv" ]; then
        # Activate virtual environment
        source venv/bin/activate
        
        echo "Starting Art-Net Visualizer..."
        echo "Note: If you see 'Address already in use' errors, this is normal when other Art-Net applications are running."
        echo "The visualizer will still work as it shares the UDP port with other applications."
        echo ""
        
        python src/main.py
        
        # Deactivate virtual environment
        deactivate
    else
        echo "Virtual environment not found. Please set up the environment first:"
        echo "python3 -m venv venv"
        echo "source venv/bin/activate"
        echo "pip install -r requirements.txt"
        exit 1
    fi
fi 