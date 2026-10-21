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
if [[ ! -s Packages ]]; then
  echo "ERROR: Package index is empty." >&2
  exit 1
fi
gzip -n -9c Packages > Packages.gz
bzip2 -9c Packages > Packages.bz2
python3 scripts/make-release.py
echo "Repository generated with $count verified package(s)."
