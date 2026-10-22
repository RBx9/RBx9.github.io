#!/usr/bin/env python3
"""Track only the newest iOS/iPadOS Stremio IPA from gorlev/stremio-altstore.

Reads the upstream AltStore JSON downloaded by GitHub Actions. The IPA itself
continues to come from Stremio's public CDN, not from the RBx9 GitHub Releases.
"""
import argparse
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent.parent
CATALOG = BASE / "catalog.json"
STREMIO_ID = "com.stremio.pal"
IOS_CDN_URL = re.compile(r"https://dl\.strem\.io/apple/[^/]+/ios/stremio_iOS\.ipa", re.IGNORECASE)


def numeric_version(value):
    value = str(value)
    if not re.fullmatch(r"\d+(?:\.\d+){1,4}", value):
        raise ValueError("Invalid upstream Stremio version: " + value)
    parts = tuple(int(p) for p in value.split("."))
    return parts + (0,) * (5 - len(parts))


def select_latest_ios(source):
    apps = source.get("apps")
    if not isinstance(apps, list):
        raise ValueError("Upstream Stremio feed has no valid apps array")
    matches = [app for app in apps if app.get("bundleIdentifier") == STREMIO_ID]
    if len(matches) != 1:
        raise ValueError("Expected exactly one Stremio iOS/iPadOS application")

    app = matches[0]
    versions = app.get("versions")
    if not isinstance(versions, list) or not versions:
        raise ValueError("Upstream Stremio feed contains no versions")

    supported = []
    for version in versions:
        url = version.get("downloadURL", "")
        if not isinstance(url, str) or not IOS_CDN_URL.fullmatch(url):
            continue  # Never import tvOS, macOS, or non-Stremio hosting URLs.
        size = version.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("Invalid Stremio IPA byte size")
        version_num = numeric_version(version.get("version", ""))
        build = str(version.get("buildVersion", "0"))
        if not build.isdigit():
            raise ValueError("Invalid Stremio build number")
        supported.append((version_num, int(build), version))

    if not supported:
        raise ValueError("No valid iOS/iPadOS IPA link found in upstream feed")
    supported.sort(key=lambda record: (record[0], record[1]), reverse=True)
    return app, supported[0][2]


def sync(source_file, catalog_file):
    upstream = json.loads(source_file.read_text(encoding="utf-8"))
    app, latest = select_latest_ios(upstream)
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict):
        raise ValueError("Source catalog is not an object")

    latest_version = {
        key: latest[key]
        for key in ("version", "buildVersion", "date", "downloadURL", "size",
                    "minOSVersion", "sha256", "localizedDescription")
        if key in latest
    }
    if not latest_version.get("date"):
        raise ValueError("Upstream version is missing a release date")
    if not latest_version.get("minOSVersion"):
        raise ValueError("Upstream version is missing minimum iOS version")

    # Replace, rather than extend: users requested the latest iOS/iPadOS only.
    catalog[STREMIO_ID] = {
        "name": "Stremio",
        "developerName": "Stremio",
        "subtitle": "iPhone & iPad · latest iOS/iPadOS release",
        "localizedDescription": (
            "Stremio for iOS and iPadOS. The IPA downloads directly from "
            "Stremio's CDN; metadata is synced from the unofficial "
            "gorlev/stremio-altstore source."
        ),
        "iconURL": app.get("iconURL") or "https://www.stremio.com/website/stremio-logo-small.png",
        "tintColor": app.get("tintColor") or "#7055D9",
        "category": app.get("category") or "entertainment",
        "versions": [latest_version],
    }
    if app.get("screenshots"):
        catalog[STREMIO_ID]["screenshots"] = app["screenshots"]

    new_data = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
    if catalog_file.read_text(encoding="utf-8") != new_data:
        catalog_file.write_text(new_data, encoding="utf-8")
        print("Updated Stremio iOS/iPadOS to", latest["version"], "build", latest.get("buildVersion"))
    else:
        print("Stremio already up to date:", latest["version"], "build", latest.get("buildVersion"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    args = parser.parse_args()
    sync(args.source, args.catalog)
