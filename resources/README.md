# Resources Directory

This directory contains resources used by the ArtNetViz application.

## Directory Structure

- `/icons`: Contains icons for the application
  - `app_icon.icns`: macOS application icon (required for proper app bundling)

## Adding Resources

When adding resources to this directory, they will be automatically included in the built application. The resources will maintain their relative directory structure when bundled.

## Icon Guidelines

To create an `app_icon.icns` file:

1. Create a PNG image at 1024x1024 pixels (recommended size)
2. Use the macOS IconUtil to convert it:
   ```bash
   # From Terminal, with your .png file in the current directory
   mkdir MyIcon.iconset
   sips -z 16 16     icon.png --out MyIcon.iconset/icon_16x16.png
   sips -z 32 32     icon.png --out MyIcon.iconset/icon_16x16@2x.png
   sips -z 32 32     icon.png --out MyIcon.iconset/icon_32x32.png
   sips -z 64 64     icon.png --out MyIcon.iconset/icon_32x32@2x.png
   sips -z 128 128   icon.png --out MyIcon.iconset/icon_128x128.png
   sips -z 256 256   icon.png --out MyIcon.iconset/icon_128x128@2x.png
   sips -z 256 256   icon.png --out MyIcon.iconset/icon_256x256.png
   sips -z 512 512   icon.png --out MyIcon.iconset/icon_256x256@2x.png
   sips -z 512 512   icon.png --out MyIcon.iconset/icon_512x512.png
   sips -z 1024 1024 icon.png --out MyIcon.iconset/icon_512x512@2x.png
   iconutil -c icns MyIcon.iconset
   mv MyIcon.icns resources/icons/app_icon.icns
   ```

3. Or use a tool like [IconMaker](https://apps.apple.com/us/app/iconmaker/id1471172350) from the Mac App Store 