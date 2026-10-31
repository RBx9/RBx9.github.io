#!/usr/bin/env python3
# RBx9 v1.3.5 — show Import from Files in the Sign tab's empty state.
# Source derived from Feather, distributed under GPL-3.0.
from pathlib import Path

root = Path("feather")
p = root / "Feather/Views/Library/LibraryView.swift"
s = p.read_text()

anchor = '''                            Text(_rbx9LibraryTab == 1
                                ? "Signed apps will appear here."
                                : "Import an IPA to get started.")
                                .font(.caption)
                                .foregroundStyle(.secondary)'''
replacement = anchor + '''
                            if _rbx9LibraryLayout == 0 || _rbx9LibraryTab == 0 {
                                Button {
                                    // Use the SAME IPA/TIPA document picker as Library +.
                                    // Avoid duplicate import logic or manual URL handling.
                                    _isImportingPresenting = true
                                } label: {
                                    Label("Import from Files", systemImage: "folder.badge.plus")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                        .foregroundStyle(Color.black)
                                        .padding(.horizontal, 18)
                                        .padding(.vertical, 10)
                                        .background(Color.accentColor, in: Capsule())
                                }
                                .buttonStyle(.borderless)
                                .accessibilityHint("Choose IPA or TIPA packages from Files.")
                                .padding(.top, 8)
                            }'''
if s.count(anchor) != 1:
    raise RuntimeError(f"Cannot find unique Sign-tab empty-state anchor ({s.count(anchor)} matches)")
s = s.replace(anchor, replacement, 1)

# Guard against accidentally showing this button in the Install tab or
# replacing the existing + menu and multi-IPA importer.
if s.count('Label("Import from Files", systemImage: "folder.badge.plus")') != 1:
    raise RuntimeError("Empty state button was not inserted once")
if 'allowedContentTypes:  [.ipa, .tipa]' not in s or '_importActions()' not in s:
    raise RuntimeError("Existing import flow missing")
p.write_text(s)

cfg = root / "Feather.xcconfig"
source = cfg.read_text()
old = "FEATHER_PROJECT_VERSION=1.3.4"
if source.count(old) != 1:
    raise RuntimeError("Unexpected previous version")
cfg.write_text(source.replace(old, "FEATHER_PROJECT_VERSION=1.3.5", 1))
print("RBx9 v1.3.5: small Import from Files button in empty Sign state")
