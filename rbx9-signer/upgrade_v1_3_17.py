#!/usr/bin/env python3
# RBx9 Signer 1.3.17 private test: deferred vault deletion and single-line action labels.
# Applied after upgrade_v1_3_16.py. Does not alter the original IPA or source catalogs.
from pathlib import Path

root = Path("feather")
swift = root / "Feather/Views/Signing/SigningTweaksView.swift"
src = swift.read_text()

def once(old: str, new: str, what: str):
    global src
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"v1.3.17: {what}: expected exactly one match; got {count}")
    src = src.replace(old, new, 1)

# Keep the confirmation content alive while its sheet is being dismissed.
# Mutating an @Published list that drives the underlying row during dismissal
# can invalidate the row/selection still held by SwiftUI. Defer actual disk
# deletion, queue cleanup and refresh until the sheet has fully disappeared.
once(
    "    @State private var pendingDelete: RBx9StoredTweak?",
    """    @State private var pendingDelete: RBx9StoredTweak?
    @State private var confirmedDeletionAfterDismiss: RBx9StoredTweak?""",
    "add deferred-delete state"
)
once(
    r'''        .sheet(item: $pendingDelete) { file in
            RBx9DeleteTweakSheet(file: file) {
                pendingDelete = nil
                do { try vault.delete(file) }
                catch {
                    notice = error.localizedDescription
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        showNotice = true
                    }
                }
            }
            .presentationDetents([.height(328)])
            .presentationDragIndicator(.visible)
        }''',
    r'''        .sheet(item: $pendingDelete, onDismiss: {
            guard let file = confirmedDeletionAfterDismiss else { return }
            confirmedDeletionAfterDismiss = nil
            do {
                try vault.delete(file)
            } catch {
                vault.refresh()
                notice = "Could not delete " + file.name + ": " + error.localizedDescription
                showNotice = true
            }
        }) { file in
            RBx9DeleteTweakSheet(file: file) {
                // Dismiss first; deletion and @Published refresh occur in onDismiss.
                confirmedDeletionAfterDismiss = file
                pendingDelete = nil
            }
            .presentationDetents([.height(328)])
            .presentationDragIndicator(.visible)
        }''',
    "defer destructive mutation to sheet onDismiss"
)
once(
    r'''            Button(role: .destructive) {
                dismiss()
                onDelete()
            } label: {
                Label("Delete File", systemImage: "trash")''',
    r'''            Button(role: .destructive) {
                // Parent clears the sheet binding; do not call dismiss twice.
                onDelete()
            } label: {
                Label("Delete File", systemImage: "trash")''',
    "avoid double dismissal"
)

# Explicit horizontal labels prevent SwiftUI from breaking 'Downloaded'
# into 'Down-' and 'loaded' on smaller iPhone displays.
once(
    r'''                Label("Downloaded", systemImage: "checkmark.circle.fill")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.green)
                    .frame(width: 101)
                    .accessibilityLabel(item.name + " downloaded")''',
    r'''                HStack(spacing: 5) {
                    Image(systemName: "checkmark.circle.fill")
                    Text("Downloaded")
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.green)
                .frame(width: 116, alignment: .trailing)
                .accessibilityLabel(item.name + " downloaded")''',
    "single-line downloaded badge"
)
once(
    r'''                Label("Download", systemImage: "arrow.down.to.line")
                    .font(.caption2.weight(.semibold))
                    .frame(width: 96)''',
    r'''                HStack(spacing: 5) {
                    Image(systemName: "arrow.down.to.line")
                    Text("Download")
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
                .font(.system(size: 11, weight: .semibold))
                .frame(width: 104)''',
    "single-line Download button"
)
once(
    r'''                        Text("Downloaded")
                            .font(.system(size: 10))
                    }
                    .frame(width: 98)''',
    r'''                        Text("Downloaded")
                            .font(.system(size: 10))
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    .frame(width: 112)''',
    "single-line downloaded label in Quick Editor"
)
once(
    r'''                Text("Downloading")
                    .font(.caption2)''',
    r'''                Text("Downloading")
                    .font(.caption2)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)''',
    "single-line loading label"
)

assert "confirmedDeletionAfterDismiss = file" in src
assert "sheet(item: $pendingDelete, onDismiss:" in src
assert "Label(\"Downloaded\", systemImage:" not in src
swift.write_text(src)
config = root / "Feather.xcconfig"
c = config.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.16") != 1:
    raise RuntimeError("Expected base 1.3.16")
config.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.16", "FEATHER_PROJECT_VERSION=1.3.17"))
print("RBx9 v1.3.17 private: delete after sheet dismiss; single-line download labels")
