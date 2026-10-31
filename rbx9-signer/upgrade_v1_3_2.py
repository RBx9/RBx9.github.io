#!/usr/bin/env python3
# RBx9 v1.3.2: swipe-left Delete in Manage Existing Dylibs, with undo.
# Deletion is STAGED, applied only to a working copy during the next Sign.
# The signed app removes both Mach-O reference and embedded binary.
# Turning OFF a toggle remains reversible and does not delete files.
from pathlib import Path

root = Path("feather")
app = root / "Feather"

def change(rel, before, after):
    path = root / rel
    source = path.read_text()
    n = source.count(before)
    if n != 1:
        raise RuntimeError(f"{rel}: expected one anchor, found {n}: {before[:95]!r}")
    path.write_text(source.replace(before, after, 1))
    print("RBx9 v1.3.2:", rel)

change("Feather.xcconfig",
       "FEATHER_PROJECT_VERSION=1.3.1",
       "FEATHER_PROJECT_VERSION=1.3.2")

# A distinct deletion list prevents an ordinary Off toggle from deleting files.
# Existing JSON options load because OptionsManager merges saved values into defaults.
change("Feather/Backend/Observable/OptionsManager.swift",
       '''var disInjectionFiles: [String]
''',
       '''var disInjectionFiles: [String]
    /// Embedded Mach-O paths explicitly queued for deletion in next signed IPA.
    var rbx9DeletedDylibPaths: [String]
''')
change("Feather/Backend/Observable/OptionsManager.swift",
       '''disInjectionFiles: [],
''',
       '''disInjectionFiles: [],
        rbx9DeletedDylibPaths: [],
''')

# Keep deletion strictly inside the copied .app bundle, and only accept a
# dylib or framework folder known to exist. Never delete arbitrary paths.
p = app / "Backend/Storage/RBx9DylibArchive.swift"
s = p.read_text()
anchor = '''    enum ArchiveError: LocalizedError {'''
if s.count(anchor) != 1:
    raise RuntimeError("RBx9 dylib archive missing ArchiveError")
utility = '''    /// Return a safe app-relative file path for the next signing operation.
    /// The original imported IPA remains untouched.
    static func relativeRemovalPath(for loadPath: String, in app: URL) -> String? {
        guard let file = retainedFile(for: loadPath, app: app) else { return nil }
        let appRoot = app.standardizedFileURL.path
        let resolved = file.standardizedFileURL.path
        guard resolved.hasPrefix(appRoot + "/") else { return nil }
        let relative = String(resolved.dropFirst(appRoot.count + 1))
        let parts = relative.split(separator: "/")
        if let frameworkIndex = parts.firstIndex(where: { $0.hasSuffix(".framework") }) {
            let framework = parts.prefix(through: frameworkIndex).joined(separator: "/")
            // Framework directories must belong to the embedded Frameworks folder.
            return framework.hasPrefix("Frameworks/") ? framework : nil
        }
        guard relative.hasSuffix(".dylib"), !relative.isEmpty else { return nil }
        return relative
    }

'''
s = s.replace(anchor, utility + anchor, 1)
old = '''disabledPaths: [String],
        previouslyLoaded: Set<String>'''
new = '''disabledPaths: [String],
        previouslyLoaded: Set<String>,
        deletedPaths: [String]'''
if s.count(old)!=1: raise RuntimeError("RBx9 archive applyAndStore signature missing")
s=s.replace(old,new,1)
old='''let requestedOff = Set(disabledPaths.filter(editablePath))
        let originalNames = previouslyLoaded.union(prior.knownPaths).union(requestedOff)'''
new='''let deleted = Set(deletedPaths.filter(editablePath))
        let requestedOff = Set(disabledPaths.filter(editablePath)).subtracting(deleted)
        let originalNames = previouslyLoaded.union(prior.knownPaths)
            .union(requestedOff).subtracting(deleted)'''
if s.count(old)!=1:raise RuntimeError("Missing archive state building code")
s=s.replace(old,new,1)
old='''        // ZsignHandler already removes load commands in requestedOff.'''
new='''        // Do not resurrect anything deleted from the new signed IPA.
        let keptPaths = allKnown.subtracting(deleted)
        // ZsignHandler already removes load commands in requestedOff.'''
if s.count(old)!=1:raise RuntimeError("Archive signing anchor missing")
s=s.replace(old,new,1)
s=s.replace('''for path in allKnown.sorted() where !requestedOff.contains(path) {''',
            '''for path in keptPaths.sorted() where !requestedOff.contains(path) {''',1)
s=s.replace('''knownPaths: allKnown.sorted(),''','''knownPaths: keptPaths.sorted(),''',1)
p.write_text(s)

# Ensure the load reference is removed even when the associated binary is
# deleted first by SigningHandler._removeFiles.
p = app / "Utilities/Handlers/ZsignHandler.swift"
s = p.read_text()
old = '''guard !_options.disInjectionFiles.isEmpty else {'''
new = '''guard !_options.disInjectionFiles.isEmpty || !_options.rbx9DeletedDylibPaths.isEmpty else {'''
if s.count(old)!=1:raise RuntimeError("disinject empty-list guard missing")
s=s.replace(old,new,1)
old = '''let toRemove = _options.disInjectionFiles.filter { loaded.contains($0) }'''
new = '''let pathsToRemove = Set(_options.disInjectionFiles + _options.rbx9DeletedDylibPaths)
        let toRemove = pathsToRemove.filter { loaded.contains($0) }'''
if s.count(old)!=1:raise RuntimeError("disinject selection missing")
s=s.replace(old,new,1)
p.write_text(s)

# The original files do not change. Existing removeFiles pipeline runs on
# the signing copy; exclude deleted paths from the stored toggle inventory.
change("Feather/Utilities/Handlers/SigningHandler.swift",
       '''disabledPaths: _options.disInjectionFiles,
            previouslyLoaded: originalPaths''',
       '''disabledPaths: _options.disInjectionFiles,
            previouslyLoaded: originalPaths,
            deletedPaths: _options.rbx9DeletedDylibPaths''')

# Do not reuse a previous app's staged deletions on another imported IPA.
change("Feather/Views/Signing/SigningView.swift",
       '''_temporaryOptions.disInjectionFiles = RBx9DylibArchive.disabled(in: base)
                _rbx9DylibStateLoaded = true''',
       '''_temporaryOptions.disInjectionFiles = RBx9DylibArchive.disabled(in: base)
                _temporaryOptions.rbx9DeletedDylibPaths = []
                _rbx9DylibStateLoaded = true''')

# Add one destructive swipe action and an undo list for staged deletions.
# Staging is instant; the app contents change only when Sign is tapped.
p = app / "Views/Signing/Shared/SigningDylibView.swift"
s = p.read_text()
old = '''SigningToggleCellView(
                        title: dylib,
                        options: $options,
                        arrayKeyPath: \.disInjectionFiles
                    )'''
new = '''SigningToggleCellView(
                        title: dylib,
                        options: $options,
                        arrayKeyPath: \.disInjectionFiles
                    )
                    .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                        Button(role: .destructive) {
                            _stageDelete(dylib)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }'''
if s.count(old)!=1:raise RuntimeError("Dylib row not found")
s=s.replace(old,new,1)
old='''        .safeAreaInset(edge: .bottom, spacing: 0) {'''
if s.count(old)!=1:raise RuntimeError("Existing-dylib action bar missing")
section = '''            if let pending = options?.rbx9DeletedDylibPaths, !pending.isEmpty {
                Section {
                    ForEach(pending, id: \.self) { path in
                        HStack(spacing: 12) {
                            Image(systemName: "trash.slash")
                                .foregroundStyle(.secondary)
                            Text((path as NSString).lastPathComponent)
                                .lineLimit(2)
                            Spacer(minLength: 4)
                            Button("Undo") { _undoDelete(path) }
                                .buttonStyle(.borderless)
                        }
                    }
                } header: {
                    Text("Delete on Next Sign (\(pending.count))")
                } footer: {
                    Text("Deletion applies only to the newly signed IPA. Your imported original is kept.")
                }
            }
'''
# Append to the NBList content, before it closes. The nearby .disabled() anchors location.
old='''            .disabled(options == nil)
'''
if s.count(old)!=1:raise RuntimeError("Existing dylib list block not found")
s=s.replace(old,old+section,1)
# Sign bar after new section
helpers='''    private func _stageDelete(_ dylib: String) {
        guard let bundlePath = Storage.shared.getAppDirectory(for: app),
              let relative = RBx9DylibArchive.relativeRemovalPath(for: dylib, in: bundlePath),
              var newOptions = options else {
            UIAlertController.showAlertWithOk(
                title: "Delete Dylib",
                message: "No safe embedded dylib file could be found for this entry."
            )
            return
        }
        if !newOptions.rbx9DeletedDylibPaths.contains(dylib) {
            newOptions.rbx9DeletedDylibPaths.append(dylib)
        }
        if !newOptions.removeFiles.contains(relative) {
            newOptions.removeFiles.append(relative)
        }
        options = newOptions
        _dylibs.removeAll { $0 == dylib }
    }

    private func _undoDelete(_ dylib: String) {
        guard let bundlePath = Storage.shared.getAppDirectory(for: app),
              var newOptions = options else { return }
        let relative = RBx9DylibArchive.relativeRemovalPath(for: dylib, in: bundlePath)
        newOptions.rbx9DeletedDylibPaths.removeAll { $0 == dylib }
        if let relative {
            newOptions.removeFiles.removeAll { $0 == relative }
        }
        options = newOptions
        _dylibs = RBx9DylibArchive.paths(in: bundlePath)
            .filter { !newOptions.rbx9DeletedDylibPaths.contains($0) }
    }
'''
old='''\tprivate func _loadDylibs() {'''
if s.count(old)!=1:raise RuntimeError("Dylib editor helper missing")
s=s.replace(old,helpers+"\n"+old,1)
old='''_dylibs = RBx9DylibArchive.paths(in: path)'''
new='''_dylibs = RBx9DylibArchive.paths(in: path)
            .filter { !(options?.rbx9DeletedDylibPaths.contains($0) ?? false) }'''
if s.count(old)!=1:raise RuntimeError("Dylib list load missing")
s=s.replace(old,new,1)
p.write_text(s)

print("RBx9 v1.3.2 swipe-to-delete and reversible staging ready")
