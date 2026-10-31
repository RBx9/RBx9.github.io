#!/usr/bin/env python3
# RBx9 v1.1 UX update. Feather-derived files retain GPL-3.0 obligations.
from pathlib import Path
root = Path("feather")
def change(file, old, new):
    p = root / file
    s = p.read_text()
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{file}: expected one match for {old[:65]!r}, got {n}")
    p.write_text(s.replace(old,new,1))
    print("RBx9 1.1 updated", file)
change("Feather.xcconfig","FEATHER_PROJECT_VERSION=1.0.0","FEATHER_PROJECT_VERSION=1.1.0")

# Install the user-provided RBx9 source, once, after the Sources view is opened.
# A successfully added source remains removable by the user.
change("Feather/Views/Sources/SourcesView.swift",
       '@State private var _searchText = ""',
       '''@State private var _searchText = ""
    @AppStorage("rbx9.addedDefaultSource") private var _rbx9AddedDefaultSource = false''')
change("Feather/Views/Sources/SourcesView.swift",
       '''.task(id: Array(_sources)) {
            await viewModel.fetchSources(_sources)
        }'''.replace("            ","\t\t\t").replace("        }","\t\t}"),
       '''.task(id: Array(_sources)) {
            await viewModel.fetchSources(_sources)
        }
        .task {
            if Storage.shared.sourceExists("com.rbx9.ipa.library") {
                _rbx9AddedDefaultSource = true
            } else if !_rbx9AddedDefaultSource {
                FR.handleSource("https://rbx9.github.io/ipa/") {
                    _rbx9AddedDefaultSource = true
                }
            }
        }''')
change("Feather/Views/Sources/SourcesView.swift",
       'UIApplication.open("https://github.com/khcrysalis/Feather")',
       'UIApplication.open("https://github.com/RBx9")')

# Make the whole library row the primary action, rather than the green action pill.
change("Feather/Views/Library/LibraryCellView.swift",
       '''if !isEditing {
                _buttonActions(for: app)
            }'''.replace("                ","\t\t\t\t").replace("            }","\t\t\t}"),
       '''if !isEditing {
                Image(systemName: app.isSigned ? "square.and.arrow.down.fill" : "signature")
                    .foregroundStyle(Color.accentColor)
                    .font(.title3)
                    .accessibilityHidden(true)
            }''')
change("Feather/Views/Library/LibraryCellView.swift",
       '''if isEditing {
				_toggleSelection()
			}
		}
		.swipeActions''',
       '''if isEditing {
                _toggleSelection()
            } else if app.isSigned {
                selectedInstallAppPresenting = AnyApp(base: app)
            } else {
                selectedSigningAppPresenting = AnyApp(base: app)
            }
        }
        .swipeActions''')

# After standard signing, ask to install with one tap. The explicit
# "Sign Only" tweak action does not ask; "Re-sign & Reinstall" still auto-launches.
change("Feather/Views/Signing/SigningView.swift",
       '''if _temporaryOptions.post_installAppAfterSigned {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        NotificationCenter.default.post(name: Notification.Name("Feather.installApp"), object: nil)
                    }
                }
                dismiss()'''.replace("                    ","\t\t\t\t\t").replace("                }","\t\t\t\t}").replace("                dismiss()","\t\t\t\tdismiss()"),
       '''if _temporaryOptions.post_installAppAfterSigned {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        NotificationCenter.default.post(name: Notification.Name("Feather.installApp"), object: nil)
                    }
                } else if installAfterSigning == nil {
                    // Standard sign flow: prompt after success, without auto-install.
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) {
                        let install = UIAlertAction(title: "Install Now", style: .default) { _ in
                            NotificationCenter.default.post(
                                name: Notification.Name("Feather.installApp"),
                                object: nil
                            )
                        }
                        UIAlertController.showAlertWithCancel(
                            title: "Signed Successfully",
                            message: "Install your newly signed app now?",
                            actions: [install]
                        )
                    }
                }
                dismiss()''')
# Old post-install defaults could skip the requested prompt; standard signing
# now prefers the confirmation even when users had previously selected auto-install.
change("Feather/Views/Signing/SigningView.swift",
       '''private func _start(installAfterSigning: Bool? = nil) {
        if let installAfterSigning {''',
       '''private func _start(installAfterSigning: Bool? = nil) {
        if installAfterSigning == nil {
            _temporaryOptions.post_installAppAfterSigned = false
        }
        if let installAfterSigning {''')
# Promote tweak controls out of the long Advanced disclosure group.
change("Feather/Views/Signing/SigningView.swift",
       '''NBSection(.localized("Advanced")) {''',
       '''NBSection("Quick Tweak Editor") {
            NavigationLink {
                SigningTweaksView(
                    options: $_temporaryOptions,
                    onApply: { shouldInstall in _start(installAfterSigning: shouldInstall) }
                )
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "puzzlepiece.extension.fill")
                        .foregroundStyle(Color.accentColor)
                        .font(.title2)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Add or Remove Dylibs")
                            .font(.headline)
                        Text("\(_temporaryOptions.injectionFiles.count) tweaks selected • .dylib / .deb")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 4)
            }
            NavigationLink {
                SigningDylibView(
                    app: app,
                    options: $_temporaryOptions.optional(),
                    onApply: { shouldInstall in _start(installAfterSigning: shouldInstall) }
                )
            } label: {
                Label("Manage Existing Dylibs", systemImage: "switch.2")
            }
        }
        NBSection(.localized("Advanced")) {''')

# Easier tweak management with visible Add and Remove All controls, and per-file
# remove button. Removing a selection never deletes files from storage.
change("Feather/Views/Signing/SigningTweaksView.swift",
       '''NBSection(.localized("Tweaks")) {''',
       '''NBSection("Quick Actions") {
                Button {
                    _isAddingPresenting = true
                } label: {
                    Label("Add Dylibs or DEBs", systemImage: "plus.circle.fill")
                        .foregroundStyle(Color.accentColor)
                }
                if !options.injectionFiles.isEmpty {
                    Button(role: .destructive) {
                        options.injectionFiles.removeAll()
                        _showRBx9ApplyConfirmation = true
                    } label: {
                        Label("Remove All Selected Tweaks", systemImage: "minus.circle")
                    }
                }
            }
            NBSection("Selected Tweaks (\(options.injectionFiles.count))") {''')
change("Feather/Views/Signing/SigningTweaksView.swift",
       '''Label(tweak.lastPathComponent, systemImage: "folder.fill")
            .lineLimit(2)
            .frame(maxWidth: .infinity, alignment: .leading)'''.replace("            ","\t\t\t").replace("            .","\t\t\t."),
       '''HStack(spacing: 12) {
                Image(systemName: tweak.pathExtension.lowercased() == "deb" ? "shippingbox" : "puzzlepiece.fill")
                    .foregroundStyle(Color.accentColor)
                Text(tweak.lastPathComponent)
                    .lineLimit(2)
                Spacer(minLength: 0)
                Button {
                    _removeTweak(tweak)
                } label: {
                    Image(systemName: "minus.circle")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.borderless)
                .accessibilityLabel("Remove \(tweak.lastPathComponent)")
            }
            .frame(maxWidth: .infinity, alignment: .leading)''')
change("Feather/Views/Signing/SigningTweaksView.swift",
       '''@ViewBuilder
	private func _fileActions(tweak: URL) -> some View {''',
       '''private func _removeTweak(_ tweak: URL) {
        if let index = options.injectionFiles.firstIndex(of: tweak) {
            options.injectionFiles.remove(at: index)
            _showRBx9ApplyConfirmation = true
        }
    }

    @ViewBuilder
    private func _fileActions(tweak: URL) -> some View {''')
# Rebrand Settings and configure the user's own Telegram feedback channel.
change("Feather/Views/Settings/SettingsView.swift",
       '''private let _donationsUrl = "https://github.com/sponsors/claration"
    private let _githubUrl = "https://github.com/claration/Feather"'''.replace("    ","\t"),
       '''private let _githubUrl = "https://github.com/RBx9"
    @AppStorage("rbx9.telegramChannelURL") private var _telegramChannelURL = ""''')
change("Feather/Views/Settings/SettingsView.swift",
       '''#if !NIGHTLY && !DEBUG
                    SettingsDonationCellView(site: _donationsUrl)
                #endif'''.replace("                    ","\t\t\t\t\t").replace("                #endif","\t\t\t\t#endif"),
       '''// No donation controls in RBx9.''')
change("Feather/Views/Settings/SettingsView.swift",
       '''_feedback()

                Section {'''.replace("                ","\t\t\t\t"),
       '''_feedback()

                Section {
                    TextField("https://t.me/yourchannel", text: $_telegramChannelURL)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Telegram Feedback Channel")
                } footer: {
                    Text("Enter your Telegram channel URL once. Submit Feedback will open this channel.")
                }

                Section {''')
change("Feather/Views/Settings/SettingsView.swift",
       '''UIApplication.open(URL(string: "\(_githubUrl)/issues/new/choose")!)''',
       '''if let url = URL(string: _telegramChannelURL.trimmingCharacters(in: .whitespacesAndNewlines)),
                   let host = url.host?.lowercased(),
                   url.scheme == "https",
                   host == "t.me" || host == "telegram.me" {
                    UIApplication.open(url)
                } else {
                    UIAlertController.showAlertWithOk(
                        title: "Telegram Channel",
                        message: "Add your Telegram channel link in Settings to enable feedback."
                    )
                }''')
change("Feather/Views/Settings/SettingsView.swift",
       '''Text(.localized("If any issues occur within the app please report it via the GitHub repository. When submitting an issue, make sure to submit detailed information."))''',
       '''Text("For help or feedback, use the Telegram channel configured above. Source code and releases are available on GitHub.")''')
change("Feather/Views/Settings/SettingsView.swift",
       '''Button(.localized("Submit Feedback"), systemImage: "safari")''',
       '''Button("Submit Feedback (Telegram)", systemImage: "paperplane.fill")''')

# Remove visible Feather donation and sponsor screens; retain original authors
# and GPL attribution in the About page.
about = root / "Feather/Views/Settings/About/AboutView.swift"
about.write_text('''// RBx9 About UI. Feather and other third-party credits retained under GPL-3.0.
import SwiftUI
import NimbleViews
import NimbleJSON

struct AboutView: View {
    var body: some View {
        NBList("About RBx9") {
            Section {
                VStack(spacing: 12) {
                    FRAppIconView(size: 72)
                    Text("RBx9")
                        .font(.largeTitle.bold())
                        .foregroundStyle(Color.accentColor)
                    Text("Version " + Bundle.main.version)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text("Developed by RBx9")
                        .font(.subheadline)
                }
                .frame(maxWidth: .infinity)
            }
            .listRowBackground(EmptyView())
            NBSection("Open-Source Credits") {
                Button {
                    UIApplication.open("https://github.com/RBx9")
                } label: {
                    Label("RBx9 · App customization", systemImage: "person.crop.circle")
                }
                Button {
                    UIApplication.open("https://github.com/claration/feather")
                } label: {
                    Label("Feather · Original open-source foundation", systemImage: "chevron.left.forwardslash.chevron.right")
                }
                Button {
                    UIApplication.open("https://github.com/claration/feather/blob/main/LICENSE")
                } label: {
                    Label("GPL-3.0 License", systemImage: "doc.text")
                }
                Text("Based on Feather. Original authors and open-source licenses remain credited.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
''')
print("RBx9 1.1 changes applied")
