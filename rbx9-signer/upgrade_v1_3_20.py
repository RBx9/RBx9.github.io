#!/usr/bin/env python3
# RBx9 Signer 1.3.20 private: version bump for the build that carries the
# installer diagnostics, Semi Local web installer and Dylib Storage delete hardening.
from pathlib import Path

config = Path("feather/Feather.xcconfig")
c = config.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.19") != 1:
    raise RuntimeError("v1.3.20: expected base 1.3.19")
config.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.19",
                            "FEATHER_PROJECT_VERSION=1.3.20", 1))
print("RBx9 v1.3.20 private: version bump")
