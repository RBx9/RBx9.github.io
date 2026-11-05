#!/usr/bin/env python3
# RBx9 Signer 1.3.15: online dylib source, verified downloads, and Quick Editor integration.
# Adds a separate Dylibs main tab. GPL-3.0-only Feather derivative.
from pathlib import Path

root = Path("feather")
swift = root / "Feather/Views/Signing/SigningTweaksView.swift"
src = swift.read_text()

def replace_once(old, new, why):
    global src
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{why}: expected one anchor, found {count}")
    src = src.replace(old,new,1)

replace_once(
    '''    @StateObject private var _rbx9Vault = RBx9DylibStorage.shared''',
    '''    @StateObject private var _rbx9Vault = RBx9DylibStorage.shared
    @State private var _rbx9OnlineDylibsPresented = false''',
    "quick editor remote library state"
)
replace_once(
    '''            NBSection("Dylib Storage") {''',
    '''            NBSection("RBx9 Source Dylibs") {
                Button {
                    _rbx9OnlineDylibsPresented = true
                } label: {
                    Label("Browse & Inject Source Dylibs", systemImage: "icloud.and.arrow.down")
                }
            }
            NBSection("Dylib Storage") {''',
    "quick editor entry point"
)
replace_once(
    '''        .sheet(isPresented: $_isAddingPresenting) {''',
    '''        .sheet(isPresented: $_rbx9OnlineDylibsPresented) {
            RBx9RemoteDylibLibraryView(onAdded: { stored in
                _rbx9SelectFromStorage(stored)
            })
        }
        .sheet(isPresented: $_isAddingPresenting) {''',
    "quick editor download and inject sheet"
)

src += r"""

// MARK: - Public RBx9 Dylib Source (separate from IPA and Sileo sources)
// Only SHA-256-verified, public GitHub Release .dylibs can enter local storage.
struct RBx9SourceDylib: Codable, Identifiable {
    let id: String
    let name: String
    let fileName: String
    let version: String
    let description: String
    let downloadURL: String
    let sha256: String
    let size: Int64
    let compatibility: String?
}
private struct RBx9SourceDylibIndex: Decodable {
    let schemaVersion: Int
    let libraries: [RBx9SourceDylib]
}

@MainActor
final class RBx9DylibSourceModel: ObservableObject {
    @Published private(set) var entries: [RBx9SourceDylib] = []
    @Published private(set) var downloading: Set<String> = []
    @Published private(set) var refreshing = false
    @Published var notice = ""
    @Published var showNotice = false
    private let feedURL = URL(string: "https://rbx9.github.io/ipa-source/dylibs.json")!

    private func validate(_ item: RBx9SourceDylib) -> Bool {
        guard item.id.range(of: "^[a-z0-9][a-z0-9._-]{0,80}$", options: .regularExpression) != nil,
              !item.name.isEmpty, item.name.count <= 120,
              item.version.count <= 50, item.description.count <= 2000,
              item.fileName.count <= 180,
              item.fileName == URL(fileURLWithPath: item.fileName).lastPathComponent,
              !item.fileName.contains(".."),
              item.fileName.pathExtension.lowercased() == "dylib",
              item.sha256.range(of: "^[0-9a-fA-F]{64}$", options: .regularExpression) != nil,
              item.size > 0, item.size <= 80 * 1024 * 1024,
              let url = URL(string: item.downloadURL),
              url.scheme == "https",
              url.host?.lowercased() == "github.com",
              url.path.hasPrefix("/RBx9/RBx9.github.io/releases/download/"),
              url.path.lowercased().hasSuffix(".dylib")
        else { return false }
        return true
    }

    func refresh() async {
        guard !refreshing else { return }
        refreshing = true
        defer { refreshing = false }
        do {
            var req = URLRequest(url: feedURL)
            req.cachePolicy = .reloadIgnoringLocalCacheData
            req.timeoutInterval = 25
            let (data, response) = try await URLSession.shared.data(for: req)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw NSError(domain: "RBx9 Dylib Source", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "Could not load the dylib catalog."])
            }
            guard data.count <= 1_048_576 else {
                throw NSError(domain: "RBx9 Dylib Source", code: 2,
                              userInfo: [NSLocalizedDescriptionKey: "Dylib catalog is too large."])
            }
            let index = try JSONDecoder().decode(RBx9SourceDylibIndex.self, from: data)
            guard index.schemaVersion == 1, index.libraries.count <= 500 else {
                throw NSError(domain: "RBx9 Dylib Source", code: 3,
                              userInfo: [NSLocalizedDescriptionKey: "Unsupported source catalog format."])
            }
            // Reject malformed or duplicate IDs rather than displaying unsafe downloads.
            let valid = index.libraries.filter(validate)
            guard valid.count == index.libraries.count,
                  Set(valid.map(\.id)).count == valid.count else {
                throw NSError(domain: "RBx9 Dylib Source", code: 4,
                              userInfo: [NSLocalizedDescriptionKey: "The source contains invalid dylib metadata."])
            }
            entries = valid.sorted {
                $0.name.localizedStandardCompare($1.name) == .orderedAscending
            }
        } catch {
            notice = "Could not refresh the Dylib Source: " + error.localizedDescription
            showNotice = true
        }
    }

    private func checksum(_ url: URL) throws -> String {
        let stream = try FileHandle(forReadingFrom: url)
        defer { stream.closeFile() }
        var hash = SHA256()
        while true {
            let chunk = stream.readData(ofLength: 512 * 1024)
            if chunk.isEmpty { break }
            hash.update(data: chunk)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private func alternateName(_ item: RBx9SourceDylib) -> String {
        // Preserve existing saved versions; never overwrite a user's original.
        let stem = URL(fileURLWithPath: item.fileName).deletingPathExtension().lastPathComponent
        let suffix = item.version.replacingOccurrences(
            of: "[^A-Za-z0-9._-]", with: "-", options: .regularExpression)
        let trimmed = String(stem.prefix(90))
        return trimmed + "-v" + String(suffix.prefix(30)) + "-" +
               String(item.sha256.prefix(8)) + ".dylib"
    }

    func download(_ item: RBx9SourceDylib) async -> URL? {
        guard validate(item), !downloading.contains(item.id) else { return nil }
        downloading.insert(item.id)
        defer { downloading.remove(item.id) }
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("RBx9Source-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        do {
            let url = URL(string: item.downloadURL)!
            let (fileURL, response) = try await URLSession.shared.download(from: url)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw NSError(domain: "RBx9 Dylib Source", code: 5,
                              userInfo: [NSLocalizedDescriptionKey: "The GitHub download failed."])
            }
            let bytes = Int64((try? fileURL.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? -1)
            guard bytes == item.size else {
                throw NSError(domain: "RBx9 Dylib Source", code: 6,
                              userInfo: [NSLocalizedDescriptionKey: "Download size mismatch; file not imported."])
            }
            guard try checksum(fileURL).caseInsensitiveCompare(item.sha256) == .orderedSame else {
                throw NSError(domain: "RBx9 Dylib Source", code: 7,
                              userInfo: [NSLocalizedDescriptionKey: "SHA-256 checksum mismatch. File was rejected."])
            }
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            var staged = folder.appendingPathComponent(item.fileName)
            try FileManager.default.copyItem(at: fileURL, to: staged)
            let vault = RBx9DylibStorage.shared
            var result = try vault.importFile(staged)
            if case .nameConflict = result {
                staged = folder.appendingPathComponent(alternateName(item))
                try FileManager.default.copyItem(at: fileURL, to: staged)
                result = try vault.importFile(staged)
            }
            switch result {
            case .added(let stored):
                notice = "Downloaded \(item.name) into Dylib Storage."
                showNotice = true
                return stored
            case .duplicate(let stored):
                notice = "Already in Dylib Storage. Reusing the existing copy."
                showNotice = true
                return stored
            case .nameConflict:
                throw NSError(domain: "RBx9 Dylib Source", code: 8,
                              userInfo: [NSLocalizedDescriptionKey: "A filename conflict prevented import."])
            }
        } catch {
            notice = "Could not download \(item.name): " + error.localizedDescription
            showNotice = true
            return nil
        }
    }
}

struct RBx9RemoteDylibLibraryView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var source = RBx9DylibSourceModel()
    // When opened from the Quick Editor, immediately enqueue the verified file
    // for the selected IPA; signing and installation remain manual actions.
    var onAdded: ((URL) -> Void)? = nil

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 12) {
                        Image(systemName: "shippingbox.circle.fill")
                            .font(.system(size: 30))
                            .foregroundStyle(.cyan)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("RBx9 Source Dylibs").font(.headline)
                            Text("Verified downloads · saved in Dylib Storage")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 7)
                    Text("Download from your RBx9 source. The tweak remains stored for future IPA updates.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if source.entries.isEmpty && !source.refreshing {
                    Section {
                        Text("No published dylibs yet. Add one using RBx9 Source Manager.")
                            .foregroundStyle(.secondary)
                    }
                }
                Section("Available Dylibs") {
                    ForEach(source.entries) { item in
                        VStack(alignment: .leading, spacing: 7) {
                            HStack {
                                Text(item.name).font(.headline)
                                Spacer(minLength: 4)
                                Text("v" + item.version)
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                            Text(item.description).font(.footnote).foregroundStyle(.secondary)
                            HStack {
                                if let compatibility = item.compatibility, !compatibility.isEmpty {
                                    Text(compatibility).font(.caption2).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text(ByteCountFormatter.string(fromByteCount: item.size, countStyle: .file))
                                    .font(.caption2).foregroundStyle(.secondary)
                            }
                            Button {
                                Task {
                                    if let stored = await source.download(item) {
                                        onAdded?(stored)
                                    }
                                }
                            } label: {
                                Label(onAdded == nil ? "Download to Storage" : "Download & Add to IPA",
                                      systemImage: onAdded == nil ? "icloud.and.arrow.down" : "plus.app")
                            }
                            .disabled(source.downloading.contains(item.id))
                            if source.downloading.contains(item.id) {
                                ProgressView("Downloading and verifying…")
                            }
                        }
                        .padding(.vertical, 6)
                    }
                }
            }
            .navigationTitle("Source Dylibs")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if onAdded != nil {
                        Button("Done") { dismiss() }
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await source.refresh() }
                    } label: { Image(systemName: "arrow.clockwise") }
                    .disabled(source.refreshing)
                }
            }
            .refreshable { await source.refresh() }
            .task { await source.refresh() }
            .alert("RBx9 Dylib Source", isPresented: $source.showNotice) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(source.notice)
            }
        }
    }
}
"""

swift.write_text(src)
tabs = root / "Feather/Views/TabView/TabEnum.swift"
tab = tabs.read_text()
def replace_tab(old,new,purpose):
    global tab
    if tab.count(old) != 1:
        raise RuntimeError(f"{purpose}: expected 1 anchor, got {tab.count(old)}")
    tab = tab.replace(old,new,1)

replace_tab("\tcase library\n", "\tcase library\n    case dylibs\n", "add tab case")
replace_tab("case .library: \t\treturn .localized(\"Library\")",
            'case .library: \t\treturn .localized("Library")\n        case .dylibs:       return "Dylibs"', "title")
replace_tab('case .library: \t\treturn "square.grid.2x2"',
            'case .library: \t\treturn "square.grid.2x2"\n        case .dylibs:       return "shippingbox.fill"', "tab icon")
replace_tab('case .library: LibraryView()',
            'case .library: LibraryView()\n        case .dylibs: RBx9RemoteDylibLibraryView()', "tab destination")
replace_tab('''\t\t\t.library,
\t\t\t.settings''',
            '''\t\t\t.library,
            .dylibs,
\t\t\t.settings''', "visible tab list")
tabs.write_text(tab)

cfg=root/"Feather.xcconfig"
content=cfg.read_text()
if content.count("FEATHER_PROJECT_VERSION=1.3.14") != 1:
    raise RuntimeError("Expected v1.3.14 patch base")
cfg.write_text(content.replace("FEATHER_PROJECT_VERSION=1.3.14","FEATHER_PROJECT_VERSION=1.3.15",1))

print("RBx9 v1.3.15: Dylibs tab, verified source downloads, Quick Editor injection integration")
