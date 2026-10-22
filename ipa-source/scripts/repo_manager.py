#!/usr/bin/env python3
"""Generate Feather/AltStore and ESign source JSON from release IPAs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import sys
import zipfile

BASE = Path(__file__).resolve().parent.parent
CATALOG = BASE / "catalog.json"
ROOT = "https://rbx9.github.io/ipa-source"
ICON = "https://rbx9.github.io/icon.png"

def load():
    if not CATALOG.exists():
        return {}
    value = json.loads(CATALOG.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("catalog.json must be an object")
    return value

def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def info_from_ipa(path):
    with zipfile.ZipFile(path) as z:
        candidates = [f for f in z.infolist()
                      if f.filename.startswith("Payload/") and
                      f.filename.count("/") == 2 and
                      f.filename.endswith(".app/Info.plist")]
        if len(candidates) != 1:
            raise ValueError("Expected one Payload/*.app/Info.plist")
        if candidates[0].file_size > 1048576:
            raise ValueError("Oversized Info.plist")
        info = plistlib.loads(z.read(candidates[0]))
    for name in ("CFBundleIdentifier", "CFBundleShortVersionString", "CFBundleVersion"):
        if not info.get(name):
            raise ValueError("IPA missing " + name)
    return {
        "bundle": str(info["CFBundleIdentifier"]),
        "name": str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or path.stem),
        "version": str(info["CFBundleShortVersionString"]),
        "build": str(info["CFBundleVersion"]),
        "minOS": str(info.get("MinimumOSVersion", ""))
    }

def add(args):
    path = Path(args.ipa)
    if not path.is_file():
        raise FileNotFoundError(path)
    if not args.url.startswith("https://") or not args.url.lower().endswith(".ipa"):
        raise ValueError("Provide a direct HTTPS .ipa asset URL")
    details = info_from_ipa(path)
    catalog = load()
    app = catalog.setdefault(details["bundle"], {
        "name": details["name"], "developerName": "RBx9",
        "subtitle": "Download and sideload this iOS app",
        "localizedDescription": "Available in the RBx9 IPA Library.",
        "iconURL": ICON, "category": "utilities", "versions": []
    })
    notes = Path(args.notes_file).read_text(encoding="utf-8").strip() if args.notes_file else ""
    release = {
        "version": details["version"], "buildVersion": details["build"],
        "date": args.date or datetime.now(timezone.utc).isoformat(),
        "downloadURL": args.url, "size": path.stat().st_size
    }
    if details["minOS"]:
        release["minOSVersion"] = details["minOS"]
    if notes:
        release["localizedDescription"] = notes[:3500]
    versions = app.setdefault("versions", [])
    versions[:] = [v for v in versions if
                   (str(v.get("version")), str(v.get("buildVersion"))) !=
                   (release["version"], release["buildVersion"])]
    versions.insert(0, release)
    versions.sort(key=lambda v: v["date"], reverse=True)
    write(CATALOG, catalog)
    render()
    print("Added", details["name"], release["version"])

def render():
    feather_apps, esign_apps = [], []
    for bundle, meta in sorted(load().items(), key=lambda pair: pair[1].get("name", "").lower()):
        versions = sorted(meta.get("versions") or [], key=lambda v: v["date"], reverse=True)
        if not versions:
            continue
        for v in versions:
            if not str(v.get("downloadURL", "")).startswith("https://"):
                raise ValueError("Invalid URL for " + bundle)
            if not isinstance(v.get("size"), int) or v["size"] <= 0:
                raise ValueError("Invalid IPA size for " + bundle)
        app = {
            "name": meta.get("name", bundle), "bundleIdentifier": bundle,
            "developerName": meta.get("developerName", "RBx9"),
            "subtitle": meta.get("subtitle", "iOS app"),
            "localizedDescription": meta.get("localizedDescription", "Download and sign this IPA."),
            "iconURL": meta.get("iconURL", ICON),
            "tintColor": meta.get("tintColor", "#739AF5"),
            "category": meta.get("category", "utilities"),
        }
        if meta.get("screenshots"):
            app["screenshots"] = meta["screenshots"]
        feather_apps.append({**app, "versions": versions})
        latest = versions[0]
        esign_apps.append({
            **app, "version": latest["version"], "versionDate": latest["date"],
            "downloadURL": latest["downloadURL"], "size": latest["size"],
            "versionDescription": latest.get("localizedDescription", ""),
            **({"minOSVersion": latest["minOSVersion"]} if latest.get("minOSVersion") else {})
        })
    common = {
        "name": "RBx9 IPA Library", "identifier": "com.rbx9.ipa.library",
        "subtitle": "iOS applications for Feather and ESign",
        "description": "Browse IPAs from RBx9. Requires your own compatible signing method.",
        "iconURL": ICON, "website": ROOT + "/"
    }
    write(BASE / "source.json", {**common, "sourceURL": ROOT + "/source.json", "apps": feather_apps, "news": []})
    write(BASE / "esign.json", {**common, "apps": esign_apps})
    print("Generated", len(feather_apps), "app entries")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("render")
    add_parser = sub.add_parser("add")
    add_parser.add_argument("--ipa", required=True)
    add_parser.add_argument("--url", required=True)
    add_parser.add_argument("--date", default="")
    add_parser.add_argument("--notes-file", default="")
    args = parser.parse_args()
    try:
        add(args) if args.command == "add" else render()
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print("Source generation failed:", exc, file=sys.stderr)
        sys.exit(1)
