#!/usr/bin/env python3
# RBx9 Signer v1.3.9 - Rename saved dylibs safely without losing queue references.
# GPL-3.0-only derivative of Feather. Applied AFTER upgrade_v1_3_8.py.
from pathlib import Path

root = Path("feather")
app = root / "Feather"
swift = app / "Views/Signing/SigningTweaksView.swift"
src = swift.read_text()

def replace_once(old, new, label):
    global src
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"v1.3.9: {label} anchor count {count}, expected 1")
    src = src.replace(old, new, 1)

# Distinguish an unsafe path, bad filename or existing file instead of
# overwriting the user's stored original. We keep the existing extension.
replace_once(
    """        case unsupported
        case invalidFile
        var errorDescription: String? {""",
    """        case unsupported
        case invalidFile
        case invalidName
        case fileAlreadyExists(String)
        var errorDescription: String? {""",
    "vault error enum"
)
replace_once(
    """            case .unsupported: return "Only .dylib and .deb files can be stored."
            case .invalidFile: return "The selected tweak is not a valid regular file."
            }""",
    """            case .unsupported: return "Only .dylib and .deb files can be stored."
            case .invalidFile: return "The selected tweak is not a valid regular file."
            case .invalidName: return "Enter a filename without slashes, colons, or control characters."
            case .fileAlreadyExists(let name): return "A stored file named \\(name) already exists. Choose a different name."
            }""",
    "vault errors"
)

# Rename only files owned by RBx9 local storage. Never touch the binary
# contents or modify the .dylib/.deb extension. Update saved signing queue URLs.
replace_once(
    """    func delete(_ item: RBx9StoredTweak) throws {""",
    r'''    @discardableResult
    func rename(_ item: RBx9StoredTweak, to requestedName: String) throws -> URL {
        let fm = FileManager.default
        let original = item.url.standardizedFileURL
        guard Self.isStored(original),
              ["dylib", "deb"].contains(original.pathExtension.lowercased()),
              (try? original.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey]))?.isRegularFile == true
        else { throw StorageFailure.invalidFile }

        var base = requestedName.trimmingCharacters(in: .whitespacesAndNewlines)
        let suffix = "." + original.pathExtension.lowercased()
        // Accept either "MyTweak" or "MyTweak.dylib" without duplicating the extension.
        if base.lowercased().hasSuffix(suffix) {
            base = String(base.dropLast(suffix.count)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let unsafe = CharacterSet(charactersIn: "/\\:")
            .union(.controlCharacters)
            .union(.newlines)
        guard !base.isEmpty, base != ".", base != "..",
              !base.hasPrefix("."),
              base.rangeOfCharacter(from: unsafe) == nil,
              base.utf8.count <= 200 else { throw StorageFailure.invalidName }

        let name = base + suffix
        if name == original.lastPathComponent { return original }
        refresh()
        guard !items.contains(where: {
            $0.url.standardizedFileURL != original
                && $0.name.caseInsensitiveCompare(name) == .orderedSame
        }) else { throw StorageFailure.fileAlreadyExists(name) }

        let destination = Self.directory.appendingPathComponent(name, isDirectory: false)
        // Compare using a unique staging path for case-only renames on APFS.
        let caseOnly = name.caseInsensitiveCompare(original.lastPathComponent) == .orderedSame
        if !caseOnly && fm.fileExists(atPath: destination.path) {
            throw StorageFailure.fileAlreadyExists(name)
        }

        if caseOnly {
            let intermediate = Self.directory.appendingPathComponent("rbx9-rename-" + UUID().uuidString + suffix)
            try fm.moveItem(at: original, to: intermediate)
            do {
                try fm.moveItem(at: intermediate, to: destination)
            } catch {
                try? fm.moveItem(at: intermediate, to: original)
                throw error
            }
        } else {
            try fm.moveItem(at: original, to: destination)
        }

        // Saved/global signing options may already refer to this file.
        // Remap rather than remove so future re-signs use the renamed tweak.
        var current = OptionsManager.shared.options
        current.injectionFiles = current.injectionFiles.map {
            $0.standardizedFileURL == original ? destination : $0
        }
        OptionsManager.shared.options = current
        refresh()
        return destination
    }

    func delete(_ item: RBx9StoredTweak) throws {''',
    "rename API"
)

# Storage screen state and context actions.
replace_once(
    """    @State private var pendingDelete: RBx9StoredTweak?

    var body: some View {""",
    """    @State private var pendingDelete: RBx9StoredTweak?
    @State private var pendingRename: RBx9StoredTweak?

    var body: some View {""",
    "rename state"
)
replace_once(
    '''                        Spacer(minLength: 4)
                        Button(role: .destructive) { pendingDelete = item } label: {
                            Image(systemName: "trash")
                        }''',
    '''                        Spacer(minLength: 4)
                        Button { beginRename(item) } label: {
                            Image(systemName: "pencil")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Rename " + item.name)
                        Button(role: .destructive) { pendingDelete = item } label: {
                            Image(systemName: "trash")
                        }''',
    "rename button"
)

# Use a sheet instead of an alert TextField to support nontrivial filenames,
# better keyboard behavior and a clear, uneditable extension indication.
replace_once(
    '''        .onAppear { vault.refresh() }
        .sheet(isPresented: $importing) {''',
    r'''        .onAppear { vault.refresh() }
        .sheet(item: $pendingRename) { item in
            RBx9RenameSheet(item: item, vault: vault) { message in
                pendingRename = nil
                notice = message
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                    showNotice = true
                }
            }
            .presentationDetents([.medium])
        }
        .sheet(isPresented: $importing) {''',
    "rename sheet"
)

# Add an accessible context menu and swipe gesture for the same action.
replace_once(
    '''                        .accessibilityLabel("Delete " + item.name)
                    }
                }
            }
        }
        .navigationTitle("Dylib Storage")''',
    '''                        .accessibilityLabel("Delete " + item.name)
                    }
                    .contextMenu {
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
                    }
                }
            }
        }
        .navigationTitle("Dylib Storage")''',
    "rename context menu and swipe"
)

# Tiny helper keeps entry point behavior identical for button/swipe/menu.
needle = '''struct RBx9DylibStorageView: View {'''
if src.count(needle) != 1:
    raise RuntimeError("Storage view declaration missing")
# View ends immediately before a comment that starts non-vault code? The original
# generated file declares storage view at its end, so append an extension.
src += r'''

private extension RBx9DylibStorageView {
    func beginRename(_ item: RBx9StoredTweak) {
        pendingRename = item
    }
}
'''

# Keep the rename form in its own SwiftUI View so the storage List can
# compile without the type check explosion caused by nested sheet + form.
src += r'''
private struct RBx9RenameSheet: View {
    @Environment(\.dismiss) private var dismiss
    let item: RBx9StoredTweak
    let vault: RBx9DylibStorage
    let onError: (String) -> Void
    @State private var newName: String

    init(item: RBx9StoredTweak, vault: RBx9DylibStorage, onError: @escaping (String) -> Void) {
        self.item = item
        self.vault = vault
        self.onError = onError
        _newName = State(initialValue: item.url.deletingPathExtension().lastPathComponent)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack(spacing: 6) {
                        TextField("Name", text: $newName)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                        Text(verbatim: "." + item.url.pathExtension.lowercased())
                            .foregroundStyle(.secondary)
                    }
                } header: {
                    Text("Filename")
                } footer: {
                    Text("The saved binary is not modified. The file extension stays unchanged.")
                }
            }
            .navigationTitle("Rename Dylib")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        do {
                            try vault.rename(item, to: newName)
                            dismiss()
                        } catch {
                            onError(error.localizedDescription)
                            dismiss()
                        }
                    }
                    .fontWeight(.semibold)
                    .disabled(newName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}
'''

# Make former queued references to renamed paths visible when switching to
# Quick Editor in same scene: selections remapped in OptionsManager on rename.
swift.write_text(src)

config = root / "Feather.xcconfig"
cfg = config.read_text()
old = "FEATHER_PROJECT_VERSION=1.3.8"
if cfg.count(old) != 1: raise RuntimeError("Expected v1.3.8 app version")
config.write_text(cfg.replace(old, "FEATHER_PROJECT_VERSION=1.3.9", 1))
print("RBx9 1.3.9: rename stored dylibs, preserve extensions, reject conflicts and update queue paths")
