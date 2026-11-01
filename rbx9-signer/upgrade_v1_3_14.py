#!/usr/bin/env python3
# RBx9 Signer v1.3.14 — expose installation errors to diagnose update conflicts.
# Does not bypass iOS update signature, entitlement, or Team ID checks.
# GPL-3.0-only derivative of Feather.
from pathlib import Path

root = Path("feather")
swift = root / "Feather/Views/Library/Install/InstallPreviewView.swift"
src = swift.read_text()

def replace_once(old, new, purpose):
    global src
    if src.count(old) != 1:
        raise RuntimeError(f"{purpose}: expected 1 anchor, saw {src.count(old)}")
    src = src.replace(old, new, 1)

replace_once(
    '''\t@State private var progressTask: Task<Void, Never>?
''',
    '''\t@State private var progressTask: Task<Void, Never>?
    @State private var rbx9ShowFailureDetails = false
    @State private var rbx9FailureDetails = ""
''',
    "diagnostics state"
)

# A failed HTTP payload stream, failed idvice install, or server startup will
# now reveal its underlying error. Apple's itms-services install may reject
# updates asynchronously; in that case iOS owns the error, and the app must
# not falsely claim it knows the cause.
replace_once(
    '''\t\t.onAppear(perform: _install)
''',
    '''        .onReceive(viewModel.$status) { newStatus in
            if case .broken(let error) = newStatus {
                let nsError = error as NSError
                rbx9FailureDetails = [
                    "App: " + (app.name ?? "Unknown"),
                    "Bundle ID: " + (app.identifier ?? "Unknown"),
                    "Error: " + nsError.localizedDescription,
                    "Domain: " + nsError.domain + " (" + String(nsError.code) + ")",
                    "Details: " + String(describing: error),
                    "If this IPA installs only when its previous version is absent, verify that both versions were signed with the same Apple team, certificate and bundle identifier. A different application-identifier cannot ordinarily replace an existing app while preserving its data."
                ].joined(separator: "\\n")
                rbx9ShowFailureDetails = true
            }
        }
        .alert("Installation Details", isPresented: $rbx9ShowFailureDetails) {
            Button("Copy Details") {
                UIPasteboard.general.string = rbx9FailureDetails
            }
            Button("Close", role: .cancel) {}
        } message: {
            Text(rbx9FailureDetails)
        }
\t\t.onAppear(perform: _install)
''',
    "display backend failure diagnostics"
)

# Keep the existing "Error" icon/text but provide a durable way to reopen
# the details if the user dismisses the popup.
replace_once(
    '''\t\tLabel(viewModel.statusLabel, systemImage: viewModel.statusImage)
\t\t\t.padding()
''',
    '''        VStack(alignment: .leading, spacing: 8) {
            if case .broken = viewModel.status {
                Button {
                    rbx9ShowFailureDetails = true
                } label: {
                    Label("View Error Details", systemImage: "info.circle")
                        .font(.caption)
                }
                .buttonStyle(.borderless)
            }
            Label(viewModel.statusLabel, systemImage: viewModel.statusImage)
        }
\t\t\t.padding()
''',
    "reopen diagnostics after failure"
)

for marker in ['rbx9ShowFailureDetails', 'Button("Copy Details")',
               'Label("View Error Details"', '.broken(let error)']:
    if marker not in src:
        raise RuntimeError("Diagnostics component missing: "+marker)

swift.write_text(src)

cfg = root / "Feather.xcconfig"
config = cfg.read_text()
if config.count("FEATHER_PROJECT_VERSION=1.3.13") != 1:
    raise RuntimeError("Expected v1.3.13 before v1.3.14 diagnostic update")
cfg.write_text(config.replace("FEATHER_PROJECT_VERSION=1.3.13",
                                "FEATHER_PROJECT_VERSION=1.3.14", 1))
print("RBx9 1.3.14: diagnostic UI on installer failures; no change to signing or replacement policy")
