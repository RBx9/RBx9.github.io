#!/usr/bin/env python3
# GPL-3.0-only RBx9 adaptation of Feather; keep upstream LICENSE and notices.
import json, plistlib, shutil, subprocess
from pathlib import Path
root=Path("feather"); app=root/"Feather"
def replace(path,old,new):
 p=root/path
 s=p.read_text()
 if s.count(old)!=1:
  raise RuntimeError(f"Expected one anchor in {p}: {old[:90]!r}; found {s.count(old)}")
 p.write_text(s.replace(old,new,1))
 print("RBx9 patched",path)
replace("Feather.xcconfig","FEATHER_PRODUCT_BUNDLE_IDENTIFIER=thewonderofyou.Feather","FEATHER_PRODUCT_BUNDLE_IDENTIFIER=com.rbx9.signer")
replace("Feather.xcconfig","FEATHER_PROJECT_VERSION=2.9.0","FEATHER_PROJECT_VERSION=1.0.0")
p=root/"Feather.xcodeproj/project.pbxproj"
t=p.read_text(); assert "INFOPLIST_KEY_CFBundleDisplayName = Feather;" in t
p.write_text(t.replace("INFOPLIST_KEY_CFBundleDisplayName = Feather;","INFOPLIST_KEY_CFBundleDisplayName = RBx9;"))
p=app/"Resources/Info.plist"
with p.open("rb") as f: info=plistlib.load(f)
info["CFBundleName"]="RBx9"; info["CFBundleDisplayName"]="RBx9"
for u in info.get("CFBundleURLTypes",[]):
 schemes=u.get("CFBundleURLSchemes",[])
 if "feather" in schemes and "rbx9" not in schemes: schemes.insert(0,"rbx9")
with p.open("wb") as f: plistlib.dump(info,f,sort_keys=False)
replace("Feather/FeatherApp.swift","var body: some Scene {",'''init() {
        UserDefaults.standard.register(defaults: [
            "Feather.userTintColor": "#2DE2CF",
            "Feather.userInterfaceStyle": 2,
            "rbx9.autoCleanupPreviousVersions": true,
            "rbx9.keepOriginalIPAs": true
        ])
    }

    var body: some Scene {''')
replace("Feather/FeatherApp.swift",'if url.scheme == "feather" {','if url.scheme == "rbx9" || url.scheme == "feather" {')
replace("Feather/FeatherApp.swift",'?? "#848ef9"','?? "#2DE2CF"')
replace("Feather/Views/Common/FRAppIconView.swift",'"#848ef9"','"#2DE2CF"')
icons=app/"Resources/Assets.xcassets/AppIcon.appiconset"
manifest=icons/"Contents.json"; data=json.loads(manifest.read_text())
for item in data["images"]:
 old=item.get("filename")
 if old in ("feather.png","feather_dark.png","feather_tint.png"):
  item["filename"]={"feather.png":"rbx9.png","feather_dark.png":"rbx9_dark.png","feather_tint.png":"rbx9_tint.png"}[old]
manifest.write_text(json.dumps(data,indent=2)+"\n")
for name in ("rbx9.png","rbx9_dark.png","rbx9_tint.png"):
 shutil.copy2("rbx9-source-icon.png",icons/name)
composer=app/"Resources/AppIcon.icon"
p=composer/"icon.json"; d=json.loads(p.read_text())
d["fill"]={"linear-gradient":["srgb:0.025,0.060,0.125,1.000","srgb:0.016,0.18,0.26,1.000"],"orientation":{"start":{"x":0.0,"y":0.0},"stop":{"x":1.0,"y":1.0}}}
d["groups"]=[{"layers":[{"image-name":"rbx9.png","name":"RBx9"}],"shadow":{"kind":"neutral","opacity":0.1},"translucency":{"enabled":False}}]
p.write_text(json.dumps(d,indent=2)+"\n")
# Icon Composer data may crash actool during asset catalog build; rely on .xcassets instead.
shutil.rmtree(composer)
# Preserve the original Feather core-data model and actual signing/installation engine.
replace("Feather/Views/Settings/SettingsView.swift",'@State private var _currentIcon: String? = UIApplication.shared.alternateIconName','''@State private var _currentIcon: String? = UIApplication.shared.alternateIconName
    @AppStorage("rbx9.autoCleanupPreviousVersions") private var _autoCleanupPrevious = true
    @AppStorage("rbx9.keepOriginalIPAs") private var _keepOriginalIPAs = true''')
replace("Feather/Views/Settings/SettingsView.swift","\n\t\t\t\t_directories()",'''
                Section {
                    Toggle(isOn: $_autoCleanupPrevious) {
                        Label("Auto-Cleanup Previous Versions", systemImage: "square.stack.3d.up.slash")
                    }
                    Toggle(isOn: $_keepOriginalIPAs) {
                        Label("Keep Original IPA Files", systemImage: "externaldrive.badge.checkmark")
                    }
                } header: {
                    Text("RBx9 Workflow")
                } footer: {
                    Text("After successful signing or installation, hide superseded signed entries. Original IPA archives and installed apps remain untouched.")
                }
                _directories()''')
replace("Feather/Views/Signing/SigningView.swift",'''SigningDylibView(
						app: app,
						options: $_temporaryOptions.optional()
					)''','''SigningDylibView(
                        app: app,
                        options: $_temporaryOptions.optional(),
                        onApply: { shouldInstall in _start(installAfterSigning: shouldInstall) }
                    )''')
replace("Feather/Views/Signing/SigningView.swift",'''SigningTweaksView(
						options: $_temporaryOptions
					)''','''SigningTweaksView(
                        options: $_temporaryOptions,
                        onApply: { shouldInstall in _start(installAfterSigning: shouldInstall) }
                    )''')
replace("Feather/Views/Signing/SigningView.swift","private func _start() {",'''private func _start(installAfterSigning: Bool? = nil) {
        if let installAfterSigning {
            _temporaryOptions.post_installAppAfterSigned = installAfterSigning
        }
        if UserDefaults.standard.bool(forKey: "rbx9.keepOriginalIPAs") {
            _temporaryOptions.post_deleteAppAfterSigned = false
        }''')
replace("Feather/Views/Signing/SigningView.swift",'NBSheetButton(title: .localized("Start Signing"), style: .prominent)','NBSheetButton(title: _temporaryOptions.post_installAppAfterSigned ? "Sign & Install" : "Sign IPA", style: .prominent)')
replace("Feather/Views/Signing/SigningTweaksView.swift",'@State private var _isAddingPresenting = false','''@State private var _isAddingPresenting = false
    @State private var _showRBx9ApplyConfirmation = false
    var onApply: (Bool) -> Void = { _ in }''')
replace("Feather/Views/Signing/SigningTweaksView.swift","options.injectionFiles.append(url)",'''if !options.injectionFiles.contains(url) {
                                options.injectionFiles.append(url)
                                _showRBx9ApplyConfirmation = true
                            }''')
replace("Feather/Views/Signing/SigningTweaksView.swift","\t\t.animation(.smooth, value: options.injectionFiles)",'''        .confirmationDialog("Dylib Changes Ready", isPresented: $_showRBx9ApplyConfirmation, titleVisibility: .visible) {
            Button("Re-sign & Reinstall") { onApply(true) }
            Button("Sign Only") { onApply(false) }
            Button("Later", role: .cancel) { }
        } message: {
            Text("Apply your tweak changes using the saved certificate and app-specific signing settings?")
        }
        .animation(.smooth, value: options.injectionFiles)''')
replace("Feather/Views/Signing/SigningTweaksView.swift",'''FileManager.default.deleteStored(tweak) { url in
				if let index = options.injectionFiles.firstIndex(where: { $0 == url }) {
					options.injectionFiles.remove(at: index)
				}
			}''','''if let index = options.injectionFiles.firstIndex(of: tweak) {
                options.injectionFiles.remove(at: index)
                _showRBx9ApplyConfirmation = true
            }''')
replace("Feather/Views/Signing/Shared/SigningDylibView.swift",'@State private var _hiddenDylibCount: Int = 0','''@State private var _hiddenDylibCount: Int = 0
    @State private var _showRBx9ApplyConfirmation = false
    var onApply: (Bool) -> Void = { _ in }''')
replace("Feather/Views/Signing/Shared/SigningDylibView.swift","\t\t.onAppear(perform: _loadDylibs)",'''        .onAppear(perform: _loadDylibs)
        .onChange(of: options?.disInjectionFiles) { _ in
            _showRBx9ApplyConfirmation = true
        }
        .confirmationDialog("Dylib Changes Ready", isPresented: $_showRBx9ApplyConfirmation, titleVisibility: .visible) {
            Button("Re-sign & Reinstall") { onApply(true) }
            Button("Sign Only") { onApply(false) }
            Button("Later", role: .cancel) { }
        } message: {
            Text("Re-sign with your saved certificate and install the updated IPA?")
        }''')
replace("Feather/Views/Library/LibraryView.swift",'''private var _filteredSignedApps: [Signed] {
		filteredAndSortedApps(from: _signedApps)
	}''','''@AppStorage("rbx9.autoCleanupPreviousVersions") private var _autoCleanupPrevious = true
    @AppStorage("rbx9.hiddenSignedUUIDs") private var _hiddenSignedUUIDs = ""
    private var _filteredSignedApps: [Signed] {
        let hidden = Set(_hiddenSignedUUIDs.split(separator: "|").map(String.init))
        return filteredAndSortedApps(from: _signedApps).filter { item in
            !_autoCleanupPrevious || !hidden.contains(item.uuid ?? "")
        }
    }''')
replace("Feather/Views/Library/LibraryView.swift","NBListAdaptable {\n\t\t\t\tif",'''NBListAdaptable {
                Section {
                    RBx9HeroCard().listRowBackground(Color.clear)
                }
                if''')
replace("Feather/Utilities/Handlers/SigningHandler.swift",'''\t\tif let error = handler.hadError {
			throw error
		}''','''        if let error = handler.hadError {
            throw error
        }
        if !_options.post_installAppAfterSigned {
            await MainActor.run {
                RBx9ListHistory.collapseOlderSignedRows(keepingUUID: self._uuid)
            }
        }''')
replace("Feather/Views/Library/Install/InstallPreviewView.swift",'''\t\t.onReceive(viewModel.$status) { newStatus in
			if _installationMethod == 0 {''','''        .onReceive(viewModel.$status) { newStatus in
            if case .completed(.success(_)) = newStatus {
                Task { @MainActor in
                    RBx9ListHistory.collapseOlderSignedRows(keepingUUID: app.uuid)
                }
            }
            if _installationMethod == 0 {''')
(app/"Backend/Storage/RBx9ListHistory.swift").write_text("""// SPDX-License-Identifier: GPL-3.0-only
import Foundation
import CoreData
@MainActor
enum RBx9ListHistory {
    private static let hiddenKey = "rbx9.hiddenSignedUUIDs"
    static func collapseOlderSignedRows(keepingUUID: String?) {
        guard UserDefaults.standard.object(forKey: "rbx9.autoCleanupPreviousVersions") as? Bool ?? true,
            let keepingUUID, !keepingUUID.isEmpty else { return }
        let request = NSFetchRequest<Signed>(entityName: "Signed")
        guard let all = try? Storage.shared.context.fetch(request),
            let newest = all.first(where: { $0.uuid == keepingUUID }),
            let identifier = newest.identifier, !identifier.isEmpty else { return }
        let old = all.compactMap { item -> String? in
            guard item.identifier == identifier && item.uuid != keepingUUID else { return nil }
            return item.uuid
        }
        guard !old.isEmpty else { return }
        var hidden = Set((UserDefaults.standard.string(forKey: hiddenKey) ?? "")
            .split(separator: "|").map(String.init))
        hidden.formUnion(old)
        hidden.remove(keepingUUID)
        UserDefaults.standard.set(hidden.sorted().joined(separator: "|"), forKey: hiddenKey)
    }
}
""")
(app/"Views/Library/RBx9HeroCard.swift").write_text("""// SPDX-License-Identifier: GPL-3.0-only
import SwiftUI
struct RBx9HeroCard: View {
    @State private var appeared = false
    private let cyan = Color(red: 0.19, green: 0.89, blue: 0.82)
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "shippingbox.fill")
                Text("RBx9  •  SIGNING STUDIO").tracking(2)
                Spacer()
                Text("iOS 16+").font(.caption2.weight(.semibold))
            }.font(.caption.weight(.bold)).foregroundStyle(cyan)
            Text("Your apps.\\nYour control.")
                .font(.system(size: 30, weight: .bold, design: .rounded))
                .lineSpacing(2).foregroundStyle(.white)
            Text("Import, personalize, inject tweaks and sign in fewer steps.")
                .font(.subheadline).foregroundStyle(.white.opacity(0.74))
            Label("Re-sign & Reinstall after tweak changes", systemImage: "arrow.triangle.2.circlepath")
                .font(.caption.weight(.medium)).foregroundStyle(cyan).padding(.top, 3)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(22)
        .background {
            RoundedRectangle(cornerRadius: 25, style: .continuous)
                .fill(LinearGradient(colors: [
                    Color(red: 0.045, green: 0.09, blue: 0.17),
                    Color(red: 0.035, green: 0.20, blue: 0.27)
                ], startPoint: .topLeading, endPoint: .bottomTrailing))
                .overlay {
                    RoundedRectangle(cornerRadius: 25, style: .continuous)
                        .stroke(cyan.opacity(0.25), lineWidth: 1)
                }
        }
        .scaleEffect(appeared ? 1 : 0.97).opacity(appeared ? 1 : 0)
        .onAppear {
            withAnimation(.spring(response: 0.52, dampingFraction: 0.84)) { appeared = true }
        }
        .accessibilityElement(children: .combine)
    }
}
""")
print("RBx9 source customization complete")
