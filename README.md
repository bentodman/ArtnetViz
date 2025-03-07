# PyQt6 Canvas with Syphon

A drawing canvas application built with PyQt6 that exposes itself as a Syphon source on macOS. This allows other applications to receive the canvas content in real-time.

## Features

- Drawing canvas with adjustable pen width and color
- Real-time exposure of canvas content as a Syphon source
- Simple, user-friendly interface

## Requirements

- Python 3.9+
- macOS (required for Syphon)
- PyQt6
- syphon-python
- NumPy

## Installation

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
   pip install PyQt6 numpy pyobjc
   ```

4. Install syphon-python from source:
   ```
   git clone --recurse-submodules https://github.com/cansik/syphon-python.git
   cd syphon-python
   pip install -e .
   cd ..
   ```

## Usage

Run the application:

```
python src/main.py
```

The application provides a white canvas where you can draw using your mouse. The controls at the bottom allow you to adjust the pen width, change the pen color, and clear the canvas.

The canvas content is automatically published as a Syphon source named "PyQt6 Canvas", which can be accessed by other Syphon-compatible applications like VDMX, MadMapper, or Processing.

## How It Works

The application uses:

1. **PyQt6** for the GUI and drawing functionality
2. **syphon-python** to expose the canvas as a Syphon source
3. **Metal** (via syphon-python) for GPU-accelerated texture sharing

Each time the canvas is updated, the application:
1. Converts the QPixmap canvas to a NumPy array
2. Copies the array data to a Metal texture
3. Publishes the texture to Syphon

## License

MIT

## Acknowledgements

- [syphon-python](https://github.com/cansik/syphon-python) by cansik
- [Syphon Framework](https://github.com/Syphon/Syphon-Framework)
- [PyQt](https://www.riverbankcomputing.com/software/pyqt/) 