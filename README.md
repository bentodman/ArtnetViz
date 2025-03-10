# ArtnetViz

A visualization tool for Art-Net DMX data with Syphon integration.

## Installation

There are two ways to install ArtnetViz:

### Option 1: Using Pre-built Wheel (Recommended)

1. Download the latest release from the releases page
2. Extract the archive
3. Run the setup script:
```bash
./setup.sh  # On macOS
```

### Option 2: Building from Source

This option requires Xcode Command Line Tools to be installed.

1. Install Xcode Command Line Tools:
```bash
xcode-select --install
```

2. Clone the repository:
```bash
git clone https://github.com/bentodman/ArtnetViz.git
cd ArtnetViz
```

3. Run the setup script:
```bash
./setup.sh
```

## Usage

Run the application:
```bash
./run.sh
```

## Features

- Real-time visualization of Art-Net DMX data
- Support for multiple universes
- Syphon integration for macOS
- DMX recording and playback functionality
- Test pattern generator for offline testing

## Requirements

- macOS (required for Syphon)
- Python 3.8 or higher
- PyQt6
- numpy

## For Developers

### Building the Wheel

If you want to build the Syphon wheel yourself:

1. Make sure you have Xcode Command Line Tools installed
2. Run the build script:
```bash
./build_wheel.sh
```

This will create a wheel file in the `dist` directory that can be distributed to users.

## Configuration

The application can be configured through the `config.yaml` file. See the example configuration for available options.

## License

[Your chosen license]