#!/usr/bin/env python3
# RBx9 Signer v1.3.12 — clean Dylib Storage row interactions.
# Swipe LEFT to delete (with confirmation); long-press to Export / Rename.
# Based on Feather GPL-3.0. Applied AFTER upgrade_v1_3_11.py.
from pathlib import Path

root = Path("feather")
view = root / "Feather/Views/Signing/SigningTweaksView.swift"
src = view.read_text()

old = '''                        Spacer(minLength: 4)
                        RBx9StoredTweakExportButton(fileURL: item.url)
                        Button { beginRename(item) } label: {
                            Image(systemName: "pencil")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Rename " + item.name)
                        Button(role: .destructive) { pendingDelete = item } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Delete " + item.name)
                    }
                    .contextMenu {
                        ShareLink(item: item.url) {
                            Label("Export", systemImage: "square.and.arrow.up")
                        }
                        Button { beginRename(item) } label: {
                            Label("Rename", systemImage: "pencil")
                        }
                        Button(role: .destructive) { pendingDelete = item } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                    .swipeActions(edge: .leading, allowsFullSwipe: false) {
                        Button { beginRename(item) } label: {
                            Label("Rename", systemImage: "pencil")
                        }
                        .tint(.blue)
                    }'''

new = '''                        Spacer(minLength: 4)
                    }
                    .contentShape(Rectangle())
                    // Long-press the file for export or rename. No visible row buttons.
                    .contextMenu {
                        ShareLink(item: item.url) {
                            Label("Share / Export", systemImage: "square.and.arrow.up")
                        }
                        Button { beginRename(item) } label: {
                            Label("Rename", systemImage: "pencil")
                        }
                    }
                    // Swipe left to delete. Keep the existing confirmation dialog
                    // so an accidental swipe never deletes stored tweak binaries.
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            pendingDelete = item
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }'''

if src.count(old) != 1:
    raise RuntimeError(f"Expected one complete legacy action row; found {src.count(old)}")
src = src.replace(old, new, 1)

# Eliminate the now-unused inline share control itself (not just its call).
helper = '''// MARK: - Native iOS file export from stored tweak URL
private struct RBx9StoredTweakExportButton: View {
    let fileURL: URL
    var body: some View {
        ShareLink(item: fileURL) {
            Image(systemName: "square.and.arrow.up")
        }
        .buttonStyle(.borderless)
        .accessibilityLabel("Export " + fileURL.lastPathComponent)
    }
}
'''
if src.count(helper) != 1:
    raise RuntimeError("Expected one deprecated inline Export button view")
src = src.replace(helper, "", 1)

for expected in [
    '.contextMenu {',
    'Label("Share / Export", systemImage: "square.and.arrow.up")',
    'Label("Rename", systemImage: "pencil")',
    '.swipeActions(edge: .trailing, allowsFullSwipe: true)',
    'pendingDelete = item',
    'Button("Delete from Storage", role: .destructive)',
    'RBx9RenameSheet(item: item, vault: vault)',
]:
    if expected not in src:
        raise RuntimeError("Storage interaction disappeared: " + expected)

if "RBx9StoredTweakExportButton" in src:
    raise RuntimeError("Inline export control is still present")
if '.swipeActions(edge: .leading' in src:
    raise RuntimeError("Old swipe-to-rename action is still present")
# The first row's action layout no longer has a visible button.
row = src.split('ForEach(vault.items) { item in', 1)[1].split('.contentShape(Rectangle())', 1)[0]
if "Button" in row or "ShareLink" in row:
    raise RuntimeError("Unexpected visible row controls remain")

view.write_text(src)

cfg = root / "Feather.xcconfig"
contents = cfg.read_text()
if contents.count("FEATHER_PROJECT_VERSION=1.3.11") != 1:
    raise RuntimeError("Expected v1.3.11 patch base")
cfg.write_text(contents.replace("FEATHER_PROJECT_VERSION=1.3.11",
                                "FEATHER_PROJECT_VERSION=1.3.12", 1))
print("RBx9 v1.3.12: streamlined storage rows, left-swipe Delete, long-press Export/Rename")
