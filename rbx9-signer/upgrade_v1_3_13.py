#!/usr/bin/env python3
# RBx9 Signer v1.3.13 — install the approved dark RBx9 icon.
# The previous icon is preserved in the GitHub branch at
# rbx9-signer/icon-original-before-dark-base64.txt for quick rollback.
from pathlib import Path
import subprocess

root = Path("feather")
source = Path("rbx9-source-icon.png")
app = root / "Feather"
main_icons = app / "Resources/Assets.xcassets/AppIcon.appiconset"
launch_icon = app / "Resources/Assets.xcassets/RBx9LaunchIcon.imageset/rbx9-launch.png"

def dimensions(path: Path) -> tuple[int, int]:
    if not path.is_file():
        raise RuntimeError("Missing iOS icon: " + str(path))
    output = subprocess.check_output(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
        text=True
    )
    width = height = None
    for line in output.splitlines():
        if "pixelWidth:" in line:
            width = int(line.split(":")[-1].strip())
        if "pixelHeight:" in line:
            height = int(line.split(":")[-1].strip())
    if width is None or height is None:
        raise RuntimeError("Cannot inspect icon dimensions: " + str(path))
    return width, height

# Apple App Store icon source must be square 1024x1024, and our project
# creates the final PNG from the 1024 RGB JPEG without any alpha channel.
if dimensions(source) != (1024, 1024):
    raise RuntimeError("The selected RBx9 source icon is not 1024 x 1024")
for name in ("rbx9.png", "rbx9_dark.png", "rbx9_tint.png"):
    path = main_icons / name
    if dimensions(path) != (1024, 1024):
        raise RuntimeError("Wrong app icon dimensions: " + str(path))
    if path.read_bytes() != source.read_bytes():
        raise RuntimeError("The main icon artwork does not match the selected dark logo")
if dimensions(launch_icon) != (1024, 1024):
    raise RuntimeError("The launch screen icon artwork has incorrect dimensions")
if launch_icon.read_bytes() != source.read_bytes():
    raise RuntimeError("The launch screen icon does not match the new main app icon")

selector = app / "Views/Settings/App Icon/AppIconView.swift"
code = selector.read_text()
if code.count('AltIcon(displayName: "Original RB9 (Default)"') != 1:
    raise RuntimeError("Default app icon selector label changed")
code = code.replace('AltIcon(displayName: "Original RB9 (Default)"',
                    'AltIcon(displayName: "RBx9 Dark (Default)"', 1)
selector.write_text(code)

cfg = root / "Feather.xcconfig"
config = cfg.read_text()
previous_version = "FEATHER_PROJECT_VERSION=1.3.12"
if config.count(previous_version) != 1:
    raise RuntimeError("Expected v1.3.12 before icon update")
cfg.write_text(config.replace(previous_version, "FEATHER_PROJECT_VERSION=1.3.13", 1))
print("RBx9 v1.3.13: approved 1024x1024 dark icon applied to primary and launch artwork")
