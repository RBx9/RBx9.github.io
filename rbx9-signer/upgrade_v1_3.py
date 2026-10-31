#!/usr/bin/env python3
# RBx9 v1.3.0: reversible dylib management, safe Library organization,
# swipe-to-edit, scoped empty states and optional direct installation handoff.
# Feather and derivative modifications remain subject to GPL-3.0.
from pathlib import Path
root=Path("feather"); app=root/"Feather"
def edit(rel, old, new, count=1):
 p=root/rel
 s=p.read_text()
 n=s.count(old)
 if n!=count: raise RuntimeError(f"{rel}: {n} anchors (expected {count}) for {old[:90]!r}")
 p.write_text(s.replace(old,new,count))
 print("RBx9 v1.3:",rel)
edit("Feather.xcconfig","FEATHER_PROJECT_VERSION=1.2.1","FEATHER_PROJECT_VERSION=1.3.0")
# Keep the stored LC list (including disabled dylibs) INSIDE the signed .app so
# it follows the package through re-signing. Load commands can be removed from
# the Mach-O executable while the dylib files and inventory remain available.
(app/"Backend/Storage/RBx9DylibArchive.swift").write_text(r'''// SPDX-License-Identifier: GPL-3.0-only
import Foundation
import Zsign

enum RBx9DylibArchive {
    private static let filename = "RBx9DylibState.plist"

    private struct Inventory: Codable {
        var knownPaths: [String] = []
        var disabledPaths: [String] = []
        var version: Int = 1
    }

    private static func inventoryURL(for app: URL) -> URL {
        app.appendingPathComponent(filename)
    }

    private static func inventory(for app: URL) -> Inventory {
        guard let data = try? Data(contentsOf: inventoryURL(for: app)),
              let item = try? PropertyListDecoder().decode(Inventory.self, from: data)
        else { return Inventory() }
        return item
    }

    private static func executable(for app: URL) -> URL? {
        Bundle(url: app)?.executableURL
    }

    private static func editablePath(_ path: String) -> Bool {
        path.hasPrefix("@executable_path/") || path.hasPrefix("@rpath/")
    }

    static func loaded(in app: URL) -> Set<String> {
        guard let executable = executable(for: app) else { return [] }
        return Set(Zsign.listDylibs(appExecutable: executable.path)
            .map { $0 as String }.filter(editablePath))
    }

    // Also recover loose dylibs from apps signed with earlier versions.
    // Never delete these files when a toggle is switched off.
    static func paths(in app: URL) -> [String] {
        let currentlyLoaded = loaded(in: app)
        var result = currentlyLoaded.union(inventory(for: app).knownPaths)
        let folders: [(String, URL)] = [
            ("Frameworks", app.appendingPathComponent("Frameworks")),
            ("", app)
        ]
        for (folder, directory) in folders {
            guard let files = try? FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: [.isRegularFileKey],
                options: [.skipsHiddenFiles]) else { continue }
            for file in files where file.pathExtension.lowercased() == "dylib" {
                guard (try? file.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true
                else { continue }
                let tail = folder.isEmpty ? file.lastPathComponent : folder + "/" + file.lastPathComponent
                let rootPath = "@executable_path/" + tail
                let rpath = "@rpath/" + file.lastPathComponent
                // Prefer an existing code path or historical inventory to avoid
                // inventing multiple representations for one binary.
                if !result.contains(rootPath) && !result.contains(rpath) {
                    result.insert(rootPath)
                }
            }
        }
        return result.filter(editablePath).sorted()
    }

    static func disabled(in app: URL) -> [String] {
        let current = loaded(in: app)
        let remembered = Set(inventory(for: app).disabledPaths)
        // A historical file without a load command should start disabled,
        // so the on/off UI reflects what will actually be signed.
        return paths(in: app).filter { remembered.contains($0) || !current.contains($0) }
    }

    private static func retainedFile(for path: String, app: URL) -> URL? {
        var files: [URL] = []
        if path.hasPrefix("@executable_path/") {
            let tail = String(path.dropFirst("@executable_path/".count))
            guard !tail.split(separator: "/").contains("..") else { return nil }
            files = [app.appendingPathComponent(tail)]
        } else if path.hasPrefix("@rpath/") {
            let tail = String(path.dropFirst("@rpath/".count))
            guard !tail.split(separator: "/").contains("..") else { return nil }
            files = [
                app.appendingPathComponent("Frameworks").appendingPathComponent(tail),
                app.appendingPathComponent(tail)
            ]
        }
        return files.first(where: { FileManager.default.fileExists(atPath: $0.path) })
    }

    enum ArchiveError: LocalizedError {
        case cannotRestore(String)
        var errorDescription: String? {
            if case let .cannotRestore(path) = self {
                return "Could not re-enable dylib \(path). Its load command could not be restored."
            }
            return "Could not restore the dylib."
        }
    }

    static func applyAndStore(
        in app: URL,
        disabledPaths: [String],
        previouslyLoaded: Set<String>
    ) throws {
        guard let executable = executable(for: app) else { return }
        let prior = inventory(for: app)
        let requestedOff = Set(disabledPaths.filter(editablePath))
        let originalNames = previouslyLoaded.union(prior.knownPaths).union(requestedOff)
        let allKnown = originalNames.union(paths(in: app).filter { path in
            // A previous @rpath/Foo.dylib must not be rediscovered as a
            // separate @executable_path/Frameworks/Foo.dylib.
            let isFrameworkRoot = path.hasPrefix("@executable_path/Frameworks/")
            return !isFrameworkRoot || !originalNames.contains("@rpath/" + (path as NSString).lastPathComponent)
        })
        // ZsignHandler already removes load commands in requestedOff.
        // Restore previously disabled load commands when they are switched ON.
        for path in allKnown.sorted() where !requestedOff.contains(path) {
            guard !loaded(in: app).contains(path) else { continue }
            guard retainedFile(for: path, app: app) != nil else {
                // Do not re-create a reference to a missing binary.
                continue
            }
            guard Zsign.injectDyLib(appExecutable: executable.path, with: path) else {
                throw ArchiveError.cannotRestore(path)
            }
        }
        let state = Inventory(
            knownPaths: allKnown.sorted(),
            disabledPaths: Array(requestedOff).sorted(),
            version: 1
        )
        let data = try PropertyListEncoder().encode(state)
        try data.write(to: inventoryURL(for: app), options: .atomic)
    }
}
''')
# On each Signing screen open, prefill the status of every existing dylib,
# not global options from a different application. This is non-destructive.
edit("Feather/Views/Signing/SigningView.swift",
'''\t\t.onAppear {
\t\t\t// ppq protection''',
'''        .onAppear {
            if let base = Storage.shared.getAppDirectory(for: app) {
                _temporaryOptions.disInjectionFiles = RBx9DylibArchive.disabled(in: base)
            }
			// ppq protection''')
# An already-disabled path has no Mach-O load command, so only send currently
# loaded paths to the Zsign removal function. Do not error on archived entries.
edit("Feather/Utilities/Handlers/ZsignHandler.swift",
     '''if !Zsign.removeDylibs(appExecutable: execPath, using: _options.disInjectionFiles) {''',
     '''let loaded = Set(Zsign.listDylibs(appExecutable: execPath).map { $0 as String })
        let toRemove = _options.disInjectionFiles.filter { loaded.contains($0) }
        guard !toRemove.isEmpty else { return }
        if !Zsign.removeDylibs(appExecutable: execPath, using: toRemove) {''')

# On the editor screen, show current AND previously disabled dylibs.
p=app/"Views/Signing/Shared/SigningDylibView.swift"
s=p.read_text()
a=s.index('\t\tlet bundle = Bundle(url: path)',s.index('private func _loadDylibs()'))
b=s.index('\n\t}',a)
s=s[:a]+'''        let current = RBx9DylibArchive.loaded(in: path)
        let all = RBx9DylibArchive.paths(in: path)
        _dylibs = all
        _hiddenDylibCount = 0
        if var currentOptions = options {
            // Old disabled references remain visible after signing; the binary
            // alone no longer contains them, so recover their OFF state.
            let switchedOff = Set(RBx9DylibArchive.disabled(in: path))
            let existingChanges = Set(currentOptions.disInjectionFiles)
            currentOptions.disInjectionFiles = Array(switchedOff.union(existingChanges)).sorted()
            options = currentOptions
        }
        _ = current
'''+s[b:]
p.write_text(s)
edit("Feather/Utilities/Handlers/SigningHandler.swift",
'''try await handler.disinject()
		
		if''',
'''let originalPaths = RBx9DylibArchive.loaded(in: movedAppPath)
        try await handler.disinject()
        try RBx9DylibArchive.applyAndStore(
            in: movedAppPath,
            disabledPaths: _options.disInjectionFiles,
            previouslyLoaded: originalPaths
        )
		
		if''')
# Keep input files on disk and preserve signing options if a user returns to
# the same app. All editable load commands are managed before re-signing.

# Hide imported apps from Sign once the matching signed app is installed.
# Only hide CoreData rows; original archives and certificates are never deleted.
p=app/"Backend/Storage/RBx9ListHistory.swift"
s=p.read_text()
marker='''    static func collapseOlderSignedRows(keepingUUID: String?) {'''
if s.count(marker)!=1:raise RuntimeError("Missing RBx9ListHistory method")
method='''    static func hideImportedAfterInstallation(bundleID: String?) {
        guard let bundleID, !bundleID.isEmpty else { return }
        let req = NSFetchRequest<Imported>(entityName: "Imported")
        guard let imported = try? Storage.shared.context.fetch(req) else { return }
        let ids = imported.compactMap { item -> String? in
            guard item.identifier == bundleID else { return nil }
            return item.uuid
        }
        guard !ids.isEmpty else { return }
        let key = "rbx9.hiddenInstalledImportedUUIDs"
        var hidden = Set((UserDefaults.standard.string(forKey: key) ?? "")
            .split(separator: "|").map(String.init))
        hidden.formUnion(ids)
        UserDefaults.standard.set(hidden.sorted().joined(separator: "|"), forKey: key)
    }

'''
p.write_text(s.replace(marker,method+marker))
# Show installation progress and toggle absence from Sign on completed event,
# but only when the installer reports success.
edit("Feather/Views/Library/Install/InstallPreviewView.swift",
'''RBx9ListHistory.collapseOlderSignedRows(keepingUUID: app.uuid)''',
'''RBx9ListHistory.collapseOlderSignedRows(keepingUUID: app.uuid)
                    RBx9ListHistory.hideImportedAfterInstallation(bundleID: app.identifier)''')
p=app/"Views/Library/LibraryView.swift"
s=p.read_text()
needle='''@AppStorage("rbx9.hiddenSignedUUIDs") private var _hiddenSignedUUIDs = ""'''
if s.count(needle)!=1:raise RuntimeError("Missing library state")
s=s.replace(needle,needle+'''
    @AppStorage("rbx9.hiddenInstalledImportedUUIDs") private var _hiddenImportedUUIDs = ""
    @AppStorage("rbx9.showInstalledInSignTab") private var _showInstalledInSignTab = false
    @State private var _selectedDylibAppPresenting: AnyApp?''')
old='''private var _filteredImportedApps: [Imported] {
		filteredAndSortedApps(from: _importedApps)
	}'''
new='''private var _filteredImportedApps: [Imported] {
        let hidden = Set(_hiddenImportedUUIDs.split(separator: "|").map(String.init))
        return filteredAndSortedApps(from: _importedApps).filter { imported in
            _showInstalledInSignTab || !hidden.contains(imported.uuid ?? "")
        }
    }'''
if s.count(old)!=1:raise RuntimeError("Missing imported filter")
s=s.replace(old,new)
# Give LibraryCellView the same swipe-to-editor binding in both sections.
needle='''selectedSigningAppPresenting: $_selectedSigningAppPresenting,
								selectedInstallAppPresenting: $_selectedInstallAppPresenting,'''
repl='''selectedSigningAppPresenting: $_selectedSigningAppPresenting,
                                selectedDylibAppPresenting: $_selectedDylibAppPresenting,
								selectedInstallAppPresenting: $_selectedInstallAppPresenting,'''
if s.count(needle)!=2:raise RuntimeError(f"LibraryCellView bindings mismatch, {s.count(needle)}")
s=s.replace(needle,repl)
needle='''.fullScreenCover(item: $_selectedSigningAppPresenting) { app in
				SigningView(app: app.base)
					.compatNavigationTransition(id: app.base.uuid ?? "", ns: _namespace)
			}'''
repl=needle+'''
            .fullScreenCover(item: $_selectedDylibAppPresenting) { app in
                SigningView(app: app.base, openDylibEditor: true)
            }'''
if s.count(needle)!=1:raise RuntimeError("Missing editor cover")
s=s.replace(needle,repl)
# Replace floating overlay with an inline, centered empty state section inside
# the correct tab. This avoids "No Apps" overlaid on valid Library content.
a=s.index('\n\t\t\t.overlay {\n\t\t\t\tif\n\t\t\t\t\t_filteredSignedApps.isEmpty,')
b=s.index('\n\t\t\t.toolbar {',a)
s=s[:a]+s[b:]
needle='''				}
			}
			.searchable(text: $_searchText'''
if s.count(needle)!=1:raise RuntimeError("Library empty-state insertion anchor missing")
s=s.replace(needle,'''                }
                if (_rbx9LibraryLayout == 1 &&
                    (_rbx9LibraryTab == 0 ? _filteredImportedApps.isEmpty : _filteredSignedApps.isEmpty)) ||
                   (_rbx9LibraryLayout == 0 &&
                    _filteredImportedApps.isEmpty && _filteredSignedApps.isEmpty) {
                    Section {
                        VStack(spacing: 10) {
                            Image(systemName: _rbx9LibraryTab == 1 ? "square.and.arrow.down" : "square.stack.3d.up")
                                .font(.system(size: 29, weight: .light))
                                .foregroundStyle(Color.accentColor)
                            Text(_rbx9LibraryTab == 1 ? "No apps ready to install" : "No apps to sign")
                                .font(.headline)
                            Text(_rbx9LibraryTab == 1
                                ? "Signed apps will appear here."
                                : "Import an IPA to get started.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    }
                }
			}
			.searchable(text: $_searchText''')
p.write_text(s)

p=app/"Views/Library/LibraryCellView.swift"
s=p.read_text()
needle='''@Binding var selectedSigningAppPresenting: AnyApp?'''
if s.count(needle)!=1:raise RuntimeError("Missing signed app binding")
s=s.replace(needle,needle+'''
    @Binding var selectedDylibAppPresenting: AnyApp?''')
needle='.swipeActions {'
if s.count(needle)!=1:raise RuntimeError("Missing swipe action")
s=s.replace(needle,'''        .swipeActions(edge: .leading, allowsFullSwipe: true) {
            if !isEditing {
                Button {
                    selectedDylibAppPresenting = AnyApp(base: app)
                } label: {
                    Label("Dylibs", systemImage: "puzzlepiece.extension.fill")
                }
                .tint(Color(red: 0.16, green: 0.75, blue: 0.83))
            }
        }
.swipeActions {''')
p.write_text(s)
# Open existing-dylibs editor directly when launched from leading swipe.
p=app/"Views/Signing/SigningView.swift"
s=p.read_text()
needle='''@State private var _isSigning = false'''
if s.count(needle)!=1:raise RuntimeError("SigningView state changed")
s=s.replace(needle,needle+'''
    @State private var _showSwipeDylibEditor = false
    private let _openDylibEditorOnLaunch: Bool''')
needle='''init(app: AppInfoPresentable) {
		self.app = app'''
if s.count(needle)!=1:raise RuntimeError("SigningView initializer changed")
s=s.replace(needle,'''init(app: AppInfoPresentable, openDylibEditor: Bool = false) {
        self._openDylibEditorOnLaunch = openDylibEditor
		self.app = app''')
needle='''.sheet(isPresented: $_isAltPickerPresenting) { SigningAlternativeIconView'''
if s.count(needle)!=1:raise RuntimeError("SigningView sheets changed")
s=s.replace(needle,'''    .sheet(isPresented: $_showSwipeDylibEditor) {
                NavigationStack {
                    SigningDylibView(
                        app: app,
                        options: $_temporaryOptions.optional(),
                        onApply: { shouldInstall in
                            _showSwipeDylibEditor = false
                            _start(installAfterSigning: shouldInstall)
                        }
                    )
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("Done") { _showSwipeDylibEditor = false }
                        }
                    }
                }
            }
			.sheet(isPresented: $_isAltPickerPresenting) { SigningAlternativeIconView''')
needle='''        .onAppear {
            if let base = Storage.shared.getAppDirectory(for: app) {'''
if s.count(needle)!=1:raise RuntimeError("Signing onAppear changed")
s=s.replace(needle,'''        .onAppear {
            if _openDylibEditorOnLaunch {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                    _showSwipeDylibEditor = true
                }
            }
            if let base = Storage.shared.getAppDirectory(for: app) {''')
p.write_text(s)
# Add a setting to restore previous imported app items if user wants to re-sign.
p=app/"Views/Settings/Appearance/AppearanceView.swift"
s=p.read_text()
needle='''@AppStorage("rbx9.libraryLayout") private var _rbx9LibraryLayout = 1'''
if s.count(needle)!=1:raise RuntimeError("Appearance controls missing")
s=s.replace(needle,needle+'''
    @AppStorage("rbx9.showInstalledInSignTab") private var _showInstalledInSignTab = false''')
needle='''NBSection("Library Layout") {
                Picker("Layout", selection: $_rbx9LibraryLayout) {'''
if s.count(needle)!=1:raise RuntimeError("Appearance Library section changed")
s=s.replace(needle,'''NBSection("Library Layout") {
                Toggle("Show previously installed apps in Sign",
                       isOn: $_showInstalledInSignTab)
                Picker("Layout", selection: $_rbx9LibraryLayout) {''')
p.write_text(s)
# Semi-Local uses Safari only to redirect to an itms-services:// install URL.
# Try opening that same link directly first. iOS may still require the OS
# security/confirmation prompt; no third-party app can auto-approve it.
p=app/"Views/Library/Install/InstallPreviewView.swift"
s=p.read_text()
needle='''@State private var _isWebviewPresenting = false'''
if s.count(needle)!=1:raise RuntimeError("Installer webview state changed")
s=s.replace(needle,needle+'''
    @AppStorage("rbx9.skipSafariInstallPage") private var _skipSafariInstallPage = true''')
needle='''} else if _serverMethod == 1 {
						_isWebviewPresenting = true
					}'''
new='''} else if _serverMethod == 1 {
                        if _skipSafariInstallPage,
                           let directLink = URL(string: installer.iTunesLinkExternal) {
                            UIApplication.shared.open(directLink, options: [:]) { didOpen in
                                if !didOpen { _isWebviewPresenting = true }
                            }
                        } else {
                            _isWebviewPresenting = true
                        }
                    }'''
if s.count(needle)!=1:raise RuntimeError("Semi-local handler changed")
s=s.replace(needle,new)
p.write_text(s)
p=app/"Views/Settings/Installation/Server & SSL/ServerView.swift"
s=p.read_text()
needle='''@AppStorage("Feather.serverMethod") private var _serverMethod: Int = 1'''
if s.count(needle)!=1:raise RuntimeError("SemiLocal default setting missing")
s=s.replace(needle,needle+'''
    @AppStorage("rbx9.skipSafariInstallPage") private var _skipSafariInstallPage = true''')
needle='''Toggle(.localized("Only use localhost address"), systemImage: "lifepreserver", isOn: $_ipFix)
					.disabled(_serverMethod != 1)'''
if s.count(needle)!=1:raise RuntimeError("Server settings controls changed")
s=s.replace(needle,needle+'''
                if _serverMethod == 1 {
                    Toggle("Try direct installation link (skip web page)",
                           isOn: $_skipSafariInstallPage)
                }''')
p.write_text(s)
print("RBx9 v1.3 UX and reversible dylib inventory completed")
