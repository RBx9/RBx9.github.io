#!/usr/bin/env python3
"""Generate a flat APT repository Release file for Sileo."""
import hashlib
import json
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

files = [Path("Packages"), Path("Packages.gz"), Path("Packages.bz2")]
settings_path = Path("sileo-settings.json")
settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
release_description = settings.get('description') or "RBx9's jailbreak tweak repository for Sileo"
lines = [
    "Origin: RBx9",
    f"Label: {settings.get('name', 'RBx9 Repo')}",
    "Suite: stable",
    "Codename: ios",
    "Components: main",
    "Version: 1.0",
    "Architectures: iphoneos-arm iphoneos-arm64 iphoneos-arm64e all",
    f"Description: {release_description}",
    f"Date: {format_datetime(datetime.now(timezone.utc), usegmt=True)}",
]
for section, algorithm in (("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256"), ("SHA512", "sha512")):
    lines.append(section + ":")
    for path in files:
        payload = path.read_bytes()
        lines.append(f" {hashlib.new(algorithm, payload).hexdigest()} {len(payload):16} {path.name}")
Path("Release").write_text("\n".join(lines) + "\n", encoding="utf-8")
