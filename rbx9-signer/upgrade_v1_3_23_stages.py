#!/usr/bin/env python3
# RBx9 Signer 1.3.23 (part 2): log the early signing stages too, so a crash
# that happens with NO tweaks selected is also pinned to a step.
# Apply AFTER upgrade_v1_3_23.py. Set RBX9_TREE to point at a different tree.
import os
import re as _re
from pathlib import Path

root = Path(os.environ.get("RBX9_TREE", "feather")) / "Feather"
SH = root / "Utilities/Handlers/SigningHandler.swift"
s = SH.read_text()


def once(old, new, label):
    global s
    assert s.count(old) == 1, ("stages " + label, s.count(old))
    s = s.replace(old, new, 1)


def before(needle, line, label):
    global s
    pat = _re.compile(r'^([ \t]*)' + _re.escape(needle) + r'[ \t]*$', _re.M)
    found = pat.findall(s)
    assert len(found) == 1, ("stages " + label, len(found))
    s = pat.sub(lambda m: m.group(1) + line + "\n" + m.group(0), s, count=1)


# The log now starts when the app copy starts, not at the inject stage.
once('RBx9InjectLog.begin("Signing run")',
     'RBx9InjectLog.add("signing: modify stage")', "no second begin")
before("try _fileManager.createDirectoryIfNeeded(at: _uniqueWorkDir)",
       'RBx9InjectLog.begin("Signing run: copying app")', "begin")
before("try _fileManager.copyItem(at: appUrl, to: movedAppURL)",
       'RBx9InjectLog.add("signing: copying app bundle to work folder")', "copy")
before("_movedAppPath = movedAppURL",
       'RBx9InjectLog.add("signing: copy finished")', "copy done")
before("try await _modifyDict(using: infoDictionary, with: _options, to: movedAppPath)",
       'RBx9InjectLog.add("signing: modifying Info.plist")', "modifydict")
before("try await _removeFiles(for: movedAppPath, from: _options.removeFiles)",
       'RBx9InjectLog.add("signing: removing selected files")', "removefiles")
before("try await _removePresetFiles(for: movedAppPath)",
       'RBx9InjectLog.add("signing: removing preset files")', "preset")
before("try await _removeWatchIfNeeded(for: movedAppPath)",
       'RBx9InjectLog.add("signing: removing watch app if needed")', "watch")
before("try await _locateMachosAndChangeToSDK26(for: movedAppPath)",
       'RBx9InjectLog.add("signing: changing Mach-O SDK to 26")', "sdk26")
before("try await _mergeEntitlements(for: movedAppPath, with: _options)",
       'RBx9InjectLog.add("signing: merging entitlements")', "entitlements")
SH.write_text(s)
print("RBx9 v1.3.23 part 2: early signing stage log")
