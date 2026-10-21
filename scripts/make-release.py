#!/usr/bin/env python3
"""Generate a flat APT repository Release file for Sileo."""
import hashlib
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

files = [Path("Packages"), Path("Packages.gz"), Path("Packages.bz2")]
lines = [
    "Origin: RBx9",
    "Label: RBx9 Repo",
    "Suite: stable",
    "Codename: ios",
    "Components: main",
    "Version: 1.0",
    "Architectures: iphoneos-arm64e iphoneos-arm64 all",
    "Description: RBx9's jailbreak tweak repository for Sileo",
    f"Date: {format_datetime(datetime.now(timezone.utc), usegmt=True)}",
]
for section, algorithm in (("MD5Sum", "md5"), ("SHA1", "sha1"), ("SHA256", "sha256"), ("SHA512", "sha512")):
    lines.append(section + ":")
    for path in files:
        payload = path.read_bytes()
        lines.append(f" {hashlib.new(algorithm, payload).hexdigest()} {len(payload):16} {path.name}")
Path("Release").write_text("\n".join(lines) + "\n", encoding="utf-8")
