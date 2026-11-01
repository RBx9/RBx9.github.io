import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import UIKit
import CryptoKit
import Security

private let owner = "RBx9"
private let repo = "RBx9.github.io"
private let repository = "\(owner)/\(repo)"

enum ManagerError: LocalizedError {
    case message(String)
    var errorDescription: String? {
        if case .message(let s) = self { return s }
        return "Unexpected error"
    }
}

enum SecretStore {
    static let key = "rbx9.source.manager.github"
    static func read() -> String {
        let q: [String: Any] = [kSecClass as String:kSecClassGenericPassword,
                                kSecAttrAccount as String:key,
                                kSecReturnData as String:true,
                                kSecMatchLimit as String:kSecMatchLimitOne]
        var item: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let value = String(data:data, encoding:.utf8) else { return "" }
        return value
    }
    static func write(_ value: String) {
        let q: [String: Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrAccount as String:key]
        SecItemDelete(q as CFDictionary)
        if !value.isEmpty {
            let a: [String: Any] = q.merging([kSecValueData as String:Data(value.utf8),
                                              kSecAttrAccessible as String:kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]) { _,new in new }
            SecItemAdd(a as CFDictionary,nil)
        }
    }
}

struct DeviceCode: Decodable {
    let device_code: String
    let user_code: String
    let verification_uri: String
    let expires_in: Int
    let interval: Int
}

struct SourceApp: Identifiable {
    let id: String
    let name: String
    let version: String
    let icon: String
    let developer: String
}
struct StagedSourceFile: Identifiable {
    let id = UUID()
    let url: URL
    let name: String
}

struct SourceDeb: Identifiable {
    let line: String
    let filename: String
    var id: String { line }
}

@MainActor
final class GitHubManager: ObservableObject {
    @Published var username: String = ""
    @Published var busy = false
    @Published var status = ""
    @Published var apps: [SourceApp] = []
    @Published var debs: [SourceDeb] = []
    @Published var catalog: [String:Any] = [:]
    @Published var ipaName = "RBx9 IPA Library"
    @Published var ipaDescription = "Browse IPAs from RBx9."
    @Published var sileoName = "RBx9 Repo"
    @Published var sileoDescription = "RBx9's jailbreak tweak repository for Sileo"
    @Published var ipaIconURL = "https://rbx9.github.io/icon.png"
    @Published var sileoIconURL = "https://rbx9.github.io/CydiaIcon.png"
    @Published var alertMessage: String? = nil
    @Published var uploadFraction: Double? = nil
    @Published var uploadSummary = ""
    @Published var uploadRemainder = ""
    @Published var hiddenBundles: Set<String> = []
    private var token = SecretStore.read()

    init() {
        if !token.isEmpty {
            Task {
                await refresh()
                await resumePendingPublicationIfNeeded()
                await resumeSavedInjectionIfNeeded()
            }
        }
    }
    var connected: Bool { !token.isEmpty && !username.isEmpty }
    private func json(_ value: Any) throws -> Data {
        try JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys,.fragmentsAllowed])
    }
    private func api(_ method: String, _ path: String, body: Data? = nil, media: String = "application/vnd.github+json", host: String = "api.github.com") async throws -> Data {
        guard !token.isEmpty else { throw ManagerError.message("Connect your GitHub account in Settings first.") }
        guard let url = URL(string:"https://\(host)\(path)") else { throw ManagerError.message("Invalid URL") }
        var req = URLRequest(url:url)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField:"Authorization")
        req.setValue("application/vnd.github+json",forHTTPHeaderField:"Accept")
        req.setValue("2022-11-28", forHTTPHeaderField:"X-GitHub-Api-Version")
        if let body {
            req.httpBody = body
            req.setValue(media,forHTTPHeaderField:"Content-Type")
        }
        let (data,response) = try await URLSession.shared.data(for:req)
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        if !(200...299).contains(code) {
            let message = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
            throw ManagerError.message("GitHub \(code): \(message?["message"] as? String ?? String(decoding:data,as:UTF8.self))")
        }
        return data
    }
    private func parse(_ data: Data) throws -> [String:Any] {
        guard let obj = try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw ManagerError.message("Invalid GitHub response") }
        return obj
    }
    private func file(_ path: String) async throws -> (Data,String) {
        let data = try await api("GET","/repos/\(repository)/contents/\(path)")
        let item = try parse(data)
        let content = (item["content"] as? String ?? "").replacingOccurrences(of:"\n",with:"")
        guard let decoded = Data(base64Encoded:content), let sha = item["sha"] as? String else {
            throw ManagerError.message("Could not read \(path)")
        }
        return (decoded,sha)
    }
    private func put(_ path:String, data:Data) async throws {
        var sha: String? = nil
        do { (_,sha) = try await file(path) } catch {
            if !error.localizedDescription.contains("404") { throw error }
        }
        var body: [String:Any] = ["message":"Update \(path) from RBx9 Source Manager",
                                 "content":data.base64EncodedString(), "branch":"main"]
        if let sha { body["sha"] = sha }
        _ = try await api("PUT","/repos/\(repository)/contents/\(path)",body:try json(body))
    }
    func connect(_ value:String) async {
        token = value.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !token.isEmpty else { status = "Enter a GitHub access token"; return }
        do {
            let data = try await api("GET","/user")
            let user = try parse(data)
            guard let login = user["login"] as? String, login.lowercased() == owner.lowercased() else {
                throw ManagerError.message("Connect the RBx9 GitHub account.")
            }
            SecretStore.write(token)
            username = login
            status = "Connected as @\(login)"
            await refresh()
        } catch {
            token = ""
            status = error.localizedDescription
        }
    }
    func disconnect() {
        SecretStore.write("")
        token = ""
        username = ""
        apps = []
        debs = []
        status = "Disconnected"
    }
    func beginDeviceLogin(clientID:String) async throws -> DeviceCode {
        guard !clientID.isEmpty else { throw ManagerError.message("Set your GitHub OAuth App Client ID in Settings.") }
        var req = URLRequest(url:URL(string:"https://github.com/login/device/code")!)
        req.httpMethod = "POST"
        req.setValue("application/json",forHTTPHeaderField:"Accept")
        req.setValue("application/x-www-form-urlencoded",forHTTPHeaderField:"Content-Type")
        req.httpBody = "client_id=\(clientID)&scope=repo".data(using:.utf8)
        let (data,_) = try await URLSession.shared.data(for:req)
        return try JSONDecoder().decode(DeviceCode.self,from:data)
    }
    func finishDeviceLogin(_ device:DeviceCode,clientID:String) async throws {
        let end = Date().addingTimeInterval(TimeInterval(device.expires_in))
        var interval = max(5,device.interval)
        while Date() < end {
            try await Task.sleep(nanoseconds: UInt64(interval) * 1_000_000_000)
            var req = URLRequest(url:URL(string:"https://github.com/login/oauth/access_token")!)
            req.httpMethod = "POST"
            req.setValue("application/json",forHTTPHeaderField:"Accept")
            req.setValue("application/x-www-form-urlencoded",forHTTPHeaderField:"Content-Type")
            req.httpBody = "client_id=\(clientID)&device_code=\(device.device_code)&grant_type=urn:ietf:params:oauth:grant-type:device_code".data(using:.utf8)
            let (data,_) = try await URLSession.shared.data(for:req)
            let payload = try parse(data)
            if let key = payload["access_token"] as? String {
                await connect(key)
                if !connected { throw ManagerError.message(status) }
                return
            }
            switch payload["error"] as? String ?? "" {
            case "authorization_pending": continue
            case "slow_down": interval = max(interval+5, payload["interval"] as? Int ?? interval+5)
            default: throw ManagerError.message(payload["error_description"] as? String ?? "GitHub authorization failed")
            }
        }
        throw ManagerError.message("GitHub authorization expired; try again.")
    }
    func refresh() async {
        guard !token.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            let user = try parse(try await api("GET","/user"))
            username = user["login"] as? String ?? ""
            let (catalogData,_) = try await file("ipa-source/catalog.json")
            catalog = try parse(catalogData)
            if let (hiddenData, _) = try? await file("ipa-source/hidden-apps.json"),
               let list = try? JSONDecoder().decode([String].self, from: hiddenData) {
                hiddenBundles = Set(list)
            } else { hiddenBundles = [] }
            apps = catalog.compactMap { key, entry -> SourceApp? in
                guard !hiddenBundles.contains(key), let a = entry as? [String:Any] else { return nil }
                let versions = a["versions"] as? [[String:Any]] ?? []
                return SourceApp(id:key,name:a["name"] as? String ?? key,
                                 version:versions.first?["version"] as? String ?? "—",
                                 icon:a["iconURL"] as? String ?? "",
                                 developer:a["developerName"] as? String ?? "RBx9")
            }.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            let (txt,_) = try await file("package-sources.txt")
            debs = String(decoding:txt,as:UTF8.self).split(separator:"\n").compactMap { row in
                let line = String(row)
                guard !line.hasPrefix("#"), line.contains("|") else { return nil }
                let cells = line.split(separator:"|",omittingEmptySubsequences:false)
                guard cells.count == 3 else { return nil }
                return SourceDeb(line:line,filename:String(cells[1]))
            }
            if let (data,_) = try? await file("ipa-source/source-settings.json"),
               let obj = try? parse(data) {
                ipaName = obj["name"] as? String ?? ipaName
                ipaDescription = obj["description"] as? String ?? ipaDescription
                ipaIconURL = obj["iconURL"] as? String ?? ipaIconURL
            }
            if let (data,_) = try? await file("sileo-settings.json"),
               let obj = try? parse(data) {
                sileoName = obj["name"] as? String ?? sileoName
                sileoDescription = obj["description"] as? String ?? sileoDescription
                sileoIconURL = "https://rbx9.github.io/CydiaIcon.png?v=\(Int(Date().timeIntervalSince1970))"
            }
            status = "Synced with GitHub"
        } catch { status = error.localizedDescription }
    }
    func changeApp(bundle:String,name:String,developer:String,description:String,iconURL:String) async {
        let title = name.trimmingCharacters(in:.whitespacesAndNewlines)
        let author = developer.trimmingCharacters(in:.whitespacesAndNewlines)
        let artwork = iconURL.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !title.isEmpty && !author.isEmpty else {
            alertMessage = "App name and developer are required."
            return
        }
        guard artwork.hasPrefix("https://") else {
            alertMessage = "App icon must be an HTTPS image URL."
            return
        }
        await work("Saving app metadata") {
            // Always fetch latest metadata to avoid overwriting another edit.
            let (current,_) = try await self.file("ipa-source/catalog.json")
            var content = try self.parse(current)
            guard var app = content[bundle] as? [String:Any] else {
                throw ManagerError.message("App no longer exists in the catalog.")
            }
            app["name"] = title
            app["developerName"] = author
            app["localizedDescription"] = description
            app["iconURL"] = artwork
            content[bundle] = app
            try await self.put("ipa-source/catalog.json",data:try self.json(content))
        }
        if status.hasPrefix("Saved to GitHub.") {
            alertMessage = "App changes saved to GitHub. Refresh ESign after publishing finishes."
        }
    }
    func removeApp(bundle:String) async {
        await work("Removing app from ESign source") {
            // Keep a durable suppression entry so scheduled catalog imports do
            // not silently bring a deleted listing back into the live feed.
            var hidden = self.hiddenBundles
            hidden.insert(bundle)
            let hiddenData = try JSONEncoder().encode(Array(hidden).sorted())
            try await self.put("ipa-source/hidden-apps.json",data:hiddenData)
            let (latestData, _) = try await self.file("ipa-source/catalog.json")
            var value = try self.parse(latestData)
            value.removeValue(forKey:bundle)
            try await self.put("ipa-source/catalog.json",data:try self.json(value))
        }
    }
    func removeDeb(line:String) async {
        await work("Removing package from Sileo source") {
            let (data,_) = try await self.file("package-sources.txt")
            let lines = String(decoding:data,as:UTF8.self).components(separatedBy:"\n")
            let kept = lines.filter { $0 != line }
            guard kept.count != lines.count else { throw ManagerError.message("Package already removed") }
            try await self.put("package-sources.txt",data:Data((kept.joined(separator:"\n").trimmingCharacters(in:.newlines)+"\n").utf8))
        }
    }
    private func work(_ activity:String,_ action:() async throws -> Void) async {
        busy = true
        status = activity + "…"
        do {
            try await action()
            await refresh()
            status = "Saved to GitHub. GitHub Actions and Pages will publish the update."
        } catch {
            status = error.localizedDescription
            alertMessage = error.localizedDescription
        }
        busy = false
    }
    func updateSourceMetadata(sileo:Bool,name:String,description:String) async {
        let newName = name.trimmingCharacters(in:.whitespacesAndNewlines)
        let newDescription = description.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !newName.isEmpty else {
            alertMessage = "Please enter a source name before saving."
            return
        }
        guard !newDescription.isEmpty else {
            alertMessage = "Please enter a description before saving."
            return
        }
        await work("Saving \(sileo ? "Sileo" : "ESign") settings") {
            let path = sileo ? "sileo-settings.json" : "ipa-source/source-settings.json"
            let (data,_) = try await self.file(path)
            var obj = try self.parse(data)
            obj["name"] = newName
            obj["description"] = newDescription
            try await self.put(path,data:try self.json(obj))
        }
        if !status.hasPrefix("Saved to GitHub.") {
            // work() already displayed the GitHub error
            return
        }
        alertMessage = "\(sileo ? "Sileo" : "ESign") settings saved to GitHub. Allow GitHub Pages to publish, then refresh your source."
    }
    func updateSourceIcon(sileo:Bool,imageData:Data) async {
        await work("Uploading source icon") {
            guard let img = UIImage(data:imageData) else { throw ManagerError.message("Select a valid image.") }
            let renderer = UIGraphicsImageRenderer(size:CGSize(width:512,height:512))
            let png = renderer.pngData { _ in img.draw(in:CGRect(x:0,y:0,width:512,height:512)) }
            if sileo {
                for path in ["CydiaIcon.png","CydiaIcon@2x.png","CydiaIcon@3x.png"] {
                    try await self.put(path,data:png)
                }
                self.sileoIconURL = "https://rbx9.github.io/CydiaIcon.png?v=\(Int(Date().timeIntervalSince1970))"
            } else {
                try await self.put("ipa-source/source-icon.png",data:png)
                let path = "ipa-source/source-settings.json"
                var obj: [String:Any] = [:]
                if let (data,_) = try? await self.file(path) { obj = (try? self.parse(data)) ?? [:] }
                obj["iconURL"] = "https://rbx9.github.io/ipa-source/source-icon.png?v=\(Int(Date().timeIntervalSince1970))"
                try await self.put(path,data:try self.json(obj))
                self.ipaIconURL = obj["iconURL"] as? String ?? self.ipaIconURL
            }
        }
    }
    private func fileHash(_ url:URL) throws -> String {
        var digest = SHA256()
        let handle = try FileHandle(forReadingFrom:url)
        defer { try? handle.close() }
        while let chunk = try handle.read(upToCount:1_048_576), !chunk.isEmpty { digest.update(data:chunk) }
        return digest.finalize().map { String(format:"%02x",$0) }.joined()
    }
    // Stage selected Files documents immediately, while the security-scoped
    // URL returned by the picker is valid; the long upload runs afterward.
    func stageSelectedFile(_ url:URL, expected:String) -> StagedSourceFile? {
        guard url.pathExtension.lowercased() == expected else {
            alertMessage = "Select a .\(expected) file from Files."
            return nil
        }
        let scope = url.startAccessingSecurityScopedResource()
        defer { if scope { url.stopAccessingSecurityScopedResource() } }
        let target = RBx9PendingUploadStore.directory
            .appendingPathComponent("rbx9-staged-\(UUID().uuidString).\(expected)")
        do {
            var coordError: NSError?
            var copyError: Error?
            NSFileCoordinator(filePresenter:nil).coordinate(readingItemAt:url, options:[],error:&coordError) { readable in
                do { try FileManager.default.copyItem(at:readable,to:target) }
                catch { copyError = error }
            }
            if let error = coordError { throw error }
            if let error = copyError { throw error }
            guard FileManager.default.fileExists(atPath:target.path) else {
                throw ManagerError.message("Files could not copy this document.")
            }
            return StagedSourceFile(url:target, name:url.lastPathComponent)
        } catch {
            alertMessage = "Could not import \(url.lastPathComponent): \(error.localizedDescription)"
            return nil
        }
    }
    func discardStagedFiles(_ files:[StagedSourceFile]) {
        for file in files { try? FileManager.default.removeItem(at:file.url) }
    }
    /// Rename the downloadable Release asset without changing the app bundle ID.
    /// Keep extensions fixed and use a filename format GitHub will not rewrite.
    func checkedPublicationName(_ proposed:String, ext:String) throws -> String {
        var base = proposed.trimmingCharacters(in:.whitespacesAndNewlines)
        if base.lowercased().hasSuffix("." + ext) {
            base = String(base.dropLast(ext.count + 1))
        }
        base = base.replacingOccurrences(of:" ",with:"-")
        guard base.range(of:"^[A-Za-z0-9][A-Za-z0-9._-]{0,96}$",
                         options:.regularExpression) != nil,
              !base.contains("..") else {
            throw ManagerError.message(
                "Enter a file name using letters, numbers, spaces, dots, hyphens or underscores (maximum 97 characters)."
            )
        }
        return base + "." + ext
    }
    @discardableResult
    func publishSelectedIPA(_ ipa:StagedSourceFile, libraries:[StagedSourceFile], publishedName:String) -> Bool {
        guard !busy else { alertMessage = "A publish operation is already running."; return false }
        do {
            let name = try checkedPublicationName(publishedName, ext:"ipa")
            if libraries.isEmpty {
                Task { await upload(stagedFile:ipa.url,originalName:name,sileo:false) }
            } else {
                Task { await uploadInjectedIPA(ipa,libraries:libraries,outputName:name) }
            }
            return true
        } catch {
            alertMessage = error.localizedDescription
            return false
        }
    }
    @discardableResult
    func publishSelectedDEB(_ deb:StagedSourceFile, publishedName:String) -> Bool {
        guard !busy else { alertMessage = "A publish operation is already running."; return false }
        do {
            let name = try checkedPublicationName(publishedName,ext:"deb")
            Task { await upload(stagedFile:deb.url,originalName:name,sileo:true) }
            return true
        } catch {
            alertMessage = error.localizedDescription
            return false
        }
    }
    private func isOfflineError(_ error:Error) -> Bool {
        let code = (error as? URLError)?.code
        return code == .notConnectedToInternet || code == .networkConnectionLost ||
            code == .timedOut || code == .cannotConnectToHost ||
            code == .cannotFindHost || code == .dnsLookupFailed ||
            code == .internationalRoamingOff || code == .dataNotAllowed
    }
    private func progressUpdate(sent:Int64,total:Int64,eta:Double?) {
        guard total > 0 else { return }
        uploadFraction = min(1,max(0,Double(sent)/Double(total)))
        let mb = 1_048_576.0
        uploadSummary = String(format:"%.1f / %.1f MB uploaded",Double(sent)/mb,Double(total)/mb)
        let remaining = max(0,total-sent)
        let timeText:String
        if let eta,eta.isFinite {
            let seconds = Int(min(eta,Double(Int.max)/2))
            timeText = seconds >= 3600 ? String(format:"~%dh %dm",seconds/3600,seconds%3600/60) :
                seconds >= 60 ? String(format:"~%dm %ds",seconds/60,seconds%60) :
                "~\(seconds)s"
        } else {
            timeText = "Calculating time…"
        }
        uploadRemainder = String(format:"%.1f MB left · %@",Double(remaining)/mb,timeText)
    }
    private func existingAsset(releaseID:Int,name:String) async -> [String:Any]? {
        guard let data = try? await api("GET","/repos/\(repository)/releases/\(releaseID)/assets?per_page=100"),
              let results = try? JSONSerialization.jsonObject(with:data) as? [[String:Any]] else {
            return nil
        }
        return results.first(where:{$0["name"] as? String == name &&
                        $0["state"] as? String == "uploaded"})
    }
    private func uploadReleaseAsset(_ path:URL,name:String,releaseID:Int) async throws -> [String:Any] {
        let localSize = (try? path.resourceValues(forKeys:[.fileSizeKey]))?.fileSize ?? 0
        var retries = 0
        while true {
            if let uploaded = await existingAsset(releaseID:releaseID,name:name) {
                guard uploaded["size"] as? Int == localSize else {
                    throw ManagerError.message("An uploaded asset already uses \(name) but has a different size.")
                }
                uploadFraction = 1
                uploadSummary = "File already uploaded"
                uploadRemainder = "0 MB left"
                return uploaded
            }
            var parts=URLComponents(string:"https://uploads.github.com/repos/\(repository)/releases/\(releaseID)/assets")!
            parts.queryItems=[URLQueryItem(name:"name",value:name)]
            var req=URLRequest(url:parts.url!)
            req.httpMethod="POST"
            req.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")
            req.setValue("application/vnd.github+json",forHTTPHeaderField:"Accept")
            req.setValue("application/octet-stream",forHTTPHeaderField:"Content-Type")
            req.setValue("2022-11-28",forHTTPHeaderField:"X-GitHub-Api-Version")
            uploadFraction = 0
            uploadSummary = String(format:"0 / %.1f MB uploaded",Double(localSize)/1_048_576)
            uploadRemainder = "Calculating remaining time…"
            do {
                let (data,response) = try await RBx9UploadTransport.shared.upload(
                    request:req,fromFile:path,
                    onProgress:{ [weak self] sent,total,eta in
                        Task { @MainActor [weak self] in
                            self?.progressUpdate(sent:sent,total:total,eta:eta)
                        }
                    }
                )
                let code=(response as? HTTPURLResponse)?.statusCode ?? 0
                if (200...299).contains(code) { return try parse(data) }
                if code == 422, let existing = await existingAsset(releaseID:releaseID,name:name) {
                    if existing["size"] as? Int == localSize { return existing }
                }
                if [429,500,502,503,504].contains(code) {
                    retries += 1
                    status = "GitHub is temporarily unavailable. Retrying upload automatically…"
                    try await Task.sleep(nanoseconds:UInt64(min(30,3*retries))*1_000_000_000)
                    continue
                }
                throw ManagerError.message("Upload failed (HTTP \(code)): \(String(decoding:data,as:UTF8.self).prefix(200))")
            } catch {
                guard isOfflineError(error) else { throw error }
                retries += 1
                status = "Connection lost. Your IPA is safely saved; waiting and retrying…"
                uploadRemainder = "Will retry when internet returns"
                try await Task.sleep(nanoseconds:UInt64(min(30,3*retries))*1_000_000_000)
                // GitHub does not support partial release-asset resumes.
                // The background task or next attempt can re-transfer this file.
            }
        }
    }
    private func apiWhenConnected(_ method:String,_ path:String,body:Data? = nil) async throws -> Data {
        var attempts=0
        while true {
            do { return try await api(method,path,body:body) }
            catch {
                guard isOfflineError(error) else { throw error }
                attempts += 1
                status="Waiting for internet. Upload is saved and will continue automatically…"
                try await Task.sleep(nanoseconds:UInt64(min(30,attempts*3))*1_000_000_000)
            }
        }
    }
    private func uploadInjectedIPA(_ ipa:StagedSourceFile,libraries:[StagedSourceFile],outputName:String) async {
        guard !busy else { return }
        busy=true
        var finished=false
        defer {
            busy=false
            if finished {
                RBx9PendingInjectionStore.clear()
                discardStagedFiles([ipa]+libraries)
            }
        }
        do {
            guard !libraries.isEmpty && libraries.count <= 16 else {
                throw ManagerError.message("Choose between 1 and 16 dylibs.")
            }
            let fileName=try checkedPublicationName(outputName,ext:"ipa")
            let names=libraries.map{$0.name.lowercased()}
            guard Set(names).count == libraries.count else {
                throw ManagerError.message("Duplicate dylib filenames are not allowed.")
            }
            var job=RBx9PendingInjectionStore.load()
            if job?.ipaPath != ipa.url.path {
                job=RBx9PendingInjection(ipaPath:ipa.url.path,ipaName:ipa.name,
                    outputName:fileName,
                    libraries:libraries.map{ RBx9PendingDylib(path:$0.url.path,name:$0.name) },
                    tag:"source-manager-inject-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))",
                    releaseID:nil)
                try RBx9PendingInjectionStore.save(job!)
            }
            guard var active=job else { throw ManagerError.message("Could not save injection queue") }
            let metadata=RBx9PendingUploadStore.directory
                .appendingPathComponent("publish-name-" + active.tag + ".txt")
            defer { if finished { try? FileManager.default.removeItem(at:metadata) } }
            try Data((fileName+"\n").utf8).write(to:metadata,options:.atomic)
            if active.releaseID == nil {
                status="Creating injection draft release…"
                // A GET by the stored unique tag handles lost POST responses
                // without creating a second release.
                let existing=try? await apiWhenConnected("GET",
                    "/repos/\(repository)/releases/tags/\(active.tag)")
                let releaseData:Data
                if let existing { releaseData=existing }
                else {
                    let body="Prepared by RBx9 Source Manager. Original IPA: \(ipa.name). Download filename: \(fileName). Dylibs: \(libraries.map(\.name).joined(separator:", ")). Unsigned IPA."
                    releaseData=try await apiWhenConnected("POST",
                        "/repos/\(repository)/releases",
                        body:try json(["tag_name":active.tag,"name":"Injected \(fileName)",
                            "body":body,"draft":true,"prerelease":false]))
                }
                guard let id=try parse(releaseData)["id"] as? Int else {
                    throw ManagerError.message("Could not create injection release")
                }
                active.releaseID=id
                try RBx9PendingInjectionStore.save(active)
            }
            guard let id=active.releaseID else { throw ManagerError.message("Missing release ID") }
            status="Uploading original IPA…"
            _=try await uploadReleaseAsset(ipa.url,name:"original-ipa.upload",releaseID:id)
            status="Uploading IPA publication name…"
            _=try await uploadReleaseAsset(metadata,name:"publish-name.txt",releaseID:id)
            for (index,lib) in libraries.enumerated() {
                status="Uploading dylib \(index+1)/\(libraries.count)…"
                _=try await uploadReleaseAsset(lib.url,name:lib.name,releaseID:id)
            }
            status="Handing off to the injection verifier…"
            _=try await apiWhenConnected("PATCH","/repos/\(repository)/releases/\(id)",
                body:try json(["draft":false]))
            finished=true
            uploadFraction=1
            uploadRemainder="0 MB left · Transfer complete"
            status="Injection queued. The modified IPA is published only after GitHub verification."
            alertMessage="All files uploaded. The modified IPA will appear in ESign after verification succeeds."
        } catch {
            status="Injection upload paused: \(error.localizedDescription)"
            alertMessage="Your IPA and dylibs are saved locally. The app will retry this upload when reopened."
        }
    }
    func importFile(_ url:URL,sileo:Bool) {
        guard !busy else { alertMessage = "Please complete the current upload first."; return }
        guard let file = stageSelectedFile(url,expected:sileo ? "deb" : "ipa") else { return }
        Task { await upload(stagedFile:file.url,originalName:file.name,sileo:sileo) }
    }
    private func resumePendingPublicationIfNeeded() async {
        guard !busy,let job = RBx9PendingUploadStore.load() else { return }
        let staged=URL(fileURLWithPath:job.stagedPath)
        guard FileManager.default.fileExists(atPath:staged.path) else {
            RBx9PendingUploadStore.clear()
            return
        }
        status = "Resuming saved upload \(job.filename)…"
        await upload(stagedFile:staged,originalName:job.filename,sileo:job.sileo)
    }
    private func resumeSavedInjectionIfNeeded() async {
        guard !busy,let job=RBx9PendingInjectionStore.load() else { return }
        let ipaURL=URL(fileURLWithPath:job.ipaPath)
        let files=job.libraries.map {
            StagedSourceFile(url:URL(fileURLWithPath:$0.path),name:$0.name)
        }
        guard FileManager.default.fileExists(atPath:ipaURL.path),
              files.allSatisfy({FileManager.default.fileExists(atPath:$0.url.path)}) else {
            status="Saved injection files are missing. Re-select IPA and dylibs."
            return
        }
        status="Resuming your saved IPA+dylib upload…"
        await uploadInjectedIPA(StagedSourceFile(url:ipaURL,name:job.ipaName),
                                libraries:files,outputName:job.outputName)
    }
    private func upload(stagedFile:URL,originalName:String,sileo:Bool) async {
        guard !busy else { return }
        busy=true
        var succeeded=false
        defer {
            busy=false
            if succeeded {
                RBx9PendingUploadStore.clear()
                try? FileManager.default.removeItem(at:stagedFile)
            }
        }
        do {
            let ext=sileo ? "deb" : "ipa"
            let name=try checkedPublicationName(originalName,ext:ext)
            var job = RBx9PendingUploadStore.load()
            if job?.stagedPath != stagedFile.path {
                job = RBx9PendingPublication(stagedPath:stagedFile.path,filename:name,
                    sileo:sileo,releaseID:nil,completedAssetURL:nil,
                    tag:"source-manager-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))")
                try RBx9PendingUploadStore.save(job!)
            }
            guard var active=job else { throw ManagerError.message("Could not save upload queue") }
            if active.releaseID == nil {
                status="Creating GitHub draft release…"
                if active.tag == nil {
                    active.tag="source-manager-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))"
                    try RBx9PendingUploadStore.save(active)
                }
                let tag=active.tag!
                let existing=try? await apiWhenConnected("GET",
                    "/repos/\(repository)/releases/tags/\(tag)")
                let releaseData:Data
                if let existing { releaseData=existing }
                else {
                    do {
                        releaseData=try await apiWhenConnected("POST","/repos/\(repository)/releases",
                            body:try json(["tag_name":tag,"name":name,
                                          "body":"Uploaded using RBx9 Source Manager",
                                          "draft":true,"prerelease":false]))
                    } catch {
                        if let recovered=try? await apiWhenConnected("GET",
                            "/repos/\(repository)/releases/tags/\(tag)") {
                            releaseData=recovered
                        } else { throw error }
                    }
                }
                let response=try parse(releaseData)
                guard let id=response["id"] as? Int else {
                    throw ManagerError.message("Could not create draft release")
                }
                active.releaseID=id
                try RBx9PendingUploadStore.save(active)
            }
            guard let releaseID=active.releaseID else { throw ManagerError.message("Missing release ID") }
            if active.completedAssetURL == nil {
                status="Uploading \(name)…"
                let asset=try await uploadReleaseAsset(stagedFile,name:name,releaseID:releaseID)
                guard let url=asset["browser_download_url"] as? String else {
                    throw ManagerError.message("GitHub did not return the uploaded file URL")
                }
                active.completedAssetURL=url
                try RBx9PendingUploadStore.save(active)
            }
            guard let downloadURL=active.completedAssetURL else { throw ManagerError.message("No download URL") }
            status="Finalizing source update…"
            if sileo {
                let sha=try fileHash(stagedFile)
                let (source,_)=try await file("package-sources.txt")
                let lines=String(decoding:source,as:UTF8.self)
                let row="\(downloadURL)|\(name)|\(sha)"
                if !lines.contains(row) {
                    let updated=lines.trimmingCharacters(in:.newlines)+"\n"+row+"\n"
                    try await put("package-sources.txt",data:Data(updated.utf8))
                }
            }
            _=try await apiWhenConnected("PATCH","/repos/\(repository)/releases/\(releaseID)",body:try json(["draft":false]))
            succeeded=true
            uploadFraction=1
            uploadRemainder="0 MB left · Upload complete"
            await refresh()
            status="Uploaded successfully. GitHub Actions is updating the source."
        } catch {
            status=error.localizedDescription
            alertMessage="Upload paused: \(error.localizedDescription). The file is retained for recovery after reconnecting or reopening the app."
        }
    }

}

struct Theme {
    static let cyan = Color(red:0.12,green:0.82,blue:0.98)
    static let background = Color(red:0.045,green:0.065,blue:0.11)
}
struct Panel<Content:View>:View {
    let content:Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    var body:some View {
        VStack(alignment:.leading,spacing:13) { content }
            .padding(17).frame(maxWidth:.infinity,alignment:.leading)
            .background(Color.white.opacity(0.065),in:RoundedRectangle(cornerRadius:21))
    }
}
struct PrimaryButton:View {
    let title:String
    let symbol:String
    let action:()->Void
    var body:some View {
        Button(action:action) { Label(title,systemImage:symbol).font(.headline).frame(maxWidth:.infinity).padding(14) }
            .buttonStyle(.plain).background(Theme.cyan,in:RoundedRectangle(cornerRadius:15)).foregroundStyle(.black)
    }
}

@main struct RBx9SourceManagerApp:App {
    @StateObject private var manager = GitHubManager()
    @StateObject private var uploadDraft = IPAUploadDraft()
    var body:some Scene {
        WindowGroup {
            TabView {
                AppsScreen().tabItem { Label("ESign",systemImage:"square.stack.3d.up") }
                DebsScreen().tabItem { Label("Sileo",systemImage:"shippingbox") }
                SettingsScreen().tabItem { Label("Settings",systemImage:"gearshape") }
            }
            .tint(Theme.cyan)
            .preferredColorScheme(.dark)
            .environmentObject(manager)
            .environmentObject(uploadDraft)
        }
    }
}
struct Header:View {
    let title:String
    let subtitle:String
    var body:some View {
        VStack(alignment:.leading,spacing:5) {
            Text("RBx9").font(.system(size:15,weight:.bold,design:.rounded)).foregroundStyle(Theme.cyan)
            Text(title).font(.system(size:34,weight:.bold,design:.rounded))
            Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
        }.padding(.vertical,12)
    }
}
struct SourceHeader: View {
    @EnvironmentObject var manager: GitHubManager
    let sileo: Bool
    @State private var pickedPhoto: PhotosPickerItem?

    private var sourceIcon: String { sileo ? manager.sileoIconURL : manager.ipaIconURL }
    private var sourceTitle: String { sileo ? manager.sileoName : manager.ipaName }

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            PhotosPicker(selection: $pickedPhoto, matching: .images) {
                ZStack(alignment: .bottomTrailing) {
                    AsyncImage(url: URL(string: sourceIcon)) { phase in
                        if case .success(let artwork) = phase {
                            artwork.resizable().scaledToFill()
                        } else {
                            ZStack {
                                Color.white.opacity(0.1)
                                Image(systemName: sileo ? "shippingbox.fill" : "square.stack.3d.up.fill")
                                    .font(.system(size: 29))
                                    .foregroundStyle(Theme.cyan)
                            }
                        }
                    }
                    .frame(width: 86, height: 86)
                    .clipShape(RoundedRectangle(cornerRadius: 22))
                    .overlay(RoundedRectangle(cornerRadius: 22).stroke(Theme.cyan.opacity(0.4), lineWidth: 1))
                    Image(systemName: "camera.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.black)
                        .padding(7)
                        .background(Theme.cyan, in: Circle())
                        .offset(x: 6, y: 4)
                }
            }
            .buttonStyle(.plain)
            .disabled(manager.busy || !manager.connected)
            .accessibilityLabel("Change \(sileo ? "Sileo" : "ESign") source icon")
            VStack(alignment: .leading, spacing: 5) {
                Text(sourceTitle).font(.title2.bold())
                Text("Tap the icon to change the source picture")
                    .font(.caption).foregroundStyle(.secondary)
                Text(sileo ? "Sileo package repository" : "ESign / Feather IPA repository")
                    .font(.caption).foregroundStyle(Theme.cyan)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 12)
        .onChange(of: pickedPhoto) { item in
            guard let item else { return }
            Task {
                do {
                    guard let data = try await item.loadTransferable(type: Data.self) else {
                        manager.alertMessage = "Could not read the selected picture."
                        return
                    }
                    await manager.updateSourceIcon(sileo:sileo, imageData:data)
                } catch {
                    manager.alertMessage = "Image import failed: \(error.localizedDescription)"
                }
                pickedPhoto = nil
            }
        }
    }
}
struct StatusPanel: View {
    @EnvironmentObject var manager:GitHubManager
    var body:some View {
        Group {
            if manager.busy || !manager.status.isEmpty {
                VStack(alignment:.leading,spacing:7) {
                    HStack(spacing:9) {
                        if manager.busy { ProgressView().tint(Theme.cyan) }
                        Text(manager.status.isEmpty ? "Working…" : manager.status)
                            .font(.caption).foregroundStyle(.primary)
                        Spacer(minLength:0)
                    }
                    if let fraction = manager.uploadFraction {
                        ProgressView(value:fraction,total:1)
                            .tint(Theme.cyan)
                        HStack {
                            Text(manager.uploadSummary)
                            Spacer()
                            Text(manager.uploadRemainder)
                        }
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                    }
                }
                .padding(12).background(.regularMaterial)
            }
        }
    }
}
/// Native iOS document browser. IPA and DEB are not always recognized by
/// SwiftUI's generic .item fileImporter filter; the UIKit import-copy picker
/// uses explicitly registered extensions plus broad document data types.
enum PackagePickKind {
    case ipa, deb, dylib
}
struct PackageDocumentPicker: UIViewControllerRepresentable {
    let kind: PackagePickKind
    let multiple: Bool
    let onPick: ([URL]) -> Void
    let onCancel: () -> Void

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let ipaType = UTType(importedAs: "com.rbx9.source-manager.ipa", conformingTo: .data)
        let debType = UTType(importedAs: "com.rbx9.source-manager.deb", conformingTo: .data)
        let dylibType = UTType(importedAs:"com.rbx9.source-manager.dylib",conformingTo:.data)
        let supported: [UTType]
        switch kind {
        case .ipa: supported = [ipaType, .data, .item, .archive]
        case .deb: supported = [debType, .data, .item, .archive]
        case .dylib: supported = [dylibType]
        }
        let picker = UIDocumentPickerViewController(
            forOpeningContentTypes:supported, asCopy:true
        )
        picker.delegate = context.coordinator
        picker.allowsMultipleSelection = multiple
        picker.shouldShowFileExtensions = true
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onPick: onPick, onCancel: onCancel)
    }

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: ([URL]) -> Void
        let onCancel: () -> Void
        init(onPick: @escaping ([URL]) -> Void, onCancel: @escaping () -> Void) {
            self.onPick = onPick
            self.onCancel = onCancel
        }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            guard !urls.isEmpty else { onCancel(); return }
            onPick(urls)
        }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            onCancel()
        }
    }
}

/// The IPA draft lives at app scope and on disk. A Files picker can replace
/// its SwiftUI presenting view; it must never own or reset the selected IPA.
@MainActor
final class IPAUploadDraft: ObservableObject {
    @Published var ipa: StagedSourceFile? { didSet { persist() } }
    @Published var libraries: [StagedSourceFile] = [] { didSet { persist() } }
    @Published var filename = "" { didSet { persist() } }

    private struct StagedItem: Codable {
        let path: String
        let name: String
        init(_ item: StagedSourceFile) { path = item.url.path; name = item.name }
        func restore() -> StagedSourceFile? {
            guard FileManager.default.fileExists(atPath:path) else { return nil }
            return StagedSourceFile(url:URL(fileURLWithPath:path),name:name)
        }
    }
    private struct Snapshot: Codable {
        var ipa: StagedItem
        var libraries: [StagedItem]
        var filename: String
    }
    private static var snapshotURL: URL {
        RBx9PendingUploadStore.directory
            .appendingPathComponent("selected-ipa-draft.json",isDirectory:false)
    }
    init() {
        guard let data=try? Data(contentsOf:Self.snapshotURL),
              let snapshot=try? JSONDecoder().decode(Snapshot.self,from:data),
              let restoredIPA=snapshot.ipa.restore() else { return }
        ipa=restoredIPA
        libraries=snapshot.libraries.compactMap{$0.restore()}
        filename=snapshot.filename
    }
    private func persist() {
        guard let ipa else {
            try? FileManager.default.removeItem(at:Self.snapshotURL)
            return
        }
        let snapshot=Snapshot(ipa:StagedItem(ipa),
                              libraries:libraries.map{StagedItem($0)},
                              filename:filename)
        guard let data=try? JSONEncoder().encode(snapshot) else { return }
        try? data.write(to:Self.snapshotURL,options:.atomic)
    }
    /// Called only after successfully staging a new IPA. Choosing dylibs can
    /// never reach this function or clear the IPA.
    func selectIPA(_ selected:StagedSourceFile) {
        ipa=selected
        libraries=[]
        filename=(selected.name as NSString).deletingPathExtension
        persist()
    }
    func clearWithoutDeleting() {
        ipa=nil
        libraries=[]
        filename=""
        try? FileManager.default.removeItem(at:Self.snapshotURL)
    }
}

private enum IPAPicker: String, Identifiable {
    case ipa, dylib, vaultImport
    var id: String { rawValue }
}

struct AppsScreen: View {
    @EnvironmentObject var manager: GitHubManager
    @State private var activePicker: IPAPicker?
    @EnvironmentObject private var draft: IPAUploadDraft
    @StateObject private var vault = RBx9DylibVault.shared
    @State private var renameDylib: SavedDylib?
    @State private var renameDylibText = ""
    @State private var deleteDylib: SavedDylib?
    @State private var pendingDelete: SourceApp?

    @ViewBuilder private var uploadSection: some View {
                Section {
                    SourceHeader(sileo:false)
                    HStack {
                        Label(manager.connected ? "@\(manager.username)" : "Connect in Settings", systemImage: "checkmark.icloud")
                        Spacer()
                        Text("\(manager.apps.count) apps").foregroundStyle(.secondary)
                    }
                    .font(.caption)
                    PrimaryButton(title:"Select IPA from Files", symbol:"plus.circle.fill") {
                        activePicker = .ipa
                    }
                    .disabled(manager.busy || !manager.connected)
                    if let ipa = draft.ipa {
                        VStack(alignment:.leading,spacing:12) {
                            Label(ipa.name,systemImage:"doc.zipper")
                                .font(.headline)
                                .lineLimit(2)
                            HStack(spacing:8) {
                                TextField("Download filename",text:$draft.filename)
                                    .textFieldStyle(.roundedBorder)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                Text(".ipa").font(.subheadline.monospaced()).foregroundStyle(.secondary)
                            }
                            Text("Rename the downloadable IPA before publishing. This doesn't change the app's name or bundle ID.")
                                .font(.caption).foregroundStyle(.secondary)
                            Text(draft.libraries.isEmpty ? "No dylibs selected. You can upload the original IPA or add libraries first." : "\(draft.libraries.count) selected dylib(s) will be embedded in the IPA.")
                                .font(.caption).foregroundStyle(.secondary)
                            Button {
                                activePicker = .dylib
                            } label: {
                                Label("Add Dylibs from Files",systemImage:"puzzlepiece.extension.fill")
                                    .font(.subheadline.bold()).foregroundStyle(Theme.cyan)
                            }
                            .disabled(manager.busy)
                            ForEach(draft.libraries) { item in
                                HStack {
                                    Image(systemName:"puzzlepiece.fill").foregroundStyle(Theme.cyan)
                                    Text(item.name).font(.caption).lineLimit(1)
                                    Spacer()
                                    Button(role:.destructive) {
                                        manager.discardStagedFiles([item])
                                        draft.libraries.removeAll { $0.id == item.id }
                                    } label: { Image(systemName:"xmark.circle.fill") }
                                }
                            }
                            PrimaryButton(
                                title:draft.libraries.isEmpty ? "Publish Original IPA" : "Inject Dylibs & Publish",
                                symbol:"arrow.up.doc.fill"
                            ) {
                                guard let ipa = draft.ipa else { return }
                                if manager.publishSelectedIPA(ipa,libraries:draft.libraries,publishedName:draft.filename) {
                                    draft.clearWithoutDeleting()
                                }
                            }
                            .disabled(manager.busy || !manager.connected)
                            Button("Cancel selection",role:.cancel) {
                                if let ipa = draft.ipa {
                                    manager.discardStagedFiles([ipa] + draft.libraries)
                                }
                                draft.clearWithoutDeleting()
                            }.font(.caption)
                        }
                    }
                }
                .listRowBackground(Color.white.opacity(0.055))
    }
    @ViewBuilder private var storageSection: some View {
                Section("Dylib Storage") {
                    HStack {
                        Label("\(vault.items.count) saved dylibs", systemImage:"externaldrive.fill")
                        Spacer()
                        Button { activePicker = .vaultImport } label: {
                            Label("Import",systemImage:"plus")
                        }.foregroundStyle(Theme.cyan)
                    }
                    if !vault.sharedContainerAvailable {
                        Text("Storage is private to this app until RBx9 Signer and Source Manager are both signed with the same App Group entitlement. You can import Signer dylibs through Files.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if vault.items.isEmpty {
                        Text("No stored dylibs yet. Add them from Files or an IPA draft.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(vault.items) { saved in
                        HStack {
                            Image(systemName:"puzzlepiece.fill").foregroundStyle(Theme.cyan)
                            VStack(alignment:.leading) {
                                Text(saved.name).font(.subheadline)
                                Text(ByteCountFormatter.string(fromByteCount:saved.byteCount,countStyle:.file))
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button {
                                renameDylib = saved
                                renameDylibText = (saved.name as NSString).deletingPathExtension
                            } label: { Image(systemName:"pencil") }
                                .buttonStyle(.borderless)
                            Button {
                                if let draftIPA = draft.ipa {
                                    _ = draftIPA
                                    if draft.libraries.contains(where:{$0.name.lowercased() == saved.name.lowercased()}) {
                                        manager.alertMessage = "This dylib is already selected."
                                    } else if draft.libraries.count < 16,
                                              let item = manager.stageSelectedFile(saved.url,expected:"dylib") {
                                        draft.libraries.append(item)
                                    }
                                } else {
                                    manager.alertMessage = "Select an IPA first to add a stored dylib."
                                }
                            } label: { Image(systemName:"plus.circle") }
                                .buttonStyle(.borderless)
                            Button(role:.destructive) { deleteDylib = saved } label: {
                                Image(systemName:"trash")
                            }.buttonStyle(.borderless)
                        }
                    }
                }
    }

    var body: some View {
        NavigationStack {
            List {
                uploadSection
                storageSection
                Section("Published applications") {
                    ForEach(manager.apps) { app in
                        NavigationLink {
                            AppEditor(app:app)
                        } label: {
                            HStack(spacing: 13) {
                                AsyncImage(url:URL(string:app.icon)) { image in
                                    image.resizable().scaledToFill()
                                } placeholder: {
                                    Image(systemName:"app.fill").resizable().scaledToFit().padding(12)
                                }
                                .frame(width:52,height:52)
                                .background(.white.opacity(0.1))
                                .clipShape(RoundedRectangle(cornerRadius:12))
                                VStack(alignment:.leading,spacing:4) {
                                    Text(app.name).font(.headline)
                                    Text(app.id).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                                    Text("v\(app.version) · \(app.developer)").font(.caption).foregroundStyle(Theme.cyan)
                                }
                            }.padding(.vertical, 3)
                        }
                        .swipeActions(edge:.trailing, allowsFullSwipe:false) {
                            Button(role:.destructive) { pendingDelete = app } label: {
                                Label("Delete", systemImage:"trash")
                            }
                            .disabled(manager.busy)
                        }
                    }
                }
                if manager.apps.isEmpty {
                    Text("No apps in the source. Select Add IPA to import a file from your iPhone.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Text("Swipe left to remove an app. Every removal requires confirmation. Publishing to GitHub Actions and Pages can take a little time.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("ESign")
            .toolbar {
                ToolbarItem(placement:.topBarTrailing) {
                    Button { Task { await manager.refresh() } } label: { Image(systemName:"arrow.clockwise") }
                        .disabled(manager.busy)
                }
            }
            // One modal host prevents the IPA draft from disappearing when
            // dismissing the IPA picker and presenting the dylib picker.
            .sheet(item:$activePicker, onDismiss:{ vault.refresh() }) { kind in
                PackageDocumentPicker(
                    kind: kind == .ipa ? .ipa : .dylib,
                    multiple:kind != .ipa,
                    onPick: { urls in
                        switch kind {
                        case .ipa:
                            if let url = urls.first {
                                let newFile = manager.stageSelectedFile(url,expected:"ipa")
                                if let newFile {
                                    if let previous = draft.ipa {
                                        manager.discardStagedFiles([previous] + draft.libraries)
                                    }
                                    draft.selectIPA(newFile)
                                }
                            }
                        case .dylib:
                            for url in urls {
                                guard draft.libraries.count < 16 else {
                                    manager.alertMessage = "You can add up to 16 dylibs."
                                    break
                                }
                                guard let item = manager.stageSelectedFile(url,expected:"dylib") else { continue }
                                if draft.libraries.contains(where:{$0.name.lowercased() == item.name.lowercased()}) {
                                    manager.discardStagedFiles([item])
                                    manager.alertMessage = "Duplicate dylib: \(item.name)"
                                } else {
                                    draft.libraries.append(item)
                                    // Keep the original IPA draft untouched.
                                    do { _ = try vault.save(item.url,originalName:item.name) } catch { /* storage is optional */ }
                                }
                            }
                        case .vaultImport:
                            for url in urls {
                                guard let file = manager.stageSelectedFile(url,expected:"dylib") else { continue }
                                do {
                                    _ = try vault.save(file.url,originalName:file.name)
                                } catch { manager.alertMessage = error.localizedDescription }
                                manager.discardStagedFiles([file])
                            }
                        }
                        activePicker = nil
                    },
                    onCancel: { activePicker = nil }
                )
                .id(kind.id) // Prevent UIKit picker/coordinator reuse across file types.
            }
            .onAppear { vault.refresh() }
            .alert("Rename dylib",isPresented:Binding(
                get:{renameDylib != nil},set:{if !$0 {renameDylib=nil}}
            )) {
                TextField("Dylib name",text:$renameDylibText)
                Button("Save") {
                    if let item = renameDylib {
                        do { try vault.rename(item,to:renameDylibText) }
                        catch { manager.alertMessage = error.localizedDescription }
                    }
                    renameDylib = nil
                }
                Button("Cancel",role:.cancel) { renameDylib=nil }
            }
            .confirmationDialog("Delete saved dylib?",isPresented:Binding(
                get:{deleteDylib != nil},set:{if !$0 {deleteDylib=nil}}
            ),titleVisibility:.visible) {
                Button("Delete saved copy",role:.destructive) {
                    if let item = deleteDylib {
                        do { try vault.remove(item) }
                        catch { manager.alertMessage = error.localizedDescription }
                    }
                    deleteDylib = nil
                }
                Button("Cancel",role:.cancel) { deleteDylib=nil }
            }
            .confirmationDialog("Remove \(pendingDelete?.name ?? "app")?",
                isPresented:Binding(get:{pendingDelete != nil},set:{if !$0 {pendingDelete=nil}}),
                titleVisibility:.visible) {
                    Button("Remove from source", role:.destructive) {
                        if let app = pendingDelete {
                            Task { await manager.removeApp(bundle:app.id) }
                        }
                        pendingDelete = nil
                    }
                    Button("Cancel",role:.cancel) { pendingDelete=nil }
                } message: {
                    Text("This removes the app from the ESign source, but keeps its existing GitHub Release files.")
                }
            .alert("Source Manager",isPresented:Binding(
                get:{manager.alertMessage != nil},
                set:{if !$0 {manager.alertMessage=nil}}
            )) {
                Button("OK", role:.cancel) { manager.alertMessage=nil }
            } message: { Text(manager.alertMessage ?? "") }
            .safeAreaInset(edge:.bottom) { StatusPanel() }
        }
    }
}
struct AppEditor: View {
    @EnvironmentObject var manager: GitHubManager
    let app: SourceApp
    @State private var name = ""
    @State private var developer = ""
    @State private var description = ""
    @State private var icon = ""

    var body: some View {
        Form {
            Section("Application details") {
                TextField("Name", text:$name)
                TextField("Developer", text:$developer)
                TextField("Description", text:$description, axis:.vertical).lineLimit(3...6)
                TextField("Icon URL (HTTPS)", text:$icon)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.URL)
            }
            Section {
                Button {
                    Task {
                        await manager.changeApp(
                            bundle:app.id, name:name, developer:developer,
                            description:description, iconURL:icon
                        )
                    }
                } label: {
                    HStack {
                        if manager.busy { ProgressView().tint(Theme.cyan) }
                        Label(manager.busy ? "Saving…" : "Save Changes",systemImage:"checkmark.circle.fill")
                    }.foregroundStyle(Theme.cyan)
                }
                .disabled(manager.busy || !manager.connected)
            }
            Section {
                Text("Bundle ID: \(app.id)")
                    .font(.caption).foregroundStyle(.secondary)
                if !manager.status.isEmpty {
                    Text(manager.status).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle(app.name)
        .onAppear {
            let meta = manager.catalog[app.id] as? [String:Any] ?? [:]
            name = app.name
            developer = app.developer
            description = meta["localizedDescription"] as? String ?? ""
            icon = app.icon
        }
        .alert("Source Manager",isPresented:Binding(
            get:{manager.alertMessage != nil},
            set:{if !$0 {manager.alertMessage=nil}}
        )) {
            Button("OK",role:.cancel) { manager.alertMessage=nil }
        } message: { Text(manager.alertMessage ?? "") }
    }
}
struct DebsScreen: View {
    @EnvironmentObject var manager: GitHubManager
    @State private var importer = false
    @State private var stagedDEB: StagedSourceFile?
    @State private var publicationBaseName = ""
    @State private var pendingDelete: SourceDeb?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    SourceHeader(sileo:true)
                    HStack {
                        Label("Debian packages",systemImage:"checkmark.shield.fill")
                        Spacer()
                        Text("\(manager.debs.count) packages").foregroundStyle(.secondary)
                    }.font(.caption)
                    PrimaryButton(title:"Add DEB from Files",symbol:"plus.circle.fill") {
                        importer = true
                    }
                    .disabled(manager.busy || !manager.connected)
                    if let deb = stagedDEB {
                        VStack(alignment:.leading,spacing:12) {
                            Label(deb.name,systemImage:"shippingbox.fill")
                                .font(.headline).lineLimit(2)
                            HStack(spacing:8) {
                                TextField("Download filename",text:$publicationBaseName)
                                    .textFieldStyle(.roundedBorder)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                                Text(".deb").font(.subheadline.monospaced()).foregroundStyle(.secondary)
                            }
                            Text("Rename the downloadable DEB before publishing. Package metadata inside the DEB stays unchanged.")
                                .font(.caption).foregroundStyle(.secondary)
                            PrimaryButton(title:"Publish DEB",symbol:"arrow.up.doc.fill") {
                                if manager.publishSelectedDEB(deb,publishedName:publicationBaseName) {
                                    stagedDEB = nil
                                    publicationBaseName = ""
                                }
                            }
                            .disabled(manager.busy || !manager.connected)
                            Button("Cancel selection",role:.cancel) {
                                if let deb = stagedDEB { manager.discardStagedFiles([deb]) }
                                stagedDEB = nil
                                publicationBaseName = ""
                            }.font(.caption)
                        }
                    }
                }
                .listRowBackground(Color.white.opacity(0.055))
                Section("Published tweaks") {
                    ForEach(manager.debs) { deb in
                        HStack(spacing:13) {
                            Image(systemName:"shippingbox.fill").font(.title2).foregroundStyle(Theme.cyan)
                            VStack(alignment:.leading,spacing:5) {
                                Text(deb.filename).font(.headline).lineLimit(2)
                                Text("Sileo · Debian package").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                        }
                        .padding(.vertical,7)
                        .swipeActions(edge:.trailing,allowsFullSwipe:false) {
                            Button(role:.destructive) { pendingDelete=deb } label: {
                                Label("Delete",systemImage:"trash")
                            }
                            .disabled(manager.busy)
                        }
                    }
                }
                if manager.debs.isEmpty {
                    Text("No tweaks yet. Add a DEB from Files to publish your first package.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section {
                    Text("Swipe left to delete. You will always be asked to confirm. The repository package index is rebuilt after each change.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background)
            .navigationTitle("Sileo")
            .toolbar {
                ToolbarItem(placement:.topBarTrailing) {
                    Button { Task { await manager.refresh() } } label: { Image(systemName:"arrow.clockwise") }
                        .disabled(manager.busy)
                }
            }
            .sheet(isPresented:$importer) {
                PackageDocumentPicker(
                    kind:.deb, multiple:false,
                    onPick: { urls in
                        if let url = urls.first {
                            if let previous = stagedDEB { manager.discardStagedFiles([previous]) }
                            stagedDEB = manager.stageSelectedFile(url,expected:"deb")
                            publicationBaseName = stagedDEB.map { ($0.name as NSString).deletingPathExtension } ?? ""
                        }
                        importer = false
                    },
                    onCancel: { importer = false }
                )
            }
            .confirmationDialog("Remove \(pendingDelete?.filename ?? "package")?",
                isPresented:Binding(get:{pendingDelete != nil},set:{if !$0 {pendingDelete=nil}}),
                titleVisibility:.visible) {
                    Button("Remove from source",role:.destructive) {
                        if let deb = pendingDelete {
                            Task { await manager.removeDeb(line:deb.line) }
                        }
                        pendingDelete=nil
                    }
                    Button("Cancel",role:.cancel) { pendingDelete=nil }
                } message: {
                    Text("Removes this DEB from the Sileo source. GitHub Release assets will be retained.")
                }
            .alert("Source Manager",isPresented:Binding(
                get:{manager.alertMessage != nil},
                set:{if !$0 {manager.alertMessage=nil}}
            )) {
                Button("OK",role:.cancel) { manager.alertMessage=nil }
            } message: { Text(manager.alertMessage ?? "") }
            .safeAreaInset(edge:.bottom) { StatusPanel() }
        }
    }
}
struct SettingsScreen:View {
    @EnvironmentObject var manager:GitHubManager
    @AppStorage("githubClientID") private var clientID = ""
    @State private var tokenInput = ""
    @State private var deviceCode:DeviceCode?
    @State private var runningLogin = false
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:17) {
                    Header(title:"Settings",subtitle:"GitHub account & source details")
                    Panel {
                        Label("GitHub connection",systemImage:"person.crop.circle.badge.checkmark").font(.headline)
                        if manager.connected {
                            Label("@\(manager.username)",systemImage:"checkmark.circle.fill").foregroundStyle(Theme.cyan)
                            Button("Disconnect GitHub",role:.destructive) { manager.disconnect() }
                        } else {
                            Text("Sign in with GitHub device authorization, or connect a fine-grained access token with Contents read/write access to RBx9.github.io.")
                                .font(.caption).foregroundStyle(.secondary)
                            TextField("GitHub OAuth App Client ID",text:$clientID).textInputAutocapitalization(.never)
                                .textFieldStyle(.roundedBorder)
                            PrimaryButton(title:"Sign in with GitHub",symbol:"person.crop.circle.badge.checkmark") {
                                Task {
                                    runningLogin = true
                                    do {
                                        let code = try await manager.beginDeviceLogin(clientID:clientID)
                                        deviceCode = code
                                        try await manager.finishDeviceLogin(code,clientID:clientID)
                                        deviceCode = nil
                                    } catch { manager.status = error.localizedDescription }
                                    runningLogin = false
                                }
                            }
                            if let code = deviceCode {
                                Text("Code: \(code.user_code)").font(.title2.bold()).textSelection(.enabled)
                                Link("Authorize on GitHub",destination:URL(string:code.verification_uri)!)
                                Text("Enter this code on GitHub. This window will update after authorization.").font(.caption)
                            }
                            SecureField("Fine-grained access token",text:$tokenInput).textFieldStyle(.roundedBorder)
                            Button("Connect with access token") { Task { await manager.connect(tokenInput); tokenInput = "" } }
                                .foregroundStyle(Theme.cyan)
                        }
                    }
                    Panel {
                        Label("ESign source appearance",systemImage:"square.stack.3d.up.fill").font(.headline)
                        Text("Change the source icon by tapping its picture at the top of the ESign tab.")
                            .font(.caption).foregroundStyle(.secondary)
                        TextField("Source name",text:$manager.ipaName).textFieldStyle(.roundedBorder)
                        TextField("Description",text:$manager.ipaDescription,axis:.vertical).textFieldStyle(.roundedBorder)
                        PrimaryButton(title:"Save ESign Changes",symbol:"checkmark.circle.fill") {
                            Task { await manager.updateSourceMetadata(sileo:false,name:manager.ipaName,description:manager.ipaDescription) }
                        }
                        .disabled(manager.busy || !manager.connected)
                    }
                    Panel {
                        Label("Sileo source appearance",systemImage:"shippingbox.fill").font(.headline)
                        Text("Change the source icon by tapping its picture at the top of the Sileo tab.")
                            .font(.caption).foregroundStyle(.secondary)
                        TextField("Source name",text:$manager.sileoName).textFieldStyle(.roundedBorder)
                        TextField("Description",text:$manager.sileoDescription,axis:.vertical).textFieldStyle(.roundedBorder)
                        PrimaryButton(title:"Save Sileo Changes",symbol:"checkmark.circle.fill") {
                            Task { await manager.updateSourceMetadata(sileo:true,name:manager.sileoName,description:manager.sileoDescription) }
                        }
                        .disabled(manager.busy || !manager.connected)
                    }
                    Panel {
                        Label("Connected repository",systemImage:"point.3.connected.trianglepath.dotted").font(.headline)
                        Text(repository).font(.subheadline).foregroundStyle(.secondary)
                        Link("Open GitHub repository",destination:URL(string:"https://github.com/\(repository)")!)
                        Button("Refresh now") { Task { await manager.refresh() } }.foregroundStyle(Theme.cyan)
                        if manager.busy { ProgressView().tint(Theme.cyan) }
                        if !manager.status.isEmpty { Text(manager.status).font(.caption).foregroundStyle(.secondary) }
                    }
                }.padding()
            }.background(Theme.background)
            .alert("Source Manager",isPresented:Binding(
                get:{manager.alertMessage != nil},
                set:{if !$0 {manager.alertMessage=nil}}
            )) {
                Button("OK",role:.cancel) { manager.alertMessage=nil }
            } message: { Text(manager.alertMessage ?? "") }
        }
    }
}
