# Art-Net Visualizer with Syphon

A PyQt6 application that listens to Art-Net DMX data, visualizes it as pixels on a canvas, and exposes the canvas as a Syphon source on macOS. This allows other applications to receive the visualization in real-time.

## Features

- Listens to multiple Art-Net universes defined in a configuration file
- Visualizes each DMX channel as a pixel (value 0-255 mapped from black to white)
- Each universe occupies one row of 512 pixels (one pixel per DMX channel)
- Configurable pixel size and spacing for better visibility
- Configurable canvas size and visualization position
- Real-time exposure of the visualization as a Syphon source at 44Hz (standard DMX512 refresh rate)
- Properly handles port sharing with other Art-Net applications
- Built-in test pattern generator with various patterns for testing without an external Art-Net source
- Available as a portable standalone macOS application

## Requirements

- macOS (required for Syphon)
- For standalone app: macOS 10.15 or newer
- For development: Python 3.9+, PyQt6, syphon-python, NumPy, PyYAML

## Installation

### Option 1: Standalone macOS Application (Recommended)

1. Download the latest `ArtNetViz.zip` from the releases page
2. Extract the ZIP file
3. Move `ArtNetViz.app` to your Applications folder
4. Right-click on the app and select "Open" (required only the first time to bypass macOS security)

### Option 2: From Source (Development)

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/ArtnetViz.git
   cd ArtnetViz
   ```

2. Create a virtual environment and activate it:
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Install syphon-python from source:
   ```
   pip install git+https://github.com/cansik/syphon-python.git
   ```

5. Run the application:
   ```
   ./start.sh
   ```

## Building the Standalone Application

If you want to build the standalone application yourself:

1. Make sure you have Python 3.9+ and pip installed
2. Run the build script:
   ```
   ./build_app.sh
   ```
3. The standalone application will be created in the `dist` folder as `ArtNetViz.app`
4. A ZIP archive for distribution will also be created at `dist/ArtNetViz.zip`

## Configuration

The application uses a YAML configuration file (`config.yaml`) to specify Art-Net and visualization settings. The file should be placed in the root directory of the project.

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

# Visualization Configuration
visualization:
  # Size of each pixel (width and height in screen pixels)
  pixel_size: 1
  # Horizontal gap between pixels (in screen pixels)
  gap_x: 0
  # Vertical gap between pixels (in screen pixels)
  gap_y: 0
  # Overall canvas width (0 = auto-size based on content)
  canvas_width: 0
  # Overall canvas height (0 = auto-size based on content)
  canvas_height: 0
  # X position of visualization from top-left of canvas
  start_x: 0
  # Y position of visualization from top-left of canvas
  start_y: 0
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

#### Example Configurations:

**Basic View (Default)**
```yaml
visualization:
  pixel_size: 1
  gap_x: 0
  gap_y: 0
  canvas_width: 0
  canvas_height: 0
  start_x: 0
  start_y: 0
```

**Spaced Grid**
```yaml
visualization:
  pixel_size: 3
  gap_x: 1
  gap_y: 1
```

**Fixed Canvas with Centered Visualization**
```yaml
visualization:
  pixel_size: 2
  gap_x: 0
  gap_y: 0
  canvas_width: 1024
  canvas_height: 768
  start_x: 100
  start_y: 50
```

**Multiple Universe Display with Row Spacing**
```yaml
visualization:
  pixel_size: 2
  gap_x: 0
  gap_y: 10
```

## Usage

Run the application using the provided shell script:

```
./start.sh
```

Or with npm:

```
npm start
```

The application will:
1. Read the configuration file to determine which Art-Net universes to listen to and how to visualize them
2. Create a canvas with the specified dimensions (or auto-sized based on content)
3. Position the visualization within the canvas according to the configuration
4. Listen for incoming Art-Net DMX data on the specified universes
5. Visualize each DMX channel as a pixel with its brightness corresponding to the channel value (0-255)
6. Publish the visualization as a Syphon source named "ArtNet Visualizer", which can be accessed by other Syphon-compatible applications

## Port Sharing

The application uses socket options `SO_REUSEADDR` and `SO_REUSEPORT` (if available) to properly handle port sharing with other Art-Net applications. This allows the visualizer to receive Art-Net data even when other lighting control software is already using the standard Art-Net port (6454).

## Using the Test Pattern Generator

The application includes a built-in test pattern generator that can generate various Art-Net DMX patterns without requiring an external Art-Net controller. This is useful for:

1. Testing Syphon integration with other applications
2. Developing and debugging the visualizer
3. Demonstrating the application without external hardware
4. Creating interesting visual patterns for creative purposes

To enable the test pattern generator:

1. Open the `config.yaml` file
2. Set `test_source.enabled` to `true`
3. Choose a pattern type from the available options
4. Optionally adjust the animation speed

Example test source configuration:

```yaml
# Test Source Configuration
test_source:
  # Enable test source instead of Art-Net listener
  enabled: true
  # Pattern type to generate
  pattern: "SINE_WAVE"
  # Animation speed multiplier
  speed: 0.5
```

When test source is enabled, the application will generate the specified pattern at the standard Art-Net refresh rate (44Hz) instead of listening for external Art-Net data.

## How It Works

The application uses:

1. **Custom Art-Net listener** to receive incoming Art-Net data with proper port sharing
2. **PyQt6** for the GUI and canvas display
3. **syphon-python** to expose the canvas as a Syphon source
4. **Metal** (via syphon-python) for GPU-accelerated texture sharing

The application:
1. Creates an Art-Net listener that binds to the specified port with proper socket options
2. Updates the canvas at 44Hz (standard DMX512 refresh rate)
3. Renders each DMX channel as a grayscale pixel in a row for each universe, with size and spacing based on the configuration
4. Converts the canvas to a NumPy array
5. Copies the array data to a Metal texture
6. Publishes the texture to Syphon

## License

MIT

## Acknowledgements

- [syphon-python](https://github.com/cansik/syphon-python) by cansik
- [Syphon Framework](https://github.com/Syphon/Syphon-Framework)
- [PyQt](https://www.riverbankcomputing.com/software/pyqt/) 