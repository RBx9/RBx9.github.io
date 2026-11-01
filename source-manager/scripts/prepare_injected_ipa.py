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
import traceback

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
        names = []
        names_lower = set()
        for library in a.library:
            source = Path(library)
            name = source.name
            if not re.fullmatch(r"[A-Za-z0-9._+-]+\.dylib", name, re.I):
                raise ValueError("Invalid library name")
            if name.lower() in names_lower:
                raise ValueError("Duplicate library")
            names.append(name)
            names_lower.add(name.lower())
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
        verified = lief.MachO.parse(exe)
        if not verified or verified.size != main_macho.size:
            raise ValueError("Output Mach-O architecture parsing failed")
        for name in names:
            expected_path = "@executable_path/Frameworks/" + name
            for index in range(verified.size):
                binary = verified.at(index)
                present = binary.find_library(expected_path)
                print("Check injected load command", expected_path, "slice", index,
                      "found", bool(present), flush=True)
                if not present:
                    available = [lib.name for lib in binary.libraries]
                    raise ValueError(
                        f"Injected load command missing after writing: {expected_path}; "
                        f"available libraries: {available}"
                    )
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
        print("Package preparation failed:", repr(error), file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
