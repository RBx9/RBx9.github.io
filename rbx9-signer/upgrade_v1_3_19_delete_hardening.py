#!/usr/bin/env python3
# RBx9 Signer 1.3.19 (no version bump): harden Dylib Storage deletion.
#  - No full-swipe on storage rows (the row vanished before the deferred delete
#    ran, which can crash the List).
#  - delete() tolerates an already-missing file, only rewrites the signing
#    options when they actually reference the file, and refreshes without
#    animation.
# Apply AFTER upgrade_v1_3_19_installer_diagnostics.py, to ./feather.
from pathlib import Path

p = Path("feather/Feather/Views/Signing/SigningTweaksView.swift")
s = p.read_text()

def once(old, new, label):
    global s
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"delete-hardening {label}: expected 1 match, found {n}")
    s = s.replace(old, new, 1)

once("""                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            pendingDelete = item""",
"""                    // No full swipe: a full swipe visually removes the row at once,
                    // but the file is only deleted after the confirmation sheet.
                    // That mismatch can crash the List.
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button {
                            pendingDelete = item""", "swipe")

once("""                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }
            }
        }
        .navigationTitle("Dylib Storage")""",
"""                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                        .tint(.red)
                    }
                }
            }
        }
        .navigationTitle("Dylib Storage")""", "tint")

once("""        guard Self.isStored(item.url) else { throw StorageFailure.invalidFile }
        try FileManager.default.removeItem(at: item.url)
        // Reset stale global signing queue references, without touching other apps.
        var settings = OptionsManager.shared.options
        settings.injectionFiles.removeAll { $0.standardizedFileURL == item.url.standardizedFileURL }
        OptionsManager.shared.options = settings
        refresh()
    }""",
"""        guard Self.isStored(item.url) else { throw StorageFailure.invalidFile }
        // A file that is already gone counts as deleted; never throw for it.
        if FileManager.default.fileExists(atPath: item.url.path) {
            try FileManager.default.removeItem(at: item.url)
        }
        // Reset stale global signing queue references, without touching other apps.
        let target = item.url.standardizedFileURL
        var settings = OptionsManager.shared.options
        let before = settings.injectionFiles.count
        settings.injectionFiles.removeAll { $0.standardizedFileURL == target }
        if settings.injectionFiles.count != before {
            OptionsManager.shared.options = settings
        }
        // Update the list without animation so no row diff runs mid-transition.
        var transaction = Transaction(animation: nil)
        transaction.disablesAnimations = true
        withTransaction(transaction) { refresh() }
    }""", "delete")

p.write_text(s)
print("RBx9 delete hardening applied")
