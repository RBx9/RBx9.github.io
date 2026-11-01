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
            apps = catalog.compactMap { key, entry -> SourceApp? in
                guard let a = entry as? [String:Any] else { return nil }
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
            }
            if let (data,_) = try? await file("sileo-settings.json"),
               let obj = try? parse(data) {
                sileoName = obj["name"] as? String ?? sileoName
                sileoDescription = obj["description"] as? String ?? sileoDescription
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
            var value = self.catalog
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
            let remaining = kept.filter { !$0.isEmpty && !$0.hasPrefix("#") }
            guard !remaining.isEmpty else { throw ManagerError.message("The current Sileo publisher requires at least one package.") }
            try await self.put("package-sources.txt",data:Data((kept.joined(separator:"\n").trimmingCharacters(in:.newlines)+"\n").utf8))
        }
    }
    private func work(_ activity:String,_ action:() async throws -> Void) async {
        busy = true
        status = activity + "…"
        do {
            try await action()
            status = "Saved to GitHub. Publishing will finish after GitHub Actions and Pages update."
            await refresh()
        } catch { status = error.localizedDescription }
        busy = false
    }
    func updateSourceMetadata(sileo:Bool,name:String,description:String) async {
        await work("Saving source settings") {
            let path = sileo ? "sileo-settings.json" : "ipa-source/source-settings.json"
            var obj: [String:Any] = [:]
            if let (data,_) = try? await self.file(path) { obj = (try? self.parse(data)) ?? [:] }
            obj["name"] = name
            obj["description"] = description
            try await self.put(path,data:try self.json(obj))
        }
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
            } else {
                try await self.put("ipa-source/source-icon.png",data:png)
                let path = "ipa-source/source-settings.json"
                var obj: [String:Any] = [:]
                if let (data,_) = try? await self.file(path) { obj = (try? self.parse(data)) ?? [:] }
                obj["iconURL"] = "https://rbx9.github.io/ipa-source/source-icon.png?v=\(Int(Date().timeIntervalSince1970))"
                try await self.put(path,data:try self.json(obj))
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
    func upload(_ sourceURL:URL,sileo:Bool) async {
        busy = true
        defer { busy = false }
        let accessed = sourceURL.startAccessingSecurityScopedResource()
        defer { if accessed { sourceURL.stopAccessingSecurityScopedResource() } }
        let ext = sileo ? "deb" : "ipa"
        guard sourceURL.pathExtension.lowercased() == ext else { status = "Please select a .\(ext) file"; return }
        do {
            status = "Preparing .\(ext) upload…"
            let temp = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString+"."+ext)
            try FileManager.default.copyItem(at:sourceURL,to:temp)
            defer { try? FileManager.default.removeItem(at:temp) }
            let name = sourceURL.lastPathComponent
            let safe = name.replacingOccurrences(of:"[^a-zA-Z0-9._-]",with:"-",options:.regularExpression)
            let tag = "source-manager-\(Int(Date().timeIntervalSince1970))-\(UUID().uuidString.prefix(8))"
            let draft = try parse(try await api("POST","/repos/\(repository)/releases",body:try json([
                "tag_name":tag, "name":safe, "body":"Uploaded using RBx9 Source Manager",
                "draft":true, "prerelease":false
            ])))
            guard let id = draft["id"] as? Int else { throw ManagerError.message("GitHub did not create a draft release") }
            status = "Uploading \(name) to GitHub…"
            guard var components = URLComponents(string:"https://uploads.github.com/repos/\(repository)/releases/\(id)/assets") else {
                throw ManagerError.message("Invalid GitHub upload URL")
            }
            components.queryItems = [URLQueryItem(name:"name",value:name)]
            var req = URLRequest(url:components.url!)
            req.httpMethod = "POST"
            req.setValue("Bearer \(token)",forHTTPHeaderField:"Authorization")
            req.setValue("application/vnd.github+json",forHTTPHeaderField:"Accept")
            req.setValue("application/octet-stream",forHTTPHeaderField:"Content-Type")
            req.setValue("2022-11-28",forHTTPHeaderField:"X-GitHub-Api-Version")
            let (uploadData,response) = try await URLSession.shared.upload(for:req,fromFile:temp)
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200...299).contains(code) else {
                throw ManagerError.message("Upload failed (\(code)): \(String(decoding:uploadData,as:UTF8.self).prefix(250))")
            }
            let asset = try parse(uploadData)
            guard let downloadURL = asset["browser_download_url"] as? String else {
                throw ManagerError.message("Missing download URL")
            }
            status = "Publishing release…"
            _ = try await api("PATCH","/repos/\(repository)/releases/\(id)",body:try json(["draft":false]))
            if sileo {
                let sha256 = try fileHash(temp)
                let (source,_) = try await file("package-sources.txt")
                let old = String(decoding:source,as:UTF8.self).trimmingCharacters(in:.newlines)
                let row = "\(downloadURL)|\(safe)|\(sha256)"
                if !old.contains(row) { try await put("package-sources.txt",data:Data((old+"\n"+row+"\n").utf8)) }
            }
            status = "Release uploaded. GitHub Actions is updating the \(sileo ? "Sileo" : "ESign") source."
            await refresh()
        } catch { status = error.localizedDescription }
    }
}

struct Theme {
    static let cyan = Color(red:0.12,green:0.82,blue:0.98)
    static let background = Color(red:0.045,green:0.065,blue:0.11)
}
struct Panel<Content:View>:View {
    @ViewBuilder let content:Content
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
struct AppsScreen:View {
    @EnvironmentObject var manager:GitHubManager
    @State private var importer = false
    @State private var pendingDelete:SourceApp?
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:17) {
                    Header(title:"ESign Source",subtitle:"Manage your iOS app library")
                    Panel {
                        HStack {
                            Image(systemName:"checkmark.icloud").foregroundStyle(Theme.cyan)
                            Text(manager.connected ? "Linked to @\(manager.username)" : "Sign in from Settings")
                            Spacer()
                            Text("\(manager.apps.count) apps").foregroundStyle(.secondary)
                        }.font(.footnote)
                        PrimaryButton(title:"Add IPA",symbol:"plus.circle.fill") { importer = true }
                    }
                    ForEach(manager.apps) { app in
                        NavigationLink {
                            AppEditor(app:app)
                        } label: {
                            HStack(spacing:14) {
                                AsyncImage(url:URL(string:app.icon)) { image in image.resizable().scaledToFill() }
                                    placeholder: { Image(systemName:"app.fill").resizable().scaledToFit().padding(12) }
                                    .frame(width:52,height:52).background(.white.opacity(0.1)).clipShape(RoundedRectangle(cornerRadius:12))
                                VStack(alignment:.leading,spacing:4) {
                                    Text(app.name).font(.headline)
                                    Text(app.id).font(.caption2).lineLimit(1).foregroundStyle(.secondary)
                                    Text("v\(app.version) · \(app.developer)").font(.caption).foregroundStyle(Theme.cyan)
                                }
                                Spacer()
                                Image(systemName:"chevron.right").foregroundStyle(.secondary)
                            }
                            .padding(14).background(.white.opacity(0.055),in:RoundedRectangle(cornerRadius:17))
                        }.buttonStyle(.plain)
                        .contextMenu {
                            Button(role:.destructive) { pendingDelete = app } label: { Label("Remove listing",systemImage:"trash") }
                        }
                    }
                    Text("Changes appear after the publishing workflow completes. Refresh ESign to fetch the new catalog.")
                        .font(.footnote).foregroundStyle(.secondary).padding(.bottom,30)
                }.padding()
            }
            .background(Theme.background)
            .toolbar { ToolbarItem(placement:.topBarTrailing) { Button { Task { await manager.refresh() } } label: { Image(systemName:"arrow.clockwise") } } }
            .fileImporter(isPresented:$importer,allowedContentTypes:[UTType(filenameExtension:"ipa") ?? .data]) { result in
                if case .success(let url) = result { Task { await manager.upload(url,sileo:false) } }
                else if case .failure(let error) = result { manager.status = error.localizedDescription }
            }
            .alert("Remove listing?",isPresented:Binding(get:{pendingDelete != nil},set:{if !$0 {pendingDelete=nil}})) {
                Button("Cancel",role:.cancel) {pendingDelete=nil}
                Button("Remove",role:.destructive) { if let a = pendingDelete { Task { await manager.removeApp(bundle:a.id) } }; pendingDelete=nil }
            } message: { Text("This removes the app from the source catalog. It does not delete existing GitHub release assets.") }
            .safeAreaInset(edge:.bottom) { statusView }
        }
    }
    private var statusView:some View {
        Group { if !manager.status.isEmpty { Text(manager.status).font(.caption).frame(maxWidth:.infinity).padding(10).background(.regularMaterial) } }
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
struct DebsScreen:View {
    @EnvironmentObject var manager:GitHubManager
    @State private var importer = false
    @State private var pendingDelete:SourceDeb?
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:17) {
                    Header(title:"Sileo Source",subtitle:"Publish and manage jailbreak tweaks")
                    Panel {
                        HStack {
                            Label("Verified Debian packages",systemImage:"checkmark.shield.fill").foregroundStyle(Theme.cyan)
                            Spacer()
                            Text("\(manager.debs.count)")
                        }.font(.footnote)
                        PrimaryButton(title:"Add DEB",symbol:"plus.circle.fill") { importer = true }
                    }
                    ForEach(manager.debs) { deb in
                        HStack(spacing:14) {
                            Image(systemName:"shippingbox.fill").font(.title2).foregroundStyle(Theme.cyan)
                            VStack(alignment:.leading,spacing:5) {
                                Text(deb.filename).font(.headline).lineLimit(2)
                                Text("Published through the Sileo index").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button(role:.destructive) { pendingDelete=deb } label: { Image(systemName:"trash").foregroundStyle(.red) }
                        }.padding(16).background(.white.opacity(0.055),in:RoundedRectangle(cornerRadius:17))
                    }
                    Text("New .deb uploads are hashed and added to package-sources.txt. GitHub Actions rebuilds Packages, Packages.gz, Packages.bz2, and Release.")
                        .font(.footnote).foregroundStyle(.secondary)
                }.padding()
            }
            .background(Theme.background)
            .toolbar { ToolbarItem(placement:.topBarTrailing) { Button { Task { await manager.refresh() } } label: { Image(systemName:"arrow.clockwise") } } }
            .fileImporter(isPresented:$importer,allowedContentTypes:[UTType(filenameExtension:"deb") ?? .data]) { result in
                if case .success(let url) = result { Task { await manager.upload(url,sileo:true) } }
                else if case .failure(let error) = result { manager.status = error.localizedDescription }
            }
            .alert("Remove package?",isPresented:Binding(get:{pendingDelete != nil},set:{if !$0 {pendingDelete=nil}})) {
                Button("Cancel",role:.cancel) {pendingDelete=nil}
                Button("Remove",role:.destructive) { if let d = pendingDelete { Task { await manager.removeDeb(line:d.line) } }; pendingDelete=nil }
            } message: { Text("The package will disappear after the Sileo index rebuild. The release asset will remain stored on GitHub.") }
            .safeAreaInset(edge:.bottom) {
                if !manager.status.isEmpty { Text(manager.status).font(.caption).frame(maxWidth:.infinity).padding(10).background(.regularMaterial) }
            }
        }
    }
}
struct SettingsScreen:View {
    @EnvironmentObject var manager:GitHubManager
    @AppStorage("githubClientID") private var clientID = ""
    @State private var tokenInput = ""
    @State private var deviceCode:DeviceCode?
    @State private var runningLogin = false
    @State private var ipaName = ""
    @State private var ipaDescription = ""
    @State private var sileoName = ""
    @State private var sileoDescription = ""
    @State private var photoIPA:PhotosPickerItem?
    @State private var photoSileo:PhotosPickerItem?
    var body:some View {
        NavigationStack {
            ScrollView {
                VStack(alignment:.leading,spacing:17) {
                    Header(title:"Settings",subtitle:"GitHub account & source appearance")
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
                        TextField("Source name",text:$ipaName).textFieldStyle(.roundedBorder)
                        TextField("Description",text:$ipaDescription,axis:.vertical).textFieldStyle(.roundedBorder)
                        PhotosPicker(selection:$photoIPA,matching:.images) {
                            Label("Change ESign source icon",systemImage:"photo.badge.plus").foregroundStyle(Theme.cyan)
                        }
                        PrimaryButton(title:"Save ESign appearance",symbol:"checkmark") {
                            Task { await manager.updateSourceMetadata(sileo:false,name:ipaName,description:ipaDescription) }
                        }
                    }
                    Panel {
                        Label("Sileo source appearance",systemImage:"shippingbox.fill").font(.headline)
                        TextField("Source name",text:$sileoName).textFieldStyle(.roundedBorder)
                        TextField("Description",text:$sileoDescription,axis:.vertical).textFieldStyle(.roundedBorder)
                        PhotosPicker(selection:$photoSileo,matching:.images) {
                            Label("Change Sileo source icon",systemImage:"photo.badge.plus").foregroundStyle(Theme.cyan)
                        }
                        PrimaryButton(title:"Save Sileo appearance",symbol:"checkmark") {
                            Task { await manager.updateSourceMetadata(sileo:true,name:sileoName,description:sileoDescription) }
                        }
                    }
                    Panel {
                        Label("Connected repository",systemImage:"point.3.connected.trianglepath.dotted").font(.headline)
                        Text(repository).font(.subheadline).foregroundStyle(.secondary)
                        Link("Open GitHub repository",destination:URL(string:"https://github.com/\(repository)")!)
                        Button("Refresh now") { Task { await manager.refresh(); syncFields() } }.foregroundStyle(Theme.cyan)
                        if manager.busy { ProgressView().tint(Theme.cyan) }
                        if !manager.status.isEmpty { Text(manager.status).font(.caption).foregroundStyle(.secondary) }
                    }
                }.padding()
            }.background(Theme.background)
            .onAppear { syncFields() }
            .onChange(of:photoIPA) { item in
                guard let item else { return }
                Task { if let data = try? await item.loadTransferable(type:Data.self) { await manager.updateSourceIcon(sileo:false,imageData:data) } }
            }
            .onChange(of:photoSileo) { item in
                guard let item else { return }
                Task { if let data = try? await item.loadTransferable(type:Data.self) { await manager.updateSourceIcon(sileo:true,imageData:data) } }
            }
        }
    }
    private func syncFields() {
        ipaName=manager.ipaName
        ipaDescription=manager.ipaDescription
        sileoName=manager.sileoName
        sileoDescription=manager.sileoDescription
    }
}
