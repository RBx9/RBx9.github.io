#!/usr/bin/env python3
"""Package user-provided libraries into a modifiable IPA and verify load paths."""
import argparse
import os
import plistlib
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

import lief

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ipa", required=True)
    p.add_argument("--library", action="append", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(a.ipa) as z:
            entries = z.infolist()
            if sum(x.file_size for x in entries) > 4 * 1024**3:
                raise ValueError("IPA contents too large")
            for entry in entries:
                if entry.filename.startswith("/") or ".." in Path(entry.filename).parts:
                    raise ValueError("Unsafe ZIP member")
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsupported symbolic link")
            z.extractall(tmp)
        payload = Path(tmp) / "Payload"
        apps = list(payload.glob("*.app"))
        if len(apps) != 1:
            raise ValueError("Expected exactly one app")
        app = apps[0]
        info = plistlib.loads((app / "Info.plist").read_bytes())
        exe = app / info["CFBundleExecutable"]
        if not exe.is_file():
            raise ValueError("Missing application executable")
        main_macho = lief.MachO.parse(exe)
        if not main_macho:
            raise ValueError("App is not a Mach-O binary")
        binaries = [main_macho.at(i) for i in range(main_macho.size)]
        frameworks = app / "Frameworks"
        frameworks.mkdir(exist_ok=True)
        names = set()
        for library in a.library:
            source = Path(library)
            name = source.name
            if not re.fullmatch(r"[A-Za-z0-9._+-]+\\.dylib", name, re.I):
                raise ValueError("Invalid library name")
            if name.lower() in names:
                raise ValueError("Duplicate library")
            names.add(name.lower())
            if not lief.MachO.parse(source):
                raise ValueError("Library is not a Mach-O dylib")
            target = frameworks / name
            if target.exists():
                raise ValueError("Library already present")
            shutil.copy2(source, target)
            os.chmod(target, 0o755)
            load_path = "@executable_path/Frameworks/" + name
            for binary in binaries:
                if binary.add_library(load_path) is None:
                    raise ValueError("Could not register library")
        for binary in binaries:
            binary.remove_signature()
        main_macho.write(str(exe))
        for name in names:
            assert all(b.find_library("@executable_path/Frameworks/" + name)
                       for b in [lief.MachO.parse(exe).at(i) for i in range(main_macho.size)])
        shutil.rmtree(app / "_CodeSignature", ignore_errors=True)
        with zipfile.ZipFile(a.output, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for item in Path(tmp).rglob("*"):
                if item.is_file():
                    z.write(item, arcname=item.relative_to(tmp))
        with zipfile.ZipFile(a.output) as z:
            if z.testzip():
                raise ValueError("Output archive verification failed")
    print("Created validated IPA. Sign with a compatible app signing certificate.")

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("Package preparation failed:", error, file=sys.stderr)
        sys.exit(1)
