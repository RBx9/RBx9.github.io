import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
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
    @Published var hiddenBundles: Set<String> = []
    private var token = SecretStore.read()

    init() {
        if !token.isEmpty { Task { await refresh() } }
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
        await work("Saving app metadata") {
            var content = self.catalog
            guard var app = content[bundle] as? [String:Any] else { throw ManagerError.message("App not found") }
            app["name"] = name
            app["developerName"] = developer
            app["localizedDescription"] = description
            app["iconURL"] = iconURL
            content[bundle] = app
            try await self.put("ipa-source/catalog.json",data:try self.json(content))
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
    func importFile(_ url: URL, sileo: Bool) {
        let expected = sileo ? "deb" : "ipa"
        guard url.pathExtension.lowercased() == expected else {
            alertMessage = "Choose a .\(expected) file from Files."
            return
        }
        guard !busy else { status = "A source operation is already running."; return }
        let opened = url.startAccessingSecurityScopedResource()
        defer { if opened { url.stopAccessingSecurityScopedResource() } }
        let local = FileManager.default.temporaryDirectory
            .appendingPathComponent("rbx9-import-\(UUID().uuidString).\(expected)")
        do {
            var fileError: NSError?
            var readError: Error?
            // iCloud Drive and third-party providers can expose placeholder
            // security-scoped URLs. Coordinated reads retrieve the actual file.
            NSFileCoordinator(filePresenter:nil).coordinate(
                readingItemAt:url, options:[], error:&fileError
            ) { readableURL in
                do { try FileManager.default.copyItem(at:readableURL,to:local) }
                catch { readError = error }
            }
            if let fileError { throw fileError }
            if let readError { throw readError }
            guard FileManager.default.fileExists(atPath:local.path) else {
                throw ManagerError.message("Files did not provide the selected document.")
            }
            let originalName = url.lastPathComponent
            Task { await upload(stagedFile:local, originalName:originalName, sileo:sileo) }
        } catch {
            status = "Could not access selected file: \(error.localizedDescription)"
            alertMessage = status
        }
    }
    private func upload(stagedFile:URL, originalName:String, sileo:Bool) async {
        guard !busy else {
            try? FileManager.default.removeItem(at:stagedFile)
            return
        }
        busy = true
        defer {
            busy = false
            try? FileManager.default.removeItem(at:stagedFile)
        }
        do {
            let ext = sileo ? "deb" : "ipa"
            status = "Preparing \(ext.uppercased()) upload…"
            let sanitized = originalName
                .replacingOccurrences(of:"[^a-zA-Z0-9._-]",with:"-",options:.regularExpression)
            guard sanitized.lowercased().hasSuffix(".\(ext)") else {
                throw ManagerError.message("Invalid \(ext.uppercased()) filename")
            }
            let tag = "source-manager-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))"
            // A draft prevents the IPA indexing workflow from importing an
            // incomplete release that does not have its binary asset yet.
            let draft = try parse(try await api("POST","/repos/\(repository)/releases",body:try json([
                "tag_name":tag, "name":sanitized,
                "body":"Uploaded using RBx9 Source Manager",
                "draft":true, "prerelease":false
            ])))
            guard let id = draft["id"] as? Int else {
                throw ManagerError.message("GitHub did not create a draft release")
            }
            status = "Uploading \(sanitized)…"
            var components = URLComponents(string:"https://uploads.github.com/repos/\(repository)/releases/\(id)/assets")!
            components.queryItems = [URLQueryItem(name:"name",value:sanitized)]
            var req = URLRequest(url:components.url!)
            req.httpMethod = "POST"
            req.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")
            req.setValue("application/vnd.github+json",forHTTPHeaderField:"Accept")
            req.setValue("application/octet-stream",forHTTPHeaderField:"Content-Type")
            req.setValue("2022-11-28",forHTTPHeaderField:"X-GitHub-Api-Version")
            let (uploadData,response) = try await URLSession.shared.upload(for:req,fromFile:stagedFile)
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200...299).contains(code) else {
                throw ManagerError.message("Upload failed (\(code)): \(String(decoding:uploadData,as:UTF8.self).prefix(250))")
            }
            let asset = try parse(uploadData)
            guard let downloadURL = asset["browser_download_url"] as? String else {
                throw ManagerError.message("GitHub did not return an asset URL")
            }
            status = "Publishing GitHub release…"
            _ = try await api("PATCH","/repos/\(repository)/releases/\(id)",body:try json(["draft":false]))
            // Publish the binary before adding its URL to the Sileo index,
            // otherwise the builder may try to download a private draft.
            if sileo {
                status = "Adding DEB to Sileo package index…"
                let sha256 = try fileHash(stagedFile)
                let (source, _) = try await file("package-sources.txt")
                let old = String(decoding:source,as:UTF8.self).trimmingCharacters(in:.newlines)
                let row = "\(downloadURL)|\(sanitized)|\(sha256)"
                guard !old.contains(row) else {
                    throw ManagerError.message("This package is already in the source")
                }
                try await put("package-sources.txt",data:Data((old+"\n"+row+"\n").utf8))
            }
            await refresh()
            status = "Uploaded successfully. Source publishing is running; refresh your client when finished."
        } catch {
            status = error.localizedDescription
            alertMessage = error.localizedDescription
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
    @EnvironmentObject var manager: GitHubManager
    var body: some View {
        Group {
            if manager.busy || !manager.status.isEmpty {
                HStack(spacing: 10) {
                    if manager.busy { ProgressView().tint(Theme.cyan) }
                    Text(manager.status.isEmpty ? "Working…" : manager.status)
                        .font(.caption).foregroundStyle(.primary)
                    Spacer(minLength: 0)
                }
                .padding(12)
                .background(.regularMaterial)
            }
        }
    }
}
struct AppsScreen: View {
    @EnvironmentObject var manager: GitHubManager
    @State private var importer = false
    @State private var pendingDelete: SourceApp?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    SourceHeader(sileo:false)
                    HStack {
                        Label(manager.connected ? "@\(manager.username)" : "Connect in Settings", systemImage: "checkmark.icloud")
                        Spacer()
                        Text("\(manager.apps.count) apps").foregroundStyle(.secondary)
                    }
                    .font(.caption)
                    PrimaryButton(title:"Add IPA from Files", symbol:"plus.circle.fill") {
                        importer = true
                    }
                    .disabled(manager.busy || !manager.connected)
                }
                .listRowBackground(Color.white.opacity(0.055))
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
            // ESign IPA files normally have a dynamic UTType. Selecting all Files
            // items avoids iOS graying out .ipa files in the Files document picker.
            .fileImporter(isPresented:$importer,
                          allowedContentTypes:[.item],
                          allowsMultipleSelection:false) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    manager.importFile(url,sileo:false)
                case .failure(let error):
                    manager.alertMessage = error.localizedDescription
                }
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
struct AppEditor:View {
    @EnvironmentObject var manager:GitHubManager
    let app:SourceApp
    @State private var name = ""
    @State private var developer = ""
    @State private var description = ""
    @State private var icon = ""
    var body:some View {
        Form {
            Section("Application metadata") {
                TextField("Name",text:$name)
                TextField("Developer",text:$developer)
                TextField("Description",text:$description,axis:.vertical).lineLimit(3...6)
                TextField("Icon URL (HTTPS)",text:$icon).textInputAutocapitalization(.never)
            }
            Section {
                Button("Save changes") { Task { await manager.changeApp(bundle:app.id,name:name,developer:developer,description:description,iconURL:icon) } }
                    .foregroundStyle(Theme.cyan)
            }
            Section { Text("App ID: \(app.id)").font(.caption).foregroundStyle(.secondary) }
        }
        .navigationTitle(app.name)
        .onAppear {
            let meta = manager.catalog[app.id] as? [String:Any] ?? [:]
            name = app.name; developer = app.developer
            description = meta["localizedDescription"] as? String ?? ""
            icon = app.icon
        }
    }
}
struct DebsScreen: View {
    @EnvironmentObject var manager: GitHubManager
    @State private var importer = false
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
            .fileImporter(isPresented:$importer,
                          allowedContentTypes:[.item],
                          allowsMultipleSelection:false) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    manager.importFile(url,sileo:true)
                case .failure(let error):
                    manager.alertMessage = error.localizedDescription
                }
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
