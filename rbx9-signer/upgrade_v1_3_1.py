#!/usr/bin/env python3
# RBx9 v1.3.1: quick editor action bars, swipe UX, precise Install tab taps,
# and polished direct-install settings. Feather-derived GPL-3.0 code.
from pathlib import Path
root = Path("feather")
app = root / "Feather"

def replace_exact(relative, before, after, matches=1):
    target = root / relative
    text = target.read_text()
    count = text.count(before)
    if count != matches:
        raise RuntimeError(f"{relative}: expected {matches}, found {count} of {before[:85]!r}")
    target.write_text(text.replace(before, after, matches))
    print("Updated", relative)

replace_exact("Feather.xcconfig",
              "FEATHER_PROJECT_VERSION=1.3.0",
              "FEATHER_PROJECT_VERSION=1.3.1")

# One shared action bar, pinned below both quick editors. A single tap
# applies the current in-memory tweak settings using the parent signer.
actions = app / "Views/Signing/RBx9EditorActionBar.swift"
actions.write_text("""// SPDX-License-Identifier: GPL-3.0-only
import SwiftUI

struct RBx9EditorActionBar: View {
    var onSignAndInstall: () -> Void
    var onSignOnly: () -> Void
    var enabled: Bool = true

    var body: some View {
        HStack(spacing: 12) {
            Button(action: onSignAndInstall) {
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
            .accessibilityHint("Apply the current tweak choices, sign, and open installation.")
            Button(action: onSignOnly) {
                Label("Sign Only", systemImage: "signature")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(Color.accentColor)
                    .frame(minWidth: 108, minHeight: 54)
                    .padding(.horizontal, 6)
                    .background(Color.accentColor.opacity(0.12),
                                in: RoundedRectangle(cornerRadius: 17, style: .continuous))
            }
            .accessibilityHint("Apply the current tweak choices and sign without installing.")
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 6)
        .background(.regularMaterial)
    }
}
""")

# The ordinary Tweaks editor is shown by Add or Remove Dylibs and the right swipe.
# Keep its action bar visible even when scrolling a long tweak list.
p = app / "Views/Signing/SigningTweaksView.swift"
s = p.read_text()
needle = '''\t\t.toolbar {
\t\t\tNBToolbarButton('''
if s.count(needle) != 1:
    raise RuntimeError("Could not locate Tweaks toolbar")
s = s.replace(needle, '''        .safeAreaInset(edge: .bottom, spacing: 0) {
            RBx9EditorActionBar(
                onSignAndInstall: { onApply(true) },
                onSignOnly: { onApply(false) }
            )
        }
'''+needle, 1)
p.write_text(s)
print("Pinned action bar in Tweaks editor")

# Manage Existing Dylibs gets the same fixed bar, including its OFF states.
p = app / "Views/Signing/Shared/SigningDylibView.swift"
s = p.read_text()
needle = '        .onAppear(perform: _loadDylibs)'
if s.count(needle) != 1:
    raise RuntimeError("Could not find existing dylib editor .onAppear")
s = s.replace(needle, '''        .safeAreaInset(edge: .bottom, spacing: 0) {
            RBx9EditorActionBar(
                onSignAndInstall: { onApply(true) },
                onSignOnly: { onApply(false) },
                enabled: options != nil
            )
        }
'''+needle, 1)
p.write_text(s)
print("Pinned action bar in existing dylibs editor")

# Right swipe should open the Tweaks page (the screenshot the user supplied)
# rather than the Existing Dylibs toggle page, without manual navigation back.
p = app / "Views/Signing/SigningView.swift"
s = p.read_text()
before = '''    .sheet(isPresented: $_showSwipeDylibEditor) {
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
            }'''
after = '''    .sheet(isPresented: $_showSwipeDylibEditor) {
                NavigationStack {
                    SigningTweaksView(
                        options: $_temporaryOptions,
                        onApply: { shouldInstall in
                            // Let the editor sheet finish dismissing before starting
                            // signing, so the install presentation is not obscured.
                            _showSwipeDylibEditor = false
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.30) {
                                _start(installAfterSigning: shouldInstall)
                            }
                        }
                    )
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button("Done") { _showSwipeDylibEditor = false }
                        }
                    }
                }
            }'''
if s.count(before) != 1:
    raise RuntimeError("Swipe editor sheet differs from RBx9 v1.3")
s = s.replace(before,after,1)
p.write_text(s)
print("Swiping right now opens the main Tweaks editor")

# Select the install action based on the actual Library section, not only on
# the AppInfoPresentable.isSigned flag. That flag wasn't reliable for row taps
# while the app was displayed under Install.
p = app / "Views/Library/LibraryView.swift"
s = p.read_text()
needle = '''selectedDylibAppPresenting: $_selectedDylibAppPresenting,
\t\t\t\t\t\t\t\tselectedInstallAppPresenting: $_selectedInstallAppPresenting,'''
if s.count(needle) != 2:
    raise RuntimeError("Expected signed and imported Library cells")
# section order: Signed first, Imported second
s = s.replace(needle, '''selectedDylibAppPresenting: $_selectedDylibAppPresenting,
                                opensInstallerOnTap: true,
\t\t\t\t\t\t\t\tselectedInstallAppPresenting: $_selectedInstallAppPresenting,''', 1)
s = s.replace(needle, '''selectedDylibAppPresenting: $_selectedDylibAppPresenting,
                                opensInstallerOnTap: false,
\t\t\t\t\t\t\t\tselectedInstallAppPresenting: $_selectedInstallAppPresenting,''', 1)
p.write_text(s)
print("Library rows now receive explicit tab-specific tap actions")

p = app / "Views/Library/LibraryCellView.swift"
s = p.read_text()
needle = '''@Binding var selectedDylibAppPresenting: AnyApp?'''
if s.count(needle) != 1:
    raise RuntimeError("Missing LibraryCellView swipe binding")
s = s.replace(needle, needle+'''
    var opensInstallerOnTap: Bool = false''', 1)
# Ensure the whole cell handles a normal tap. Keep edit mode selection.
before = '''} else if app.isSigned {
                selectedInstallAppPresenting = AnyApp(base: app)
            } else {
                selectedSigningAppPresenting = AnyApp(base: app)
            }'''
after = '''} else if opensInstallerOnTap {
                selectedInstallAppPresenting = AnyApp(base: app)
            } else {
                selectedSigningAppPresenting = AnyApp(base: app)
            }'''
if s.count(before) != 1:
    raise RuntimeError("Could not find RBx9 row tap handler")
s = s.replace(before,after,1)
# Ensure the visual action labels also reflect the actual Library section.
s = s.replace(
    'Image(systemName: app.isSigned ? "square.and.arrow.down.fill" : "signature")',
    'Image(systemName: opensInstallerOnTap ? "square.and.arrow.down.fill" : "signature")')
s = s.replace(
    'Text(app.isSigned ? "Install" : "Sign")',
    'Text(opensInstallerOnTap ? "Install" : "Sign")')
s = s.replace(
    '.accessibilityLabel(app.isSigned ? "Install application" : "Sign application")',
    '.accessibilityLabel(opensInstallerOnTap ? "Install application" : "Sign application")')
p.write_text(s)
print("Whole Install row now opens installer reliably")

# Match the icon language of other controls.
p = app / "Views/Settings/Installation/Server & SSL/ServerView.swift"
s = p.read_text()
before = '''Toggle("Try direct installation link (skip web page)",
                           isOn: $_skipSafariInstallPage)'''
after = '''Toggle("Direct installation link (skip web page)",
                           systemImage: "arrow.down.app",
                           isOn: $_skipSafariInstallPage)'''
if s.count(before)!=1:
    raise RuntimeError("Missing direct installation toggle")
s=s.replace(before,after,1)
p.write_text(s)
print("Renamed direct installation setting with matching SF Symbol")
print("RBx9 v1.3.1 editor and install navigation patches applied")
