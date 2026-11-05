#!/usr/bin/env python3
# RBx9 Signer 1.3.19 (no version bump): installer diagnostics for "stuck at Ready".
#  - ServerInstaller reports the real server startup error (was swallowed by try?)
#    and shuts down a half-started Vapor app.
#  - Install progress polling runs every 300 ms instead of every 1 ms.
#  - The recovery card shows a non-mutating local server check.
#  - Expanded installer sheet is 440 pt (was 400) to fit the extra line.
# Apply AFTER upgrade_v1_3_19.py, to the upstream tree in ./feather.
from pathlib import Path

root = Path("feather")

def patch(path, edits):
    p = root / path
    s = p.read_text()
    for old, new, label in edits:
        n = s.count(old)
        if n != 1:
            raise RuntimeError(f"installer-diagnostics {path} {label}: expected 1 match, found {n}")
        s = s.replace(old, new, 1)
    p.write_text(s)

OLD_READY = """                            if case .ready = viewModel.status {
                                rbx9OpenNativeInstaller()
                            }"""
NEW_READY = """                            if case .ready = viewModel.status {
                                // Semi Local: use upstream Feather's proven path, the
                                // Safari page that redirects to itms-services. Direct
                                // opening from the app is kept as the Retry action.
                                if _serverMethod == 1 {
                                    _isWebviewPresenting = true
                                } else {
                                    rbx9OpenNativeInstaller()
                                }
                            }"""

patch("Feather/Backend/Server/ServerInstaller.swift", [
    ("\t\tself._server = try? setupApp(port: port)",
     "\t\t// Propagate the real error (TLS, port, address) instead of hiding it.\n"
     "\t\tself._server = try setupApp(port: port)",
     "setup error"),
    ("        } catch {\n            startupError = error\n            DispatchQueue.main.async {",
     "        } catch {\n            startupError = error\n"
     "            // Release the half-started Vapor application so it is not leaked.\n"
     "            _server?.shutdown()\n            _server = nil\n"
     "            DispatchQueue.main.async {",
     "startup cleanup"),
])

patch("Feather/Views/Library/Install/InstallPreviewView.swift", [
    ("try? await Task.sleep(nanoseconds: 1_000_000) // 1 ms",
     "try? await Task.sleep(nanoseconds: 300_000_000) // 300 ms", "poll interval"),
    ("    @State private var rbx9InstallHint = \"\"",
     "    @State private var rbx9InstallHint = \"\"\n    @State private var rbx9ServerCheck = \"\"", "state"),
    ("                            withAnimation(.easeInOut(duration: 0.25)) {\n"
     "                                rbx9RecoveryExpanded = true\n                            }",
     "                            withAnimation(.easeInOut(duration: 0.25)) {\n"
     "                                rbx9RecoveryExpanded = true\n                            }\n"
     "                            let report = await rbx9CheckLocalServer()\n"
     "                            if case .ready = viewModel.status { rbx9ServerCheck = report }",
     "run check"),
    ("                    rbx9RecoveryTask = nil\n                    rbx9RecoveryExpanded = false\n                }\n\n                if case .sendingPayload",
     "                    rbx9RecoveryTask = nil\n                    rbx9RecoveryExpanded = false\n"
     "                    rbx9ServerCheck = \"\"\n                    rbx9InstallHint = \"\"\n                }\n\n                if case .sendingPayload",
     "reset"),
    ("            if !rbx9InstallHint.isEmpty {",
     "            if !rbx9ServerCheck.isEmpty {\n                Text(rbx9ServerCheck)\n"
     "                    .font(.caption2)\n                    .foregroundStyle(.secondary)\n"
     "                    .fixedSize(horizontal: false, vertical: true)\n            }\n\n"
     "            if !rbx9InstallHint.isEmpty {", "card text"),
    (OLD_READY,
     NEW_READY, "semi-local web installer first"),
    ("private func rbx9OpenNativeInstaller() {",
     '''    /// Non-mutating diagnostic. Requests the /install page (not the manifest),
    /// so it cannot move the installer out of `.ready` by itself.
    private func rbx9CheckLocalServer() async -> String {
        guard _serverMethod == 1 else {
            return "iOS never requested the install manifest. Full Local needs a trusted SSL certificate in Settings > Server & SSL."
        }
        var request = URLRequest(url: installer.pageEndpoint, timeoutInterval: 3)
        request.httpMethod = "GET"
        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            if (response as? HTTPURLResponse)?.statusCode == 200 {
                return "Installer server is running, but iOS never requested the install manifest. Try Retry Install or Web Installer."
            }
            return "Installer server answered unexpectedly. Try another Server Type."
        } catch {
            return "Installer server did not respond (" + error.localizedDescription + "). Check Wi-Fi/IP settings or Server Type."
        }
    }

private func rbx9OpenNativeInstaller() {''', "check function"),
])

patch("Feather/Views/Library/LibraryView.swift", [
    ("rbx9RecoveryExpanded ? 400 : 200", "rbx9RecoveryExpanded ? 440 : 200", "sheet height"),
])
print("RBx9 installer diagnostics applied")
