#!/usr/bin/env python3
# RBx9 Signer 1.3.23 private: step-by-step injection log.
#  - Every injection / signing stage is appended to a file and flushed to disk
#    BEFORE it runs, so if the app crashes natively the last line names the step.
#  - Settings > Features > Injection Log shows, copies, shares and clears it.
# Apply AFTER upgrade_v1_3_22.py, to the upstream tree in ./feather
# (set RBX9_TREE to point at a different tree).
import os
import re as _re
from pathlib import Path

tree = Path(os.environ.get("RBX9_TREE", "feather"))
root = tree / "Feather"

SWIFT = r'''//
//  RBx9InjectLog.swift
//  RBx9 Signer
//
//  Crash breadcrumbs for IPA injection and signing. Each line is written and
//  fsync'd before the step it describes runs, so a native crash leaves the
//  name of the step in progress as the last line of the file.
//

import Foundation
import SwiftUI
import Darwin

enum RBx9InjectLog {
	private static let queue = DispatchQueue(label: "com.rbx9.injectlog")

	static var url: URL {
		FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
			.appendingPathComponent("RBx9-injection.log")
	}

	/// Physical memory this app currently holds, in MB. iOS kills apps that
	/// go over their limit without any crash report.
	private static func footprintMB() -> Int {
		var info = task_vm_info_data_t()
		var count = mach_msg_type_number_t(MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<integer_t>.size)
		let kr = withUnsafeMutablePointer(to: &info) {
			$0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
				task_info(mach_task_self_, task_flavor_t(TASK_VM_INFO), $0, &count)
			}
		}
		return kr == KERN_SUCCESS ? Int(info.phys_footprint / 1_048_576) : -1
	}

	/// Start a fresh log for a new signing run.
	static func begin(_ title: String) {
		queue.sync {
			try? FileManager.default.removeItem(at: url)
			FileManager.default.createFile(atPath: url.path, contents: nil)
		}
		add("=== \(title) ===")
		let v = ProcessInfo.processInfo.operatingSystemVersionString
		add("device: iOS \(v)")
	}

	static func add(_ message: String) {
		let line = "\(timestamp()) [\(footprintMB()) MB] \(message)\n"
		queue.sync {
			guard let data = line.data(using: .utf8) else { return }
			if !FileManager.default.fileExists(atPath: url.path) {
				FileManager.default.createFile(atPath: url.path, contents: nil)
			}
			guard let handle = try? FileHandle(forWritingTo: url) else { return }
			defer { try? handle.close() }
			_ = try? handle.seekToEnd()
			try? handle.write(contentsOf: data)
			try? handle.synchronize()
		}
	}

	static func read() -> String {
		queue.sync { (try? String(contentsOf: url, encoding: .utf8)) ?? "" }
	}

	static func clear() {
		queue.sync { try? FileManager.default.removeItem(at: url) }
	}

	private static func timestamp() -> String {
		let f = DateFormatter()
		f.dateFormat = "HH:mm:ss.SSS"
		return f.string(from: Date())
	}
}

struct RBx9InjectLogView: View {
	@State private var _text = ""

	var body: some View {
		ScrollView {
			Text(_text.isEmpty
				? "No injection log yet. Sign an IPA with a dylib, then open this page again. If the app crashed, the last line shows the step that was running."
				: _text)
				.font(.system(size: 11, design: .monospaced))
				.frame(maxWidth: .infinity, alignment: .leading)
				.padding()
				.textSelection(.enabled)
		}
		.navigationTitle("Injection Log")
		.navigationBarTitleDisplayMode(.inline)
		.toolbar {
			ToolbarItemGroup(placement: .topBarTrailing) {
				Button { _text = RBx9InjectLog.read() } label: { Image(systemName: "arrow.clockwise") }
				Button { UIPasteboard.general.string = _text } label: { Image(systemName: "doc.on.doc") }
					.disabled(_text.isEmpty)
				ShareLink(item: RBx9InjectLog.url) { Image(systemName: "square.and.arrow.up") }
					.disabled(_text.isEmpty)
				Button(role: .destructive) { RBx9InjectLog.clear(); _text = "" } label: { Image(systemName: "trash") }
					.disabled(_text.isEmpty)
			}
		}
		.onAppear { _text = RBx9InjectLog.read() }
	}
}
'''

(root / "Backend/Storage").mkdir(parents=True, exist_ok=True)
out = root / "Backend/Storage/RBx9InjectLog.swift"
assert not out.exists(), "RBx9InjectLog.swift already exists"
out.write_text(SWIFT)


def _insert(path, needle, new_lines, label, before=True):
    """Insert `new_lines` before/after the single line whose stripped text is
    `needle`, using that line's indentation."""
    p = root / path
    s = p.read_text()
    pattern = _re.compile(r'^([ \t]*)' + _re.escape(needle) + r'[ \t]*$', _re.M)
    found = pattern.findall(s)
    assert len(found) == 1, ("injectlog " + path + " " + label, len(found))
    indent = found[0]
    block = "\n".join((indent + ln) if ln else "" for ln in new_lines)

    def sub(m):
        return block + "\n" + m.group(0) if before else m.group(0) + "\n" + block

    p.write_text(pattern.sub(sub, s, count=1))


def _regex_insert_before(path, pattern_text, new_line, label):
    p = root / path
    s = p.read_text()
    pat = _re.compile(r'^([ \t]*)(' + pattern_text + ')', _re.M)
    found = pat.findall(s)
    assert len(found) == 1, ("injectlog " + path + " " + label, len(found))
    p.write_text(pat.sub(lambda m: m.group(1) + new_line + "\n" + m.group(0), s, count=1))


_SH = "Utilities/Handlers/SigningHandler.swift"
_TH = "Utilities/Handlers/TweakHandler.swift"

# --- Signing stages
_insert(_SH, "if _options.experiment_replaceSubstrateWithEllekit {", [
    'RBx9InjectLog.begin("Signing run")',
    'RBx9InjectLog.add("signing: before inject (injectionFiles=\\(_options.injectionFiles.count), ellekitReplace=\\(_options.experiment_replaceSubstrateWithEllekit), injectIntoExtensions=\\(_options.injectIntoExtensions))")',
], "begin")
_insert(_SH, "try await _locateMachosAndFixupArm64eSlice(for: movedAppPath)", [
    'RBx9InjectLog.add("signing: inject finished, starting arm64e fix-up")',
], "before fixup")
_insert(_SH, "try await _locateMachosAndFixupArm64eSlice(for: movedAppPath)", [
    'RBx9InjectLog.add("signing: arm64e fix-up finished")',
], "after fixup", before=False)
_insert(_SH, "let handler = ZsignHandler(appUrl: movedAppPath, options: _options, cert: appCertificate)", [
    'RBx9InjectLog.add("signing: before Zsign setup")',
], "zsign")
_insert(_SH, "try await handler.sign()", [
    'RBx9InjectLog.add("signing: before Zsign sign")',
], "sign")
_insert(_SH, "try await self.move()", [
    'RBx9InjectLog.add("signing: signed OK, moving app")',
], "move")

# --- Tweak injection stages
_insert(_TH, "try await _checkEllekit()", [
    'RBx9InjectLog.add("tweaks: start (files=\\(_urls.map { $0.lastPathComponent }.joined(separator: ", ")))")',
], "start")
_insert(_TH, "let baseTmpDir = _fileManager.temporaryDirectory.appendingPathComponent(\"FeatherTweak_\\(UUID().uuidString)\")", [
    'RBx9InjectLog.add("tweaks: after ElleKit check (files=\\(_urls.map { $0.lastPathComponent }.joined(separator: ", ")))")',
], "after ellekit")

_regex_insert_before(_TH, r'guard Self\._rbx9LooksLikeMachO\(url\) else \{',
    'RBx9InjectLog.add("tweaks: dylib \\(url.lastPathComponent) validating")', "validate")
_regex_insert_before(_TH, r'_ = Zsign\.changeDylibPath\(\s*appExecutable: destinationURL\.path,',
    'RBx9InjectLog.add("tweaks: dylib copied, rewriting Substrate path in \\(destinationURL.lastPathComponent)")', "changepath dylib")
_regex_insert_before(_TH, r'_ = Zsign\.injectDyLib\(\s*appExecutable: appexe\.path,\s*with: "\\\(_options',
    'RBx9InjectLog.add("tweaks: injecting \\(destinationURL.lastPathComponent) into the app executable")', "inject dylib")
_regex_insert_before(_TH, r'_ = Zsign\.changeDylibPath\(\s*appExecutable: fexe\.path,',
    'RBx9InjectLog.add("tweaks: framework \\(framework.lastPathComponent) rewriting Substrate path")', "changepath framework")
_insert(_TH, "let handler = AR(with: url)", [
    'RBx9InjectLog.add("tweaks: extracting deb \\(url.lastPathComponent)")',
], "deb")
_insert(_TH, "_injectIntoExtension(extensionURL: extensionURL, dylibName: dylibName)", [
    'RBx9InjectLog.add("tweaks: extension \\(extensionURL.lastPathComponent) <- \\(dylibName)")',
], "extension")
_insert(_TH, "_injectIntoAllExtensions(dylibNames: _injectedDylibNames)", [
    'RBx9InjectLog.add("tweaks: injecting into app extensions")',
], "extensions start")

# --- Settings entry
_insert("Views/Settings/SettingsView.swift", "NavigationLink(destination: ConfigurationView()) {", [
    'NavigationLink(destination: RBx9InjectLogView()) {',
    '\tLabel("Injection Log", systemImage: "doc.text.magnifyingglass")',
    '}',
], "settings link")

cfg = tree / "Feather.xcconfig"
c = cfg.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.22") != 1:
    raise RuntimeError("v1.3.23: expected base 1.3.22")
cfg.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.22", "FEATHER_PROJECT_VERSION=1.3.23", 1))
print("RBx9 v1.3.23 private: injection step log")
