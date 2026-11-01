import Foundation
import SwiftUI
import CryptoKit

struct SavedDylib: Identifiable {
    let url: URL
    let hash: String
    let byteCount: Int64
    var id: String { hash }
    var name: String { url.lastPathComponent }
}

/// Shared only when BOTH apps have the matching App Group entitlement in their
/// provisioning profiles. Without it, iOS sandboxing forbids direct sharing;
/// the compatible local Documents folder remains available through Files import.
@MainActor
final class RBx9DylibVault: ObservableObject {
    static let shared = RBx9DylibVault()
    static let appGroupID = "group.com.rbx9.shared"
    @Published private(set) var items: [SavedDylib] = []
    @Published private(set) var sharedContainerAvailable = false

    var root: URL {
        if let group = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: Self.appGroupID) {
            return group.appendingPathComponent("RBx9DylibStorage", isDirectory:true)
        }
        return FileManager.default.urls(for:.documentDirectory,in:.userDomainMask)[0]
            .appendingPathComponent("RBx9DylibStorage",isDirectory:true)
    }

    private init() { refresh() }

    private func sha256(_ url:URL) throws -> String {
        let file = try FileHandle(forReadingFrom:url)
        defer { try? file.close() }
        var hasher = SHA256()
        while let data = try file.read(upToCount:524288), !data.isEmpty {
            hasher.update(data:data)
        }
        return hasher.finalize().map { String(format:"%02x",$0) }.joined()
    }

    func refresh() {
        sharedContainerAvailable = FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier:Self.appGroupID) != nil
        let directory = root
        try? FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        let files = (try? FileManager.default.contentsOfDirectory(at:directory,
            includingPropertiesForKeys:[.isRegularFileKey,.fileSizeKey],
            options:[.skipsHiddenFiles])) ?? []
        items = files.compactMap { url -> SavedDylib? in
            guard url.pathExtension.lowercased() == "dylib",
                  (try? url.resourceValues(forKeys:[.isRegularFileKey]))?.isRegularFile == true,
                  let hash = try? sha256(url) else { return nil }
            let bytes = Int64((try? url.resourceValues(forKeys:[.fileSizeKey]))?.fileSize ?? 0)
            return SavedDylib(url:url,hash:hash,byteCount:bytes)
        }.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    enum SaveResult {
        case saved, duplicate
    }
    func save(_ input:URL,originalName:String? = nil) throws -> SaveResult {
        let requestedName = originalName ?? input.lastPathComponent
        guard requestedName.lowercased().hasSuffix(".dylib"),
              requestedName.range(of:"^[A-Za-z0-9][A-Za-z0-9._+-]{0,96}\\.dylib$",options:.regularExpression) != nil,
              !requestedName.contains("..") else {
            throw ManagerError.message("Select a .dylib file.")
        }
        refresh()
        let hash = try sha256(input)
        if items.contains(where:{$0.hash == hash}) { return .duplicate }
        let dest = root.appendingPathComponent(requestedName)
        guard !FileManager.default.fileExists(atPath:dest.path) else {
            throw ManagerError.message("A different dylib already uses this filename. Rename it first.")
        }
        try FileManager.default.copyItem(at:input,to:dest)
        refresh()
        return .saved
    }
    func rename(_ item:SavedDylib,to proposed:String) throws {
        var name = proposed.trimmingCharacters(in:.whitespacesAndNewlines)
        if name.lowercased().hasSuffix(".dylib") { name = String(name.dropLast(6)) }
        guard name.range(of:"^[A-Za-z0-9][A-Za-z0-9._+-]{0,96}$",
                         options:.regularExpression) != nil,
              !name.contains("..") else {
            throw ManagerError.message("Use letters, numbers, periods, dashes, underscores or +.")
        }
        let output = root.appendingPathComponent(name + ".dylib")
        guard output.path != item.url.path else { return }
        guard !FileManager.default.fileExists(atPath:output.path) else {
            throw ManagerError.message("Another dylib already has that name.")
        }
        try FileManager.default.moveItem(at:item.url,to:output)
        refresh()
    }
    func remove(_ item:SavedDylib) throws {
        guard item.url.deletingLastPathComponent().standardizedFileURL == root.standardizedFileURL else {
            throw ManagerError.message("Invalid storage path.")
        }
        try FileManager.default.removeItem(at:item.url)
        refresh()
    }
}
