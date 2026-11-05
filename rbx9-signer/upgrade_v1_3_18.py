#!/usr/bin/env python3
# RBx9 Signer v1.3.18 private: repair "Ready" installation handoff.
# Retain manual fallback and error detail display; never publish automatically.
from pathlib import Path

root=Path("feather")
path=root/"Feather/Views/Library/Install/InstallPreviewView.swift"
src=path.read_text()

def once(old,new,reason):
    global src
    old=old.replace(r"\t", "\t")
    new=new.replace(r"\t", "\t")
    n=src.count(old)
    if n!=1:
        raise RuntimeError(f"RBx9 v1.3.18 {reason}: expected 1 match, got {n}")
    src=src.replace(old,new,1)

once(
    '    @State private var rbx9FailureDetails = ""',
    '''    @State private var rbx9FailureDetails = ""
    @State private var rbx9InstallHint = ""
    @State private var rbx9DidAttemptHandoff = false''',
    "add retry state"
)

# The old Semi Local path only presents a Safari sheet. When the iOS
# presentation gets suppressed (e.g. nested sheet during signing), the
# status stays Ready forever with no actionable control.
once(
    r'''\t\t\t\tif case .ready = newStatus {
\t\t\t\t\tif _serverMethod == 0 {
\t\t\t\t\t\tUIApplication.shared.open(URL(string: installer.iTunesLink)!)
\t\t\t\t\t} else if _serverMethod == 1 {
\t\t\t\t\t\t_isWebviewPresenting = true
\t\t\t\t\t}
\t\t\t\t}''',
    r'''\t\t\t\tif case .ready = newStatus {
                    if !rbx9DidAttemptHandoff {
                        rbx9DidAttemptHandoff = true
                        // Give the signing sheet time to finish its transition.
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) {
                            if case .ready = viewModel.status {
                                rbx9OpenNativeInstaller()
                            }
                        }
                    }
\t\t\t\t}''',
    "replace unreliable automatic Ready handoff"
)

once(
    r'''\t\t\tif viewModel.isCompleted {
\t\t\t\tButton {''',
    r'''\t\t\tif case .ready = viewModel.status {
                VStack(alignment: .trailing, spacing: 8) {
                    Button {
                        rbx9OpenNativeInstaller()
                    } label: {
                        Label("Install Now", systemImage: "square.and.arrow.down.fill")
                            .font(.subheadline.weight(.semibold))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(.cyan)

                    if _serverMethod == 1 {
                        Button {
                            _isWebviewPresenting = true
                        } label: {
                            Label("Try Web Installer", systemImage: "safari")
                                .font(.caption)
                        }
                        .buttonStyle(.borderless)
                    }
                    if !rbx9InstallHint.isEmpty {
                        Text(rbx9InstallHint)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.trailing)
                            .lineLimit(3)
                    }
                }
                .padding(.trailing, 12)
                .padding(.bottom, 8)
            }
\t\t\tif viewModel.isCompleted {
\t\t\t\tButton {''',
    "show manual installer action when Ready"
)

once(
    r'''\tprivate func _install() {''',
    r'''    // iOS may not present a nested Safari sheet at the end of signing.
    // Direct itms-services handoff tries the native OS installer; the user
    // can explicitly retry or open the legacy web method if iOS rejects it.
    private func rbx9OpenNativeInstaller() {
        let target = _serverMethod == 1 ? installer.iTunesLinkExternal : installer.iTunesLink
        guard let url = URL(string: target) else {
            rbx9InstallHint = "Could not create an installation link. Try Web Installer."
            return
        }
        rbx9InstallHint = "If no iOS install prompt appears, try the Web Installer or change Server Type in Settings."
        UIApplication.shared.open(url, options: [:]) { accepted in
            if !accepted {
                DispatchQueue.main.async {
                    rbx9InstallHint = "iOS rejected the link. Try Web Installer, or use Fully Local with a valid SSL certificate."
                }
            }
        }
    }

\tprivate func _install() {''',
    "add installer handoff helper"
)

assert 'Label("Install Now"' in src and 'rbx9OpenNativeInstaller()' in src
assert '"Try Web Installer"' in src
path.write_text(src)

config=root/"Feather.xcconfig"
c=config.read_text()
assert c.count("FEATHER_PROJECT_VERSION=1.3.17")==1
config.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.17","FEATHER_PROJECT_VERSION=1.3.18"))
print("RBx9 1.3.18 private: native install handoff from Ready, manual retry and Web fallback")
