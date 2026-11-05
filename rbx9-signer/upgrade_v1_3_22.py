#!/usr/bin/env python3
# RBx9 Signer 1.3.22 private: injection crash hardening.
#  - Only run the native arm64e fix-up on universal (fat) Mach-O files.
#  - Reject non-Mach-O dylibs with a clear error before the native injector runs.
#  - Do not crash on a certificate with an empty team identifier.
# Apply AFTER upgrade_v1_3_21.py, to the upstream tree in ./feather.
from pathlib import Path

root = Path("feather/Feather")

# --- Injection crash hardening ---------------------------------------------
import re as _re

def _inj_line(path, needle, new_lines, label, replace=True, before=False):
    """Find the single line whose stripped text equals `needle` and replace it
    (or insert before it) with `new_lines`, keeping that line's indentation."""
    p = root / path
    s = p.read_text()
    pattern = _re.compile(r'^([ \t]*)' + _re.escape(needle) + r'[ \t]*$', _re.M)
    found = pattern.findall(s)
    assert len(found) == 1, ("inject " + path + " " + label, len(found))
    indent = found[0]
    block = "\n".join((indent + ln) if ln else "" for ln in new_lines)
    def sub(m):
        if replace:
            return block
        return block + "\n" + m.group(0) if before else m.group(0) + "\n" + block
    s = pattern.sub(sub, s, count=1)
    p.write_text(s)

_SH = "Utilities/Handlers/SigningHandler.swift"
_TH = "Utilities/Handlers/TweakHandler.swift"

_inj_line(_SH, "private func _locateMachosAndFixupArm64eSlice(for app: URL) async throws {", [
    "/// First four bytes of a file, big-endian, or nil if it cannot be read.",
    "private static func _rbx9MachOMagic(_ url: URL) -> UInt32? {",
    "\tguard let handle = try? FileHandle(forReadingFrom: url) else { return nil }",
    "\tdefer { try? handle.close() }",
    "\tguard let data = try? handle.read(upToCount: 4), data.count == 4 else { return nil }",
    "\tlet b = [UInt8](data)",
    "\treturn (UInt32(b[0]) << 24) | (UInt32(b[1]) << 16) | (UInt32(b[2]) << 8) | UInt32(b[3])",
    "}",
    "",
    "/// The arm64e fix-up only applies to universal (fat) binaries. Running the",
    "/// native patcher on anything else adds risk and no benefit.",
    "private static func _rbx9IsFatMachO(_ url: URL) -> Bool {",
    "\tguard let magic = _rbx9MachOMagic(url) else { return false }",
    "\treturn [0xCAFEBABE, 0xCAFEBABF, 0xBEBAFECA, 0xBFBAFECA].contains(magic)",
    "}",
    "",
    "private func _locateMachosAndFixupArm64eSlice(for app: URL) async throws {",
], "helpers")

_inj_line(_SH, "LCPatchMachOFixupARM64eSlice(fileURL.path)", [
    "if Self._rbx9IsFatMachO(fileURL) { LCPatchMachOFixupARM64eSlice(fileURL.path) }",
], "dylib fixup")

_inj_line(_SH, "LCPatchMachOFixupARM64eSlice(execURL.path)", [
    "if Self._rbx9IsFatMachO(execURL) { LCPatchMachOFixupARM64eSlice(execURL.path) }",
], "framework fixup")

_inj_line(_SH, "let ourTeamIdentifier = ourEntitlements.TeamIdentifier[0]", [
    "guard let ourTeamIdentifier = ourEntitlements.TeamIdentifier.first else { return }",
], "team id")

_inj_line(_TH, "private func _handleDylib(at url: URL) async throws {", [
    "/// Reject anything that is not a Mach-O before it reaches the native injector,",
    "/// which can crash the whole app on a corrupt or non-Mach-O file.",
    "private static func _rbx9LooksLikeMachO(_ url: URL) -> Bool {",
    "\tguard let handle = try? FileHandle(forReadingFrom: url) else { return false }",
    "\tdefer { try? handle.close() }",
    "\tguard let data = try? handle.read(upToCount: 4), data.count == 4 else { return false }",
    "\tlet b = [UInt8](data)",
    "\tlet magic = (UInt32(b[0]) << 24) | (UInt32(b[1]) << 16) | (UInt32(b[2]) << 8) | UInt32(b[3])",
    "\treturn [0xFEEDFACE, 0xCEFAEDFE, 0xFEEDFACF, 0xCFFAEDFE,",
    "\t\t\t0xCAFEBABE, 0xBEBAFECA, 0xCAFEBABF, 0xBFBAFECA].contains(magic)",
    "}",
    "",
    "private func _handleDylib(at url: URL) async throws {",
    "\tguard Self._rbx9LooksLikeMachO(url) else {",
    "\t\tthrow TweakHandlerError.invalidDylib(url.lastPathComponent)",
    "\t}",
], "validate")

_inj_line(_TH, "case noAccess", ["case noAccess", "case invalidDylib(String)"], "error case")

_thp = root / _TH
_ths = _thp.read_text()
assert "extension TweakHandlerError: LocalizedError" not in _ths
_thp.write_text(_ths.rstrip("\n") + """

extension TweakHandlerError: LocalizedError {
	var errorDescription: String? {
		if case .invalidDylib(let name) = self {
			return "\\(name) is not a valid dylib (it is not a Mach-O file), so it was not injected. Re-download or re-import it."
		}
		return nil
	}
}
""")

cfg = Path("feather/Feather.xcconfig")
c = cfg.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.21") != 1:
    raise RuntimeError("v1.3.22: expected base 1.3.21")
cfg.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.21", "FEATHER_PROJECT_VERSION=1.3.22", 1))
print("RBx9 v1.3.22 private: injection crash hardening")
