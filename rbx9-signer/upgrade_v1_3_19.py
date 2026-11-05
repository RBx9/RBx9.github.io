#!/usr/bin/env python3
# RBx9 Signer 1.3.19 private: show a separate, styled installation recovery card
# only if the installer stays on Ready for nine seconds. Preserve signing.
from pathlib import Path

root = Path("feather")
preview = root / "Feather/Views/Library/Install/InstallPreviewView.swift"
src = preview.read_text()

def once(old, new, label):
    global src
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"v1.3.19 {label}: expected one match; found {count}")
    src = src.replace(old, new, 1)

once(
    '    @State private var rbx9DidAttemptHandoff = false',
    '''    @State private var rbx9DidAttemptHandoff = false
    @State private var rbx9RecoveryTask: Task<Void, Never>?
    @Binding private var rbx9RecoveryExpanded: Bool''',
    "recovery task and sheet height binding"
)

once(
    '''init(app: AppInfoPresentable, isSharing: Bool = false) {
\t\tself.app = app
\t\tself.isSharing = isSharing'''.replace(r"\t", "\t"),
    '''init(app: AppInfoPresentable, isSharing: Bool = false,
         recoveryExpanded: Binding<Bool> = .constant(false)) {
\t\tself.app = app
\t\tself.isSharing = isSharing
        self._rbx9RecoveryExpanded = recoveryExpanded'''.replace(r"\t", "\t"),
    "recovery binding initializer"
)

# The original preview is a ZStack in a 200-point sheet; placing more controls
# in that ZStack caused controls to cover the icon, Ready label, and each other.
# Keep the normal compact preview untouched. Only add a non-overlapping card
# underneath the original preview when the parent expands the sheet.
once(
    '''\t\tZStack {
\t\t\tInstallProgressView(app: app, viewModel: viewModel)
\t\t\t_status()
\t\t\t_button()
\t\t}
\t\t.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)'''.replace(r"\t", "\t"),
    '''        VStack(spacing: 0) {
            ZStack {
                InstallProgressView(app: app, viewModel: viewModel)
                _status()
                _button()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            if rbx9RecoveryExpanded && !isSharing {
                rbx9RecoveryCard()
                    .padding(.horizontal, 10)
                    .padding(.bottom, 12)
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)''',
    "move recovery card outside the overlay"
)

# The initial automatic handoff stays in place. A recovery card is revealed only
# when Ready has not advanced to payload sending, installing or completion.
ready_token = "if case .ready = newStatus {"
next_token = "if case .sendingPayload = newStatus"
if src.count(ready_token) != 1 or src.count(next_token) != 1:
    raise RuntimeError("v1.3.19: cannot locate Ready handoff")
begin = src.index(ready_token)
end = src.index(next_token, begin)
if not (0 < end - begin < 1900):
    raise RuntimeError("v1.3.19: unexpected Ready handler length")
src = src[:begin] + '''if case .ready = newStatus {
                    if !rbx9DidAttemptHandoff {
                        rbx9DidAttemptHandoff = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) {
                            if case .ready = viewModel.status {
                                rbx9OpenNativeInstaller()
                            }
                        }
                    }
                    rbx9RecoveryTask?.cancel()
                    rbx9RecoveryTask = Task { @MainActor in
                        try? await Task.sleep(nanoseconds: 9_000_000_000)
                        guard !Task.isCancelled else { return }
                        if case .ready = viewModel.status {
                            withAnimation(.easeInOut(duration: 0.25)) {
                                rbx9RecoveryExpanded = true
                            }
                        }
                    }
                } else {
                    rbx9RecoveryTask?.cancel()
                    rbx9RecoveryTask = nil
                    rbx9RecoveryExpanded = false
                }

                ''' + src[end:]

# Remove ALL Ready-specific actions from _button() so that view remains
# responsible only for the original Open-after-success control.
btn = src.index("private func _button()")
start = src.index("if case .ready = viewModel.status {", btn)
finish = src.index("if viewModel.isCompleted {", start)
if not (0 < finish-start < 2100):
    raise RuntimeError("v1.3.19: incorrect Ready overlay range")
src = src[:start] + src[finish:]
if "Label(\"Install Now\"" in src or "Try Web Installer\"" in src:
    raise RuntimeError("v1.3.19: obsolete action still in preview overlay")

# Keep helper and errors but replace verbose status text with compact card help.
once("If no iOS install prompt appears, try the Web Installer or change Server Type in Settings.",
     "No install prompt? Try Web Installer or another server type.", "shorten help")
once("iOS rejected the link. Try Web Installer, or use Fully Local with a valid SSL certificate.",
     "iOS declined the link. Try Web Installer or change Server Type.", "shorten handoff error")

# Cancel timer on exit; never show the fallback when already installing.
once(
    '''\t\t.onDisappear {
\t\t\tprogressTask?.cancel()'''.replace(r"\t", "\t"),
    '''\t\t.onDisappear {
            rbx9RecoveryTask?.cancel()
            rbx9RecoveryTask = nil
            rbx9RecoveryExpanded = false
\t\t\tprogressTask?.cancel()'''.replace(r"\t", "\t"),
    "cancel recovery when installer closes"
)

# A compact dark RBx9 card with two separate, accessible hit targets.
# The card is inside the vertical layout, never absolute-positioned.
card = r'''
    @ViewBuilder
    private func rbx9RecoveryCard() -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 9) {
                Image(systemName: "arrow.clockwise.circle.fill")
                    .font(.system(size: 22))
                    .foregroundStyle(Color.cyan)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Installation still pending")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                    Text("No progress after several seconds on Ready.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                }
                Spacer(minLength: 0)
            }

            HStack(spacing: 9) {
                Button {
                    rbx9OpenNativeInstaller()
                } label: {
                    Label("Retry Install", systemImage: "arrow.clockwise")
                        .font(.system(size: 13, weight: .semibold))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, minHeight: 43)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.black)
                .background(
                    LinearGradient(colors: [
                        Color(red: 0.22, green: 0.87, blue: 0.95),
                        Color(red: 0.10, green: 0.72, blue: 0.92)
                    ], startPoint: .topLeading, endPoint: .bottomTrailing),
                    in: RoundedRectangle(cornerRadius: 13, style: .continuous)
                )

                if _serverMethod == 1 {
                    Button {
                        _isWebviewPresenting = true
                    } label: {
                        Label("Web Installer", systemImage: "safari")
                            .font(.system(size: 13, weight: .semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                            .frame(maxWidth: .infinity, minHeight: 43)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Color.cyan)
                    .background(Color.cyan.opacity(0.10),
                                in: RoundedRectangle(cornerRadius: 13, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous)
                        .strokeBorder(Color.cyan.opacity(0.30), lineWidth: 1))
                }
            }

            if !rbx9InstallHint.isEmpty {
                Text(rbx9InstallHint)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(13)
        .background(Color(UIColor.tertiarySystemBackground),
                    in: RoundedRectangle(cornerRadius: 17, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 17, style: .continuous)
            .strokeBorder(Color.cyan.opacity(0.19), lineWidth: 1))
        .accessibilityElement(children: .contain)
    }

'''
once('private func rbx9OpenNativeInstaller() {', card + 'private func rbx9OpenNativeInstaller() {', "recovery card definition")

assert 'if rbx9RecoveryExpanded && !isSharing' in src
assert 'Task.sleep(nanoseconds: 9_000_000_000)' in src
assert 'Label("Retry Install"' in src
assert 'Label("Web Installer"' in src
assert 'if viewModel.isCompleted {' in src

preview.write_text(src)

# Drive sheet height from the child status; no redundant nested sheet, no
# larger idle UI. The 200 pt original expands only while recovery is visible.
library = root / "Feather/Views/Library/LibraryView.swift"
s = library.read_text()
old = '@State private var _selectedInstallAppPresenting: AnyApp?'
if s.count(old) != 1:
    raise RuntimeError("v1.3.19: missing LibraryView installer state")
s = s.replace(old, old + '\n    @State private var rbx9RecoveryExpanded = false', 1)
old = '''\t\t\t.sheet(item: $_selectedInstallAppPresenting) { app in
\t\t\t\tInstallPreviewView(app: app.base, isSharing: app.archive)
\t\t\t\t\t.presentationDetents([.height(200)])
\t\t\t\t\t.presentationDragIndicator(.visible)
\t\t\t}'''.replace(r"\t", "\t")
new = '''\t\t\t.sheet(item: $_selectedInstallAppPresenting, onDismiss: {
                rbx9RecoveryExpanded = false
            }) { app in
\t\t\t\tInstallPreviewView(app: app.base, isSharing: app.archive,
                    recoveryExpanded: $rbx9RecoveryExpanded)
                    .presentationDetents([.height(rbx9RecoveryExpanded ? 400 : 200)])
\t\t\t\t\t.presentationDragIndicator(.visible)
\t\t\t}'''.replace(r"\t", "\t")
if s.count(old) != 1:
    raise RuntimeError("v1.3.19: expected one LibraryView installer sheet; got " + str(s.count(old)))
s = s.replace(old, new, 1)
library.write_text(s)

config = root / "Feather.xcconfig"
c = config.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.18") != 1:
    raise RuntimeError("v1.3.19: expected base 1.3.18")
config.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.18",
                            "FEATHER_PROJECT_VERSION=1.3.19", 1))
print("RBx9 v1.3.19 private: 9-second Ready guard, independently laid-out recovery card, dynamic sheet height")
