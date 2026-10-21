#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p debs
find debs -maxdepth 1 -type f -name '*.deb' -delete
count=0

while IFS='|' read -r url name expected || [[ -n "$url" ]]; do
  [[ -z "$url" || "$url" == \#* ]] && continue
  if [[ ! "$url" =~ ^https://github\.com/[^/]+/[^/]+/releases/download/[^/]+/[^/]+\.deb$ ]]; then
    echo "ERROR: Only GitHub Release .deb URLs are accepted: $url" >&2
    exit 1
  fi
  if [[ ! "$name" =~ ^[A-Za-z0-9._+-]+\.deb$ ]]; then
    echo "ERROR: Invalid package filename: $name" >&2
    exit 1
  fi
  if [[ ! "$expected" =~ ^[a-fA-F0-9]{64}$ ]]; then
    echo "ERROR: Missing or invalid SHA-256 for: $name" >&2
    exit 1
  fi
  echo "Fetching and verifying $name"
  curl --fail --show-error --silent --location --retry 3 --max-time 180 --output "debs/$name" "$url"
  echo "$expected  debs/$name" | sha256sum --check --status
  dpkg-deb -f "debs/$name" Package Version Architecture
  count=$((count + 1))
done < package-sources.txt

if [[ "$count" -eq 0 ]]; then
  echo "ERROR: Refusing to publish an empty Sileo repository." >&2
  exit 1
fi

dpkg-scanpackages --multiversion debs /dev/null > Packages
# Display RootHide compatibility in Sileo without altering the signed .deb.
# Override only the index Name field for this exact package and architecture.
python3 - <<'PY'
from pathlib import Path

p = Path("Packages")
stanzas = p.read_text().strip().split("\n\n")
for index, stanza in enumerate(stanzas):
    fields = stanza.splitlines()
    if "Package: local.duobar" in fields and "Architecture: iphoneos-arm64e" in fields:
        fields = ["Name: DuoBar (RootHide)" if line.startswith("Name: ") else line for line in fields]
        if not any(line.startswith("Name: ") for line in fields):
            fields.append("Name: DuoBar (RootHide)")
        # Sileo uses the depiction URL to show screenshots and richer details.
        fields = [line for line in fields if not line.startswith(("Depiction: ", "SileoDepiction: "))]
        fields = [
            "Description: DuoBar (RootHide) - circular battery/Wi-Fi/cellular indicator for iOS 16 with Personal Hotspot support, Control Center fixes and adjustable size."
            if line.startswith("Description: ") else line for line in fields
        ]
        fields.append("Depiction: https://rbx9.github.io/depictions/duobar-v2.html")
        fields.append("SileoDepiction: https://rbx9.github.io/depictions/duobar-v2.json")
        stanzas[index] = "\n".join(fields)
    elif "Package: local.duobar.rootless" in fields and "Architecture: iphoneos-arm64" in fields:
        # Keep Rootless metadata and depiction separate from the RootHide edition.
        fields = [line for line in fields if not line.startswith(("Name: ", "Depiction: ", "SileoDepiction: "))]
        fields = [
            "Description: DuoBar (Rootless) - iOS 16 Rootless edition with adjustable size. First release is pending device testing."
            if line.startswith("Description: ") else line for line in fields
        ]
        fields.append("Name: DuoBar (Rootless)")
        fields.append("Depiction: https://rbx9.github.io/depictions/duobar-rootless.html")
        fields.append("SileoDepiction: https://rbx9.github.io/depictions/duobar-rootless.json")
        stanzas[index] = "\n".join(fields)
p.write_text("\n\n".join(stanzas) + "\n", encoding="utf-8")
PY
if [[ ! -s Packages ]]; then
  echo "ERROR: Package index is empty." >&2
  exit 1
fi
gzip -n -9c Packages > Packages.gz
bzip2 -9c Packages > Packages.bz2
python3 scripts/make-release.py
echo "Repository generated with $count verified package(s)."
