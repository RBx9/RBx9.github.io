#!/usr/bin/env python3
# RBx9 Signer v1.3.10 - remove the old transmission startup entirely.
# Make the real app content visible without an artificial launch delay.
# Based on Feather GPL-3.0; leaves signing, IPA import, and storage unchanged.
from pathlib import Path
import shutil

root = Path("feather")
app = root / "Feather"
entry = app / "FeatherApp.swift"
src = entry.read_text()

fields = """    @Environment(\\.accessibilityReduceMotion) private var rbx9ReduceMotion
    @State private var rbx9ShowingStartup = true
"""
if src.count(fields) != 1:
    raise RuntimeError("Old RBx9 splash state has changed; cannot safely remove")
src = src.replace(fields, "", 1)

start_marker = """            .overlay {
                if rbx9ShowingStartup {
                    RBx9TransmissionStartup()"""
start = src.find(start_marker)
if start < 0 or src.count(start_marker) != 1:
    raise RuntimeError("Old transmission overlay not found exactly once")
end = src.find("            .onAppear {", start)
if end < 0:
    raise RuntimeError("Missing original app onAppear after the transmission")
removed = src[start:end]
if ".task {" not in removed or "Task.sleep(" not in removed or "230_000_000" not in removed:
    raise RuntimeError("Unexpected splash block: refusing to remove non-splash startup code")
src = src[:start] + src[end:]

# Native SwiftUI View was appended to FeatherApp by v1.3.7. Delete the
# complete unused view rather than merely hiding it, avoiding any animation
# drawing or timer work at startup.
splash_header = "// MARK: - RBx9 startup transmission (iOS 16+)"
if src.count(splash_header) != 1:
    raise RuntimeError("Unexpected transmission view definition")
head, tail = src.split(splash_header, 1)
if "private struct RBx9TransmissionStartup: View" not in tail:
    raise RuntimeError("Unexpected code after transmission header")
src = head.rstrip() + "\n"

for banned in [
    "RBx9TransmissionStartup",
    "rbx9ShowingStartup",
    "rbx9ReduceMotion",
    "TRANSMISSION ESTABLISHED",
    "INITIALIZING SECURE WORKSPACE",
    "RBx9LaunchIcon",
    "230_000_000",
]:
    if banned in src:
        raise RuntimeError("Startup cleanup incomplete: " + banned)

entry.write_text(src)

# No reason to compile a splash-only icon asset after removing the view.
splash_icon = app / "Resources/Assets.xcassets/RBx9LaunchIcon.imageset"
if splash_icon.is_dir():
    shutil.rmtree(splash_icon)

config = root / "Feather.xcconfig"
cfg = config.read_text()
if cfg.count("FEATHER_PROJECT_VERSION=1.3.9") != 1:
    raise RuntimeError("Expected version 1.3.9 before launch cleanup")
config.write_text(cfg.replace("FEATHER_PROJECT_VERSION=1.3.9", "FEATHER_PROJECT_VERSION=1.3.10", 1))

print("RBx9 v1.3.10: old animated splash, startup timer, and unused icon removed")
print("App scene starts immediately; the normal iOS system launch transition still applies")
