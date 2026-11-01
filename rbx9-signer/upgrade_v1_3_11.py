#!/usr/bin/env python3
# RBx9 Signer v1.3.11 - one startup screen only:
# replace Feather's original iOS launch image with RBx9.
# Applied after v1.3.10, which removed the separate SwiftUI startup overlay.
from pathlib import Path
import json
import shutil

root=Path("feather")
app=root/"Feather"
storyboard=app/"Resources/Launch Screen.storyboard"
old=storyboard.read_text()

# The iOS system launch storyboard is what displays the upstream Feather
# logo before SwiftUI. Replace that Glyph with the RBx9 icon in the same
# system storyboard so users see one continuous branded launch.
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
                        <subviews>
                            <imageView clipsSubviews="YES" userInteractionEnabled="NO" contentMode="scaleAspectFit" horizontalHuggingPriority="251" verticalHuggingPriority="251" image="RBx9LaunchIcon" translatesAutoresizingMaskIntoConstraints="NO" id="RB9-startup-icon">
                                <rect key="frame" x="124.5" y="354" width="144" height="144"/>
                                <constraints>
                                    <constraint firstAttribute="width" constant="144" id="RB9-startup-width"/>
                                    <constraint firstAttribute="height" constant="144" id="RB9-startup-height"/>
                                </constraints>
                            </imageView>
                        </subviews>
                        <viewLayoutGuide key="safeArea" id="Bcu-3y-fUS"/>
                        <color key="backgroundColor" red="0.022" green="0.045" blue="0.085" alpha="1" colorSpace="custom" customColorSpace="sRGB"/>
                        <constraints>
                            <constraint firstItem="RB9-startup-icon" firstAttribute="centerX" secondItem="Ze5-6b-2t3" secondAttribute="centerX" id="RB9-centerX"/>
                            <constraint firstItem="RB9-startup-icon" firstAttribute="centerY" secondItem="Ze5-6b-2t3" secondAttribute="centerY" id="RB9-centerY"/>
                        </constraints>
                    </view>
                </viewController>
                <placeholder placeholderIdentifier="IBFirstResponder" id="iYj-Kq-Ea1" userLabel="First Responder" sceneMemberID="firstResponder"/>
            </objects>
            <point key="canvasLocation" x="52.67" y="374.65"/>
        </scene>
    </scenes>
    <resources>
        <image name="RBx9LaunchIcon" width="1024" height="1024"/>
    </resources>
</document>
'''
storyboard.write_text(new)

# iOS owns this static system launch screen. Do not overlay an animated
# RBx9 or Feather startup; 1.3.10 removed the separate SwiftUI animation.
entry=(app/"FeatherApp.swift").read_text()
for unexpected in [
    'RBx9TransmissionStartup',
    'rbx9ShowingStartup',
    '230_000_000',
    'TRANSMISSION ESTABLISHED',
]:
    if unexpected in entry:
        raise RuntimeError("A second startup animation is still present: "+unexpected)

# The v1.3.10 cleanup deleted the old splash-only assets. Restore only the
# branded image resource needed by the real iOS launch storyboard.
icon=app/"Resources/Assets.xcassets/RBx9LaunchIcon.imageset"
icon.mkdir(parents=True, exist_ok=True)
shutil.copy2("rbx9-source-icon.png", icon/"rbx9-launch.png")
(icon/"Contents.json").write_text(json.dumps({
    "images": [{"filename": "rbx9-launch.png", "idiom": "universal"}],
    "info": {"author": "xcode", "version": 1}
}, indent=2)+"\n")
if not (icon/"rbx9-launch.png").is_file():
    raise RuntimeError("iOS launch RBx9 brand icon missing")

if 'Glyph' in new or 'image="RBx9LaunchIcon"' not in new:
    raise RuntimeError("iOS launch storyboard does not use RBx9 artwork")
if new.count('image="RBx9LaunchIcon"') != 1:
    raise RuntimeError("RBx9 system launch artwork is not unique")
# Parse the generated XML before handing it to Interface Builder.
import xml.etree.ElementTree as ET
ET.fromstring(new)

# Retain storyboard registration; without it iOS could show a fallback launch.
project=(root/"Feather.xcodeproj/project.pbxproj").read_text()
if project.count('INFOPLIST_KEY_UILaunchStoryboardName = "Launch Screen.storyboard";') < 1:
    raise RuntimeError("App launch storyboard configuration changed")

cfg=root/"Feather.xcconfig"
text=cfg.read_text()
oldversion="FEATHER_PROJECT_VERSION=1.3.10"
if text.count(oldversion) != 1:
    raise RuntimeError("Expected 1.3.10 patch base for RBx9 v1.3.11")
cfg.write_text(text.replace(oldversion, "FEATHER_PROJECT_VERSION=1.3.11", 1))
print("RBx9 v1.3.11: one iOS system launch screen with RBx9 logo; no Feather glyph or secondary animation")
