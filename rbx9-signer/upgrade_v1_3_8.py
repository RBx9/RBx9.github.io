#!/usr/bin/env python3
# RBx9 v1.3.8: reusable, content-deduplicated tweak storage and IPA sharing.
# Feather derivative, GPL-3.0-only. Preserve the original signing engine.
from pathlib import Path
import plistlib

root = Path("feather")
app = root / "Feather"

def edit(relative, old, new, count=1):
    p = root / relative
    s = p.read_text()
    n = s.count(old)
    if n != count:
        raise RuntimeError(f"{relative}: expected {count} anchors, found {n}: {old[:100]!r}")
    p.write_text(s.replace(old, new, count))

# Vault is embedded in an existing Swift target member so Xcode project file
# updates are unnecessary. Stored originals are not modified by the signer.
p = app / "Views/Signing/SigningTweaksView.swift"
s = p.read_text()
if "import NimbleViews\n" not in s:
    raise RuntimeError("Missing Quick Editor imports")
s = s.replace("import NimbleViews\n", "import NimbleViews\nimport CryptoKit\n", 1)
s = s.replace("@State private var _isAddingPresenting = false", '''@State private var _isAddingPresenting = false
    @StateObject private var _rbx9Vault = RBx9DylibStorage.shared
    @State private var _rbx9ShowStorageNotice = false
    @State private var _rbx9StorageNotice = ""''', 1)

# Append the stored library as a distinct section INSIDE the quick editor NBList.
anchor = ".safeAreaInset(edge: .bottom, spacing: 0)"
pos = s.index(anchor)
close = s.rfind("\n\t\t}\n", 0, pos)
if close < 0 or "NBList" not in s[:close]:
    raise RuntimeError("Quick Editor NBList closing anchor not found")
stored_section = """
            NBSection("Dylib Storage") {
                if _rbx9Vault.items.isEmpty {
                    Text("Saved dylibs appear here after your first import.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(_rbx9Vault.items) { item in
                        Button {
                            _rbx9SelectFromStorage(item.url)
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "shippingbox.fill")
                                    .foregroundStyle(Color.accentColor)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(item.name)
                                        .foregroundStyle(.primary)
                                        .lineLimit(2)
                                    Text(item.sizeLabel)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Image(systemName: _rbx9IsSelected(item.url) ? "checkmark.circle.fill" : "plus.circle")
                                    .foregroundStyle(Color.accentColor)
                            }
                        }
                        .buttonStyle(.borderless)
                        .disabled(_rbx9IsSelected(item.url))
                    }
                }
            }
"""
s = s[:close] + "\n" + stored_section + s[close:]

# Replace the original temporary-file import: save the original in the vault
# immediately, then pass its URL to the signing queue.
begin = s.index("\t\t.sheet(isPresented: $_isAddingPresenting) {")
# Upstream and RBx9 versions use different indentation for chained modifiers.
marker = ".animation(.smooth, value: options.injectionFiles)"
animation = s.index(marker, begin)
end = s.rfind("\n", begin, animation)
confirmation = s.find('.confirmationDialog("Dylib Changes Ready"', begin, animation)
if confirmation != -1:
    end = s.rfind("\n", begin, confirmation)
new_sheet = """        .sheet(isPresented: $_isAddingPresenting) {
            FileImporterRepresentableView(
                allowedContentTypes: [.dylib, .deb],
                allowsMultipleSelection: true,
                onDocumentsPicked: { urls in
                    for url in urls {
                        do {
                            switch try _rbx9Vault.importFile(url) {
                            case .added(let stored):
                                _rbx9SelectFromStorage(stored)
                            case .duplicate(let existing):
                                // No second copy. Reuse the previously saved copy.
                                _rbx9SelectFromStorage(existing)
                            case .nameConflict(let name):
                                _rbx9StorageNotice = "A different file named \\(name) is already saved. Remove or rename the old one first."
                                _rbx9ShowStorageNotice = true
                            }
                        } catch {
                            _rbx9StorageNotice = error.localizedDescription
                            _rbx9ShowStorageNotice = true
                        }
                    }
                }
            )
            .ignoresSafeArea()
        }
        .alert("Dylib Storage", isPresented: $_rbx9ShowStorageNotice) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(_rbx9StorageNotice)
        }"""
s = s[:begin] + new_sheet + s[end:]

# Remove from the CURRENT app's queue, but never delete the saved binary.
begin = s.index("\t\tButton(role: .destructive) {", s.index("private func _fileActions("))
end = s.index("\n\t\t} label: {", begin)
s = s[:begin] + """        Button(role: .destructive) {
            options.injectionFiles.removeAll { $0.standardizedFileURL == tweak.standardizedFileURL }
        """ + s[end:]

# Helpers live in SigningTweaksView's existing extension, and therefore don't
# require a custom initializer or changes to the swipe-to-edit sheet.
needle = "\n\t@ViewBuilder\n\tprivate func _file(tweak: URL) -> some View {"
if s.count(needle) != 1:
    raise RuntimeError("Quick Editor helper anchor mismatch")
helpers = """
    private func _rbx9IsSelected(_ url: URL) -> Bool {
        options.injectionFiles.contains {
            $0.standardizedFileURL == url.standardizedFileURL
            || $0.lastPathComponent.caseInsensitiveCompare(url.lastPathComponent) == .orderedSame
        }
    }

    private func _rbx9SelectFromStorage(_ url: URL) {
        guard !_rbx9IsSelected(url) else { return }
        options.injectionFiles.append(url)
        _showRBx9ApplyConfirmation = true
    }
"""
s = s.replace(needle, "\n" + helpers + needle, 1)

# A durable local vault; only user-initiated Remove in Settings deletes contents.
# Hash and case-insensitive filename checks prevent duplicate binaries and
# ambiguous same-name versions. Non-vault files remain untouched.
s += r"""

// MARK: - RBx9 local tweak library
struct RBx9StoredTweak: Identifiable {
    let url: URL
    let hash: String
    let bytes: Int64
    var id: String { url.standardizedFileURL.path }
    var name: String { url.lastPathComponent }
    var sizeLabel: String {
        ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
    }
}

final class RBx9DylibStorage: ObservableObject {
    static let shared = RBx9DylibStorage()
    @Published private(set) var items: [RBx9StoredTweak] = []

    enum ImportResult {
        case added(URL)
        case duplicate(URL)
        case nameConflict(String)
    }

    enum StorageFailure: LocalizedError {
        case unsupported
        case invalidFile
        var errorDescription: String? {
            switch self {
            case .unsupported: return "Only .dylib and .deb files can be stored."
            case .invalidFile: return "The selected tweak is not a valid regular file."
            }
        }
    }

    static var directory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("RBx9DylibStorage", isDirectory: true)
    }

    static func isStored(_ url: URL) -> Bool {
        url.standardizedFileURL.deletingLastPathComponent() == directory.standardizedFileURL
    }

    private init() { refresh() }

    private static func checksum(_ file: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: file)
        defer { handle.closeFile() }
        var digest = SHA256()
        while true {
            let chunk = handle.readData(ofLength: 512 * 1024)
            if chunk.isEmpty { break }
            digest.update(data: chunk)
        }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    func refresh() {
        let fm = FileManager.default
        try? fm.createDirectory(at: Self.directory, withIntermediateDirectories: true)
        let files = (try? fm.contentsOfDirectory(
            at: Self.directory,
            includingPropertiesForKeys: [.isRegularFileKey, .fileSizeKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        items = files.compactMap { file -> RBx9StoredTweak? in
            guard ["dylib", "deb"].contains(file.pathExtension.lowercased()),
                  (try? file.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true,
                  let digest = try? Self.checksum(file) else { return nil }
            let bytes = Int64((try? file.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0)
            return RBx9StoredTweak(url: file, hash: digest, bytes: bytes)
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    func importFile(_ original: URL) throws -> ImportResult {
        let ext = original.pathExtension.lowercased()
        guard ext == "dylib" || ext == "deb" else { throw StorageFailure.unsupported }
        let granted = original.startAccessingSecurityScopedResource()
        defer { if granted { original.stopAccessingSecurityScopedResource() } }
        guard (try? original.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true
        else { throw StorageFailure.invalidFile }
        let name = original.lastPathComponent
        let digest = try Self.checksum(original)
        // Refresh first to include imports from Files or previous app sessions.
        refresh()
        if let existing = items.first(where: { $0.hash == digest }) {
            return .duplicate(existing.url)
        }
        if items.contains(where: { $0.name.caseInsensitiveCompare(name) == .orderedSame }) {
            return .nameConflict(name)
        }
        let destination = Self.directory.appendingPathComponent(name, isDirectory: false)
        // Stored files are copies. Never move originals out of Files/AirDrop.
        try FileManager.default.copyItem(at: original, to: destination)
        refresh()
        return .added(destination)
    }

    func delete(_ item: RBx9StoredTweak) throws {
        guard Self.isStored(item.url) else { throw StorageFailure.invalidFile }
        try FileManager.default.removeItem(at: item.url)
        // Reset stale global signing queue references, without touching other apps.
        var settings = OptionsManager.shared.options
        settings.injectionFiles.removeAll { $0.standardizedFileURL == item.url.standardizedFileURL }
        OptionsManager.shared.options = settings
        refresh()
    }
}

struct RBx9DylibStorageView: View {
    @StateObject private var vault = RBx9DylibStorage.shared
    @State private var importing = false
    @State private var notice = ""
    @State private var showNotice = false
    @State private var pendingDelete: RBx9StoredTweak?

    var body: some View {
        List {
            Section {
                HStack(spacing: 12) {
                    Image(systemName: "shippingbox.fill")
                        .font(.system(size: 30))
                        .foregroundStyle(Color.accentColor)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Saved Tweak Library")
                            .font(.headline)
                        Text("\(vault.items.count) unique files · saved on this iPhone")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 8)
            } footer: {
                Text("Saved files are reusable in the Quick Editor when updating any app. Removing a tweak from a signing queue does not delete it from storage.")
            }
            Section("Stored Dylibs & Tweaks") {
                if vault.items.isEmpty {
                    Text("No files yet. Tap + to import .dylib or .deb files.")
                        .foregroundStyle(.secondary)
                }
                ForEach(vault.items) { item in
                    HStack(spacing: 12) {
                        Image(systemName: "doc.zipper")
                            .foregroundStyle(Color.accentColor)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.name).lineLimit(2)
                            Text(item.sizeLabel)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 4)
                        Button(role: .destructive) { pendingDelete = item } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Delete " + item.name)
                    }
                }
            }
        }
        .navigationTitle("Dylib Storage")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { importing = true } label: {
                    Image(systemName: "plus.circle.fill")
                }
                .accessibilityLabel("Import dylib")
            }
        }
        .onAppear { vault.refresh() }
        .sheet(isPresented: $importing) {
            FileImporterRepresentableView(
                allowedContentTypes: [.dylib, .deb],
                allowsMultipleSelection: true,
                onDocumentsPicked: { urls in
                    var added = 0
                    var duplicates = 0
                    var conflicts = 0
                    for url in urls {
                        do {
                            switch try vault.importFile(url) {
                            case .added: added += 1
                            case .duplicate: duplicates += 1
                            case .nameConflict: conflicts += 1
                            }
                        } catch {
                            notice = error.localizedDescription
                            showNotice = true
                        }
                    }
                    if !showNotice && (duplicates > 0 || conflicts > 0) {
                        notice = "\(added) saved, \(duplicates) duplicate files skipped, \(conflicts) filename conflicts skipped."
                        showNotice = true
                    }
                }
            )
            .ignoresSafeArea()
        }
        .alert("Dylib Storage", isPresented: $showNotice) {
            Button("OK", role: .cancel) {}
        } message: {
            Text(notice)
        }
        .confirmationDialog(
            "Delete stored file?",
            isPresented: Binding(
                get: { pendingDelete != nil },
                set: { if !$0 { pendingDelete = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Delete from Storage", role: .destructive) {
                guard let file = pendingDelete else { return }
                pendingDelete = nil
                do { try vault.delete(file) }
                catch {
                    notice = error.localizedDescription
                    showNotice = true
                }
            }
            Button("Cancel", role: .cancel) { pendingDelete = nil }
        } message: {
            Text("This deletes the saved copy. Previously signed apps and original files outside RBx9 are unchanged.")
        }
    }
}
"""
p.write_text(s)

# Update displayed RBx9 credit while preserving original GPL acknowledgments.
about = app / "Views/Settings/About/AboutView.swift"
about_content = about.read_text()
old_credit = 'Label("RBx9 · App customization", systemImage: "person.crop.circle")'
new_credit = 'Label("RBx9 · Developing and Modification", systemImage: "person.crop.circle")'
if about_content.count(old_credit) != 1:
    raise RuntimeError("RBx9 About credit anchor not found")
about.write_text(about_content.replace(old_credit, new_credit, 1))

# Link to storage from Settings as requested.
settings = app / "Views/Settings/SettingsView.swift"
ss = settings.read_text()
feature = '''NavigationLink(destination: ConfigurationView()) {'''
if ss.count(feature) != 1: raise RuntimeError("Settings features anchor mismatch")
ss = ss.replace(feature, '''NavigationLink(destination: RBx9DylibStorageView()) {
                        Label("Dylib Storage", systemImage: "shippingbox.fill")
                    }
                    ''' + feature, 1)
settings.write_text(ss)

# The original TweakHandler moves input binaries into a temporary signed app.
# For vault URLs COPY instead: moving would permanently empty the library.
tweak = app / "Utilities/Handlers/TweakHandler.swift"
ts = tweak.read_text()
anchor = "try _fileManager.moveFileIfNeeded(from: url, to: destinationURL)"
if ts.count(anchor) != 2: raise RuntimeError("Expected framework and direct dylib move locations")
start = ts.index("private func _handleDylib(at url: URL)")
location = ts.index(anchor, start)
ts = ts[:location] + '''if RBx9DylibStorage.isStored(url) {
            // Replace only the working copy; the library original stays intact.
            if _fileManager.fileExists(atPath: destinationURL.path) {
                try _fileManager.removeItem(at: destinationURL)
            }
            try _fileManager.copyItem(at: url, to: destinationURL)
        } else {
            try _fileManager.moveFileIfNeeded(from: url, to: destinationURL)
        }''' + ts[location + len(anchor):]
tweak.write_text(ts)

# Faster launch: retain the branded pulse but never hold navigation hostage.
launch = app / "FeatherApp.swift"
launch_code = launch.read_text()
for old, new in [
    ("rbx9ReduceMotion ? 450_000_000 : 2_350_000_000",
     "rbx9ReduceMotion ? 50_000_000 : 230_000_000"),
    ("rbx9ReduceMotion ? 0.12 : 0.42",
     "rbx9ReduceMotion ? 0.04 : 0.10"),
    (".spring(response: 0.72, dampingFraction: 0.82)",
     ".easeOut(duration: 0.13)"),
    ("Task.sleep(nanoseconds: 300_000_000)",
     "Task.sleep(nanoseconds: 70_000_000)"),
    (".easeInOut(duration: 1.18)",
     ".easeInOut(duration: 0.16)"),
    ("Task.sleep(nanoseconds: 1_100_000_000)",
     "Task.sleep(nanoseconds: 95_000_000)"),
    (".easeOut(duration: 0.33)",
     ".easeOut(duration: 0.08)")
]:
    if launch_code.count(old) != 1:
        raise RuntimeError("Startup speed anchor missing: " + old)
    launch_code = launch_code.replace(old, new, 1)
launch.write_text(launch_code)

# Apple supports owner document declarations, but iOS does NOT offer an
# IPA system-wide default-app switch. Register our own UTI identity for both
# IPA and TIPA, retaining the existing scene onOpenURL import handling.
plist = app / "Resources/Info.plist"
with plist.open("rb") as f: metadata = plistlib.load(f)
types = metadata.get("CFBundleDocumentTypes", [])
exports = metadata.get("UTExportedTypeDeclarations", [])
for record in types:
    values = record.get("LSItemContentTypes", [])
    record["LSItemContentTypes"] = [
        value.replace("thewonderofyou.Feather.ipa", "com.rbx9.signer.ipa")
             .replace("thewonderofyou.Feather.tipa", "com.rbx9.signer.tipa")
        for value in values
    ]
    record["CFBundleTypeRole"] = "Editor"
    if record.get("CFBundleTypeName") == "iOS Package Archive":
        record["CFBundleTypeName"] = "RBx9 IPA"
        record["LSHandlerRank"] = "Owner"
for record in exports:
    value = record.get("UTTypeIdentifier", "")
    record["UTTypeIdentifier"] = value.replace(
        "thewonderofyou.Feather.ipa", "com.rbx9.signer.ipa"
    ).replace(
        "thewonderofyou.Feather.tipa", "com.rbx9.signer.tipa"
    )
if not any("com.rbx9.signer.ipa" in x.get("LSItemContentTypes", []) for x in types):
    raise RuntimeError("IPA handler declaration missing")
metadata["LSSupportsOpeningDocumentsInPlace"] = True
with plist.open("wb") as f:
    plistlib.dump(metadata, f, sort_keys=False)

cfg = root / "Feather.xcconfig"
s = cfg.read_text()
if s.count("FEATHER_PROJECT_VERSION=1.3.7") != 1: raise RuntimeError("Unexpected old version")
cfg.write_text(s.replace("FEATHER_PROJECT_VERSION=1.3.7", "FEATHER_PROJECT_VERSION=1.3.8", 1))
print("RBx9 v1.3.8: Dylib Storage + Quick Editor reuse + SHA256 dedup + IPA document handling")
