# Art-Net Visualizer with Syphon

A PyQt6 application that listens to Art-Net DMX data, visualizes it as pixels on a canvas, and exposes the canvas as a Syphon source on macOS. This allows other applications to receive the visualization in real-time.

## Features

- Listens to multiple Art-Net universes configurable directly in the UI
- Visualizes each DMX channel as a pixel (value 0-255 mapped from black to white)
- Each universe occupies one row of 512 pixels (one pixel per DMX channel)
- Configurable pixel size and spacing for better visibility
- Configurable canvas size and visualization position
- Real-time exposure of the visualization as a Syphon source at 44Hz (standard DMX512 refresh rate)
- Properly handles port sharing with other Art-Net applications
- Built-in test pattern generator with various patterns for testing without an external Art-Net source
- All settings configurable through an intuitive user interface
- Persistent window size and position between sessions

## Requirements

- macOS (required for Syphon)
- Python 3.9 or newer
- Git (for dependency installation)

## Installation

### Quick Start

1. Clone this repository:
   ```
   git clone https://github.com/bentodman/ArtnetViz.git
   cd ArtnetViz
   ```

2. Run the setup script:
   ```
   ./setup.sh
   ```
   
   This will:
   - Create a virtual environment
   - Install all required dependencies
   - Set up the necessary directories
   - Verify the installation

3. Run the application:
   ```
   ./run.sh
   ```

### Alternative Setup with npm

If you have npm installed, you can also use:

```
npm run setup   # Set up the environment
npm run run     # Run the application
```

## User Interface

The application features an intuitive user interface with the following components:

### Main Window

The main window consists of:

1. **Canvas Area**: The top portion displays the DMX data visualization with each universe as a row of pixels, each pixel representing one DMX channel value.

2. **Control Panel**: The bottom section contains intuitive controls organized into logical groups:
   - **Visualization Settings**: Controls for pixel size, gaps, starting position, canvas dimensions, and frame rate
   - **Art-Net Settings**: Universe management tools to add/remove monitored universes
   - **Save Settings**: Saves your current configuration to the `config.yaml` file

3. **Menu Bar**: Provides access to:
   - **File**: Exit the application
   - **Settings**: Open advanced settings dialog for Art-Net network configuration and test pattern settings
   - **Help**: About dialog and documentation

### Direct Universe Management

You can directly manage which universes you want to monitor:

1. The universe list displays all currently monitored universes
2. Use the numeric spinner and "Add" button to add a new universe 
3. Select one or more universes and click "Remove" to stop monitoring them
4. Changes take effect immediately for real-time testing

### Advanced Settings Dialog

The Settings dialog allows configuration of Art-Net network settings and test pattern generation:

- **Art-Net Settings**: Configure IP address, port, and universes
- **Test Source Settings**: Enable/disable test pattern generator, select pattern type, and adjust animation speed

## Configuration

While most settings can be adjusted directly through the user interface, the application also uses a YAML configuration file (`config.yaml`) for persistence. This file is automatically created or updated when you click "Save Settings to Config" in the UI.

Example configuration:

```yaml
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
    # Add more universes as needed

# Test Source Configuration
test_source:
  # Enable test source instead of Art-Net listener
  enabled: false
  # Pattern type to generate
  pattern: "MOVING_BAR_H"
  # Animation speed multiplier
  speed: 1.0

# Visualization Settings
pixel_size: 1
gap_x: 0
gap_y: 0
canvas_width: 0
canvas_height: 0
start_x: 0
start_y: 0
frame_rate: 44
```

### Configuration Options

#### Art-Net Settings
- `host`: IP address to bind to (use "0.0.0.0" to listen on all interfaces)
- `port`: UDP port for Art-Net (default is 6454)
- `universes`: List of Art-Net universes to monitor

#### Test Source Settings
- `enabled`: Whether to use the test pattern generator instead of listening for real Art-Net data (default: false)
- `pattern`: Type of pattern to generate. Options are:
  - `GRADIENT_H`: Horizontal gradient (left to right)
  - `GRADIENT_V`: Vertical gradient (top to bottom)
  - `CHECKERBOARD`: Animated checkerboard pattern
  - `MOVING_BAR_H`: Horizontal moving bar
  - `MOVING_BAR_V`: Vertical moving bar
  - `PULSE`: Pulsing brightness
  - `RANDOM`: Random noise
  - `SINE_WAVE`: Sine wave pattern
- `speed`: Animation speed multiplier (higher = faster, default: 1.0)

#### Visualization Settings
- `pixel_size`: Size of each pixel in screen pixels (default: 1)
- `gap_x`: Horizontal gap between pixels in screen pixels (default: 0)
- `gap_y`: Vertical gap between pixels in screen pixels (default: 0)
- `canvas_width`: Overall width of the canvas in pixels (0 = auto-size based on content + start_x)
- `canvas_height`: Overall height of the canvas in pixels (0 = auto-size based on content + start_y)
- `start_x`: X position of visualization from top-left of canvas (default: 0)
- `start_y`: Y position of visualization from top-left of canvas (default: 0)
- `frame_rate`: Update rate for the visualization (default: 44, which is the DMX standard)

## Common Use Cases

### Basic Setup for DMX Monitoring

1. **Launch the application** using `./run.sh`
2. **Set which universes to monitor** using the Universe control panel
3. **Adjust visualization settings** as needed:
   - Increase `Pixel Size` for better visibility
   - Add `H-Gap` or `V-Gap` to create spacing between pixels/universes
4. **Save your settings** by clicking "Save Settings to Config"

** to apply the settings and restart the application when prompted

### Integrating with Syphon-compatible Applications

1. Configure ArtNetViz to visualize your desired universes
2. Launch a Syphon-compatible application (e.g., VDMX, MadMapper, OBS with Syphon plugin)
3. In the receiving application, select "ArtNet Visualizer" as the Syphon source
4. The DMX visualization will appear in real-time in the receiving application


## License

MIT