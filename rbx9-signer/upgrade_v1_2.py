#!/usr/bin/env python3
# RBx9 v1.2 UX fixes - Feather GPL-3.0-derived project.
from pathlib import Path
import json, shutil, re
root=Path("feather")
app=root/"Feather"
def change(path,old,new, count=1):
    file=root/path
    source=file.read_text()
    occurrences=source.count(old)
    if occurrences != count:
        raise RuntimeError(f"RBx9 v1.2 {path}: wanted {count} copies, found {occurrences}, of {old[:100]!r}")
    file.write_text(source.replace(old,new,count))
    print("RBx9 v1.2:",path)
def patch(path, callback):
    file=root/path
    source=file.read_text()
    result=callback(source)
    if result==source:
        raise RuntimeError("No patch applied: "+path)
    file.write_text(result)
    print("RBx9 v1.2:",path)

change("Feather.xcconfig","FEATHER_PROJECT_VERSION=1.1.0","FEATHER_PROJECT_VERSION=1.2.0")

# No interruption while enabling/disabling, importing or removing tweaks.
# Apply all staged changes by tapping the main Sign & Install button.
p=app/"Views/Signing/SigningTweaksView.swift"
s=p.read_text()
s=s.replace('    @State private var _showRBx9ApplyConfirmation = false\n','')
s=s.replace('                                _showRBx9ApplyConfirmation = true\n','')
s=s.replace('                        _showRBx9ApplyConfirmation = true\n','')
s=s.replace('            _showRBx9ApplyConfirmation = true\n','')
start=s.find('        .confirmationDialog("Dylib Changes Ready"')
end=s.find('        .animation(.smooth, value: options.injectionFiles)',start)
if start<0 or end<start: raise RuntimeError("Could not remove tweak confirmation safely")
s=s[:start]+s[end:]
if "_showRBx9ApplyConfirmation" in s: raise RuntimeError("Unexpected tweak confirmation reference")
p.write_text(s)

p=app/"Views/Signing/Shared/SigningDylibView.swift"
s=p.read_text()
s=s.replace('    @State private var _showRBx9ApplyConfirmation = false\n','')
start=s.find('        .onChange(of: options?.disInjectionFiles)')
end=s.find('        } message: {', start)
if start<0 or end<start: raise RuntimeError("Missing existing-dylibs dialog")
end=s.find('\n        }',end+12)
if end<0: raise RuntimeError("Missing closing confirmation dialog")
s=s[:start]+s[end+len('\n        }'):]
if "_showRBx9ApplyConfirmation" in s: raise RuntimeError("Unexpected embedded dylib popup reference")
p.write_text(s)

# Clear primary and secondary buttons. Exact one-tap Sign & Install
# uses saved signing configuration then immediately opens the installer.
p=app/"Views/Signing/SigningView.swift"
s=p.read_text()
start=s.index('\n\t\t\t.overlay {\n\t\t\t\tVStack(spacing: 0) {')
end=s.index('\n\t\t\t.toolbar {',start)
bar='''
            .safeAreaInset(edge: .bottom, spacing: 0) {
                HStack(spacing: 12) {
                    Button {
                        _start(installAfterSigning: true)
                    } label: {
                        Label("Sign & Install", systemImage: "square.and.arrow.down.fill")
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                            .foregroundStyle(Color.black)
                            .frame(maxWidth: .infinity, minHeight: 54)
                            .background(
                                LinearGradient(
                                    colors: [
                                        Color(red: 0.42, green: 0.92, blue: 0.84),
                                        Color(red: 0.16, green: 0.80, blue: 0.90)
                                    ],
                                    startPoint: .leading,
                                    endPoint: .trailing
                                ),
                                in: RoundedRectangle(cornerRadius: 17, style: .continuous)
                            )
                    }
                    .accessibilityHint("Sign this IPA and immediately open the installer.")
                    Button {
                        _start(installAfterSigning: false)
                    } label: {
                        Label("Sign Only", systemImage: "signature")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Color.accentColor)
                            .frame(minWidth: 108, minHeight: 54)
                            .padding(.horizontal, 6)
                            .background(Color.accentColor.opacity(0.12),
                                        in: RoundedRectangle(cornerRadius: 17, style: .continuous))
                    }
                    .accessibilityHint("Sign this IPA without installing it.")
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 6)
                .background(.regularMaterial)
            }
'''
s=s[:start]+bar+s[end:]
# Remove the original white feather from the signing titlebar.
glyph='''Image("Glyph")
\t\t\t\t\t\t.resizable()
\t\t\t\t\t\t.scaledToFit()
\t\t\t\t\t\t.frame(height: 38)'''
brand='''Image("RBx9Brand")
                        .resizable()
                        .scaledToFit()
                        .frame(width: 36, height: 36)
                        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                        .accessibilityLabel("RBx9")'''
if s.count(glyph)!=1:raise RuntimeError("Feather glyph location changed")
s=s.replace(glyph,brand)
p.write_text(s)
brandAssets=app/"Resources/Assets.xcassets/RBx9Brand.imageset"
brandAssets.mkdir(exist_ok=True)
shutil.copy2("rbx9-source-icon.png",brandAssets/"rbx9-brand.png")
(brandAssets/"Contents.json").write_text(json.dumps({"images":[{"filename":"rbx9-brand.png","idiom":"universal"}],"info":{"author":"xcode","version":1}},indent=2))

# Rebrand any other explicit screenshot-visible Feather glyph references.
signing=s
assert 'Image("Glyph")' not in signing
# Read-only notices and upstream GPL credits are intentionally preserved.

# Modern action badges instead of tiny glyphs on Library rows; whole row still tappable.
p=app/"Views/Library/LibraryCellView.swift"
s=p.read_text()
old='''Image(systemName: app.isSigned ? "square.and.arrow.down.fill" : "signature")
                    .foregroundStyle(Color.accentColor)
                    .font(.title3)
                    .accessibilityHidden(true)'''
new='''HStack(spacing: 5) {
                    Image(systemName: app.isSigned ? "square.and.arrow.down.fill" : "signature")
                    Text(app.isSigned ? "Install" : "Sign")
                }
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(Color.black)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(Color(red: 0.32, green: 0.88, blue: 0.81),
                            in: Capsule())
                .accessibilityLabel(app.isSigned ? "Install application" : "Sign application")'''
if s.count(old)!=1:raise RuntimeError("Library row action anchor changed")
p.write_text(s.replace(old,new))

# Keep Telegram feedback button at the top. No editable channel setting block.
p=app/"Views/Settings/SettingsView.swift"
s=p.read_text()
settingStart=s.index('                Section {\n                    TextField("https://t.me/RBx9_Repo"')
settingEnd=s.index('\n\t\t\t\tSection {',settingStart)
s=s[:settingStart]+s[settingEnd:]
s=s.replace('For help or feedback, use the Telegram channel configured above. Source code and releases are available on GitHub.',
            'Submit feedback through @RBx9_Repo on Telegram. Source code and open-source credits are available on GitHub.')
p.write_text(s)

# Icon picker previously read iOS alternateIconName (sometimes reported nil after
# sideloading). Track the last successful user choice to keep the check aligned.
p=app/"Views/Settings/App Icon/AppIconView.swift"
s=p.read_text()
needle='''    @Binding var currentIcon: String?'''
if s.count(needle)!=1:raise RuntimeError("Icon view binding missing")
s=s.replace(needle,needle+'''
    @AppStorage("rbx9.selectedAlternateIcon") private var _selectedIconKey = ""''')
old='''UIApplication.shared.setAlternateIconName(icon.key) { _ in
                            currentIcon = UIApplication.shared.alternateIconName
                        }'''
new='''UIApplication.shared.setAlternateIconName(icon.key) { error in
                            DispatchQueue.main.async {
                                if let error {
                                    UIAlertController.showAlertWithOk(
                                        title: "App Icon",
                                        message: error.localizedDescription
                                    )
                                } else {
                                    _selectedIconKey = icon.key ?? ""
                                    currentIcon = icon.key
                                }
                            }
                        }'''
if s.count(old)!=1:raise RuntimeError("setAlternateIconName callback changed")
s=s.replace(old,new)
s=s.replace('''if currentIcon == icon.key {''','''if (_selectedIconKey.isEmpty ? currentIcon == icon.key : _selectedIconKey == icon.key) {''')
old='''currentIcon = UIApplication.shared.alternateIconName'''
new='''if let active = UIApplication.shared.alternateIconName {
                _selectedIconKey = active
                currentIcon = active
            } else {
                currentIcon = _selectedIconKey.isEmpty ? nil : _selectedIconKey
            }'''
if s.count(old)!=1:raise RuntimeError("Icon onAppear anchor missing")
s=s.replace(old,new)
p.write_text(s)

# Library: modern segmented Sign / Install with optional existing Classic layout.
p=app/"Views/Library/LibraryView.swift"
s=p.read_text()
needle='''@State private var _selectedScope: Scope = .all'''
if s.count(needle)!=1:raise RuntimeError("Missing library selection")
s=s.replace(needle,needle+'''
    @State private var _rbx9LibraryTab = 0
    @AppStorage("rbx9.libraryLayout") private var _rbx9LibraryLayout = 1''')
hero='''Section {
                    RBx9HeroCard().listRowBackground(Color.clear)
                }'''
if s.count(hero)!=1:raise RuntimeError("Missing library hero")
s=s.replace(hero,hero+'''
                if _rbx9LibraryLayout == 1 {
                    Section {
                        Picker("Library Mode", selection: $_rbx9LibraryTab) {
                            Label("Sign", systemImage: "signature").tag(0)
                            Label("Install", systemImage: "square.and.arrow.down.fill").tag(1)
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                    }
                    .listRowBackground(Color.clear)
                }''')
old='''_selectedScope == .all || _selectedScope == .signed'''
new='''(_rbx9LibraryLayout == 1
                        ? _rbx9LibraryTab == 1
                        : (_selectedScope == .all || _selectedScope == .signed))'''
if s.count(old)!=1:raise RuntimeError("Signed section condition mismatch")
s=s.replace(old,new)
old='''_selectedScope == .all || _selectedScope == .imported'''
new='''(_rbx9LibraryLayout == 1
                        ? _rbx9LibraryTab == 0
                        : (_selectedScope == .all || _selectedScope == .imported))'''
if s.count(old)!=2:raise RuntimeError("Imported search and section conditions mismatch")
# Replace ONLY the first section predicate, retain bulk delete logic in Classic.
s=s.replace(old,new,1)
# Bulk delete must respect the displayed tab.
s=s.replace('''if _selectedScope == .all || _selectedScope == .signed {
\t\t\tallApps.append(contentsOf: _filteredSignedApps)
\t\t}''','''if (_rbx9LibraryLayout == 1 && _rbx9LibraryTab == 1) ||
            (_rbx9LibraryLayout == 0 && (_selectedScope == .all || _selectedScope == .signed)) {
            allApps.append(contentsOf: _filteredSignedApps)
        }''')
s=s.replace('''if _selectedScope == .all || _selectedScope == .imported {
\t\t\tallApps.append(contentsOf: _filteredImportedApps)
\t\t}''','''if (_rbx9LibraryLayout == 1 && _rbx9LibraryTab == 0) ||
            (_rbx9LibraryLayout == 0 && (_selectedScope == .all || _selectedScope == .imported)) {
            allApps.append(contentsOf: _filteredImportedApps)
        }''')
p.write_text(s)

# Appearance includes a layout selection; classic keeps existing Signed/Imported layout.
p=app/"Views/Settings/Appearance/AppearanceView.swift"
s=p.read_text()
n='''@AppStorage("Feather.shouldTintIcons")'''
if s.count(n)!=1:raise RuntimeError("Missing appearance tint toggle")
s=s.replace(n,'''@AppStorage("rbx9.libraryLayout") private var _rbx9LibraryLayout = 1

    '''+n)
needle='''NBSection(.localized("Theme")) {'''
if s.count(needle)!=1:raise RuntimeError("Missing appearance theme section")
s=s.replace(needle,'''NBSection("Library Layout") {
                Picker("Layout", selection: $_rbx9LibraryLayout) {
                    Text("Modern • Sign / Install").tag(1)
                    Text("Classic • Signed / Imported").tag(0)
                }
                .pickerStyle(.inline)
                .labelsHidden()
            }
            '''+needle)
p.write_text(s)

# Improve source refresh: publish completion, preserve previous apps while updating,
# avoid HTTP cache, and allow refresh after an in-flight initial fetch completes.
p=app/"Views/Sources/SourcesViewModel.swift"
s=p.read_text()
s=s.replace('''var isFinished = true''','''@Published var isFinished = true''')
needle='''func fetchSources(_ sources: FetchedResults<AltSource>, refresh: Bool = false, batchSize: Int = 4) async {
\t\tguard isFinished else { return }'''
replace='''func fetchSources(_ sources: [AltSource], refresh: Bool = false, batchSize: Int = 4) async {
        if !isFinished {
            if !refresh { return }
            while !isFinished {
                if Task.isCancelled { return }
                try? await Task.sleep(nanoseconds: 150_000_000)
            }
        }'''
if s.count(needle)!=1:raise RuntimeError("SourcesViewModel fetch signature changed")
s=s.replace(needle,replace)
block='''\t\tawait MainActor.run {
\t\t\tself.sources = [:]
\t\t}
'''
if s.count(block)!=1:raise RuntimeError("Sources clearing anchor missing")
s=s.replace(block,'')
s=s.replace('''let sourcesArray = Array(sources)''','''let sourcesArray = sources''')
old='''return await withCheckedContinuation { continuation in
\t\t\t\t\t\t\tself._dataService.fetch(from: url) { (result: RepositoryDataHandler) in
\t\t\t\t\t\t\t\tswitch result {
\t\t\t\t\t\t\t\tcase .success(let repo):
\t\t\t\t\t\t\t\t\tcontinuation.resume(returning: (source, repo))
\t\t\t\t\t\t\t\tcase .failure(_):
\t\t\t\t\t\t\t\t\tcontinuation.resume(returning: (source, nil))
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}
\t\t\t\t\t\t}'''
new='''do {
                            var requestURL = url
                            if refresh, var components = URLComponents(url: url, resolvingAgainstBaseURL: false) {
                                var query = components.queryItems ?? []
                                query.append(URLQueryItem(name: "_rbx9_refresh", value: UUID().uuidString))
                                components.queryItems = query
                                requestURL = components.url ?? url
                            }
                            var request = URLRequest(
                                url: requestURL,
                                cachePolicy: .reloadIgnoringLocalCacheData,
                                timeoutInterval: 22
                            )
                            request.setValue("no-cache, no-store", forHTTPHeaderField: "Cache-Control")
                            let (data, response) = try await URLSession.shared.data(for: request)
                            guard let http = response as? HTTPURLResponse,
                                  (200...299).contains(http.statusCode) else {
                                return (source, nil)
                            }
                            return (source, try JSONDecoder().decode(ASRepository.self, from: data))
                        } catch {
                            return (source, nil)
                        }'''
if s.count(old)!=1:raise RuntimeError("Source fetch continuation anchor missing")
s=s.replace(old,new)
# Keep last known good repository when one endpoint temporarily fails.
p.write_text(s)

p=app/"Views/Sources/SourcesView.swift"
s=p.read_text()
if s.count('await viewModel.fetchSources(_sources')!=2:raise RuntimeError("Sources refresh calls changed")
s=s.replace('await viewModel.fetchSources(_sources','await viewModel.fetchSources(Array(_sources)')
# Add explicit refresh action even when pull-to-refresh gesture is unavailable.
needle='''\t\t\t.toolbar {
\t\t\t\tNBToolbarButton(
\t\t\t\t\tsystemImage: "plus",'''
replace='''            .toolbar {
                NBToolbarButton(
                    systemImage: "arrow.clockwise",
                    style: .icon,
                    placement: .topBarTrailing
                ) {
                    Task { await viewModel.fetchSources(Array(_sources), refresh: true) }
                }
                NBToolbarButton(
                    systemImage: "plus",'''
if s.count(needle)!=1:raise RuntimeError("Sources toolbar anchor mismatch")
s=s.replace(needle,replace)
p.write_text(s)

p=app/"Views/Sources/Apps/SourceAppsView.swift"
s=p.read_text()
needle='''\t\t.toolbar {
\t\t\tNBToolbarMenu(
\t\t\t\tsystemImage: "line.3.horizontal.decrease",'''
replace='''        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    Task { await viewModel.fetchSources(object, refresh: true) }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .accessibilityLabel("Refresh sources")
            }
            NBToolbarMenu(
                systemImage: "line.3.horizontal.decrease",'''
if s.count(needle)!=1:raise RuntimeError("SourceAppsView toolbar changed")
s=s.replace(needle,replace)
needle='''\t\t.onChange(of: viewModel.isFinished) { _ in
\t\t\t_load()
\t\t}'''
replace='''        .onChange(of: viewModel.isFinished) { newValue in
            if newValue { _load() }
        }
        .onReceive(viewModel.$sources) { _ in
            _load()
        }'''
if s.count(needle)!=1:raise RuntimeError("SourceAppsView refresh reload hook changed")
s=s.replace(needle,replace)
p.write_text(s)
print("RBx9 v1.2 upgrade successful")
