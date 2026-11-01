#!/usr/bin/env python3
# RBx9 Signer v1.3.11 - remove Feather's iOS launch glyph,
# restore/preserve RBx9's native transmission opening.
# Applied after v1.3.9 (intentionally skips the v1.3.10 overlay removal).
from pathlib import Path

root=Path("feather")
app=root/"Feather"
storyboard=app/"Resources/Launch Screen.storyboard"
old=storyboard.read_text()

# The iOS system launch storyboard is what displays the upstream Feather
# logo before the SwiftUI scene appears. Remove that logo, not RBx9's overlay.
assert old.count('image="Glyph"') == 1, "Expected upstream Feather Glyph in launch storyboard"
assert 'launchScreen="YES"' in old, "Expected iOS launch storyboard"

new='''<?xml version="1.0" encoding="UTF-8"?>
<document type="com.apple.InterfaceBuilder3.CocoaTouch.Storyboard.XIB" version="3.0" toolsVersion="24506" targetRuntime="iOS.CocoaTouch" propertyAccessControl="none" useAutolayout="YES" launchScreen="YES" useTraitCollections="YES" useSafeAreas="YES" colorMatched="YES" initialViewController="01J-lp-oVM">
    <device id="retina6_12" orientation="portrait" appearance="dark"/>
    <dependencies>
        <deployment identifier="iOS"/>
        <plugIn identifier="com.apple.InterfaceBuilder.IBCocoaTouchPlugin" version="24504"/>
        <capability name="documents saved in the Xcode 8 format" minToolsVersion="8.0"/>
    </dependencies>
    <scenes>
        <scene sceneID="EHf-IW-A2E">
            <objects>
                <viewController id="01J-lp-oVM" sceneMemberID="viewController">
                    <view key="view" contentMode="scaleToFill" id="Ze5-6b-2t3">
                        <rect key="frame" x="0.0" y="0.0" width="393" height="852"/>
                        <viewLayoutGuide key="safeArea" id="Bcu-3y-fUS"/>
                        <color key="backgroundColor" red="0.022" green="0.045" blue="0.085" alpha="1" colorSpace="custom" customColorSpace="sRGB"/>
                    </view>
                </viewController>
                <placeholder placeholderIdentifier="IBFirstResponder" id="iYj-Kq-Ea1" userLabel="First Responder" sceneMemberID="firstResponder"/>
            </objects>
            <point key="canvasLocation" x="52.67" y="374.65"/>
        </scene>
    </scenes>
</document>
'''
storyboard.write_text(new)

# The earlier 1.3.7/1.3.8 patches provide the cyan RBx9 splash,
# retained with a 230 ms automatic dismissal. Don't modify the animation.
entry=(app/"FeatherApp.swift").read_text()
for expected in [
    'RBx9TransmissionStartup()',
    'private struct RBx9TransmissionStartup: View',
    'rbx9ShowingStartup',
    '230_000_000',
    'Image("RBx9LaunchIcon")',
]:
    if expected not in entry:
        raise RuntimeError("RBx9 transmission animation missing: "+expected)
if not (app/"Resources/Assets.xcassets/RBx9LaunchIcon.imageset/rbx9-launch.png").is_file():
    raise RuntimeError("RBx9 splash brand icon missing")
if 'Glyph' in new or '<imageView' in new:
    raise RuntimeError("Feather launch glyph still present")

# Retain storyboard registration; without it iOS could show a fallback launch.
project=(root/"Feather.xcodeproj/project.pbxproj").read_text()
if project.count('INFOPLIST_KEY_UILaunchStoryboardName = "Launch Screen.storyboard";') < 1:
    raise RuntimeError("App launch storyboard configuration changed")

cfg=root/"Feather.xcconfig"
text=cfg.read_text()
oldversion="FEATHER_PROJECT_VERSION=1.3.9"
if text.count(oldversion) != 1:
    raise RuntimeError("Expected 1.3.9 patch base for RBx9 v1.3.11")
cfg.write_text(text.replace(oldversion, "FEATHER_PROJECT_VERSION=1.3.11", 1))
print("RBx9 v1.3.11: Feather glyph removed, dark launch canvas set, RBx9 transmission restored")
