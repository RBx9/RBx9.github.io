#!/usr/bin/env python3
"""Generate Feather/AltStore and ESign source JSON from release IPAs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import plistlib
import sys
import zipfile
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

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
    path.parent.mkdir(parents=True, exist_ok=True)
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

def sync_icons(args):
    """Resolve app artwork for App Store bundle IDs while preserving custom art.

    Native Assets.car icons inside IPA packages are not readable with plistlib
    on Linux. Apple's Lookup API is a best-effort alternative.
    """
    catalog = load()
    dirty = False
    for bundle, app in catalog.items():
        current = app.get("iconURL")
        if current and current != ICON and bundle != args.force_bundle:
            continue
        try:
            request_url = "https://itunes.apple.com/lookup?" + urlencode({
                "bundleId": bundle, "country": "us", "entity": "software"
            })
            request = Request(request_url, headers={
                "User-Agent": "RBx9-IPA-Catalog/1.0",
                "Accept": "application/json"
            })
            with urlopen(request, timeout=12) as response:
                payload = response.read(1024 * 1024)
            rows = json.loads(payload).get("results", [])
            matches = [
                row for row in rows
                if row.get("bundleId", "").lower() == bundle.lower()
            ]
            artwork = (matches[0].get("artworkUrl512") or
                       matches[0].get("artworkUrl100")) if matches else None
            if not artwork or urlparse(artwork).scheme != "https":
                print("No matching App Store artwork for", bundle)
                continue
            if artwork != current:
                app["iconURL"] = artwork
                dirty = True
                print("Found app icon for", bundle)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print("App icon lookup unavailable for", bundle, type(exc).__name__)
    if dirty:
        write(CATALOG, catalog)


def prune(args):
    """Remove deleted GitHub Release assets from this repository's app catalog.

    External hosted IPAs are not touched.
    """
    releases = json.loads(Path(args.releases_json).read_text(encoding="utf-8"))
    if not isinstance(releases, list):
        raise ValueError("Expected GitHub releases JSON array")
    valid_urls = {
        asset["browser_download_url"]
        for release in releases
        for asset in release.get("assets", [])
        if asset.get("browser_download_url")
    }
    release_prefix = "https://github.com/" + args.repository + "/releases/download/"
    catalog = load()
    removed = []
    for bundle, app in list(catalog.items()):
        old_versions = app.get("versions") or []
        keep_versions = [
            version for version in old_versions
            if not str(version.get("downloadURL", "")).startswith(release_prefix)
            or version["downloadURL"] in valid_urls
        ]
        if len(old_versions) > len(keep_versions):
            removed.append(app.get("name", bundle))
        if keep_versions:
            app["versions"] = keep_versions
        else:
            del catalog[bundle]
    write(CATALOG, catalog)
    print("Pruned missing release assets:", ", ".join(removed) or "none")


def render():
    universal_apps = []
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
        latest = versions[0]
        # Combined schema: version history for Feather, plus flat latest-version
        # fields for ESign and other AltStore-compatible signing apps.
        universal_apps.append({
            **app, "versions": versions,
            "version": latest["version"], "versionDate": latest["date"],
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
    # One AltStore-compatible source for Feather and ESign.
    unified_source = {
        **common,
        "sourceURL": "https://rbx9.github.io/ipa/",
        "apps": universal_apps,
        "news": []
    }
    # Legacy URLs stay working and contain the identical universal feed.
    for filename in ("source.json", "esign.json"):
        write(BASE / filename, unified_source)
    for directory in ("ipa", "esign"):
        write(BASE.parent / directory / "index.html", unified_source)
    print("Generated", len(universal_apps), "universal app entries")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("render")
    icon_parser = sub.add_parser("sync-icons")
    icon_parser.add_argument("--force-bundle", default="")
    prune_parser = sub.add_parser("prune")
    prune_parser.add_argument("--releases-json", required=True)
    prune_parser.add_argument("--repository", required=True)
    add_parser = sub.add_parser("add")
    add_parser.add_argument("--ipa", required=True)
    add_parser.add_argument("--url", required=True)
    add_parser.add_argument("--date", default="")
    add_parser.add_argument("--notes-file", default="")
    args = parser.parse_args()
    try:
        if args.command == "add":
            add(args)
        elif args.command == "prune":
            prune(args)
        elif args.command == "sync-icons":
            sync_icons(args)
        else:
            render()
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print("Source generation failed:", exc, file=sys.stderr)
        sys.exit(1)
