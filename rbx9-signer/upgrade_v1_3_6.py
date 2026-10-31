#!/usr/bin/env python3
# RBx9 v1.3.6 - Injection-focused copy for tweak edits.
# The genuine re-sign + optional installation process remains unchanged.
# GPL-3.0 Feather derivative.
from pathlib import Path

root = Path("feather")
app = root/"Feather"

def replace_file(rel, old, new, count=1):
    p = root/rel
    s = p.read_text()
    actual = s.count(old)
    if actual != count:
        raise RuntimeError(f"{rel}: expected {count} matches, found {actual} for {old[:80]!r}")
    p.write_text(s.replace(old,new,count))
    print("RBx9 injection copy:",rel)

replace_file("Feather.xcconfig","FEATHER_PROJECT_VERSION=1.3.5","FEATHER_PROJECT_VERSION=1.3.6")
bar=app/"Views/Signing/RBx9EditorActionBar.swift"
s=bar.read_text()
for old,new in (
    ('Label("Sign & Install", systemImage:', 'Label("Inject & Install", systemImage:'),
    ('Label("Sign Only", systemImage:', 'Label("Inject Only", systemImage:'),
    ('Apply the current tweak choices, sign, and open installation.',
     'Inject the selected tweaks, re-sign the IPA, then open installation.'),
    ('Apply the current tweak choices and sign without installing.',
     'Inject the selected tweaks and sign the IPA without installing.')
):
    if s.count(old)!=1:raise RuntimeError("Editor label changed: "+old)
    s=s.replace(old,new,1)
bar.write_text(s)

p=app/"Views/Signing/SigningView.swift"
s=p.read_text()
anchor='''    @State private var _rbx9DylibStateLoaded = false'''
if s.count(anchor)!=1: raise RuntimeError("Missing injection status anchor")
s=s.replace(anchor,anchor+'''
    @State private var _rbx9InjectingTweaks = false

    private var _rbx9HasTweakChanges: Bool {
        !_temporaryOptions.injectionFiles.isEmpty
            || !_temporaryOptions.disInjectionFiles.isEmpty
            || !_temporaryOptions.rbx9DeletedDylibPaths.isEmpty
    }''',1)

# UI only: when the user is modifying an app's dylibs, name the operation by
# the user goal. Never pretend signing has been eliminated.
labels=[
    ('Label("Sign & Install", systemImage: "square.and.arrow.down.fill")',
     'Label(_rbx9HasTweakChanges ? "Inject & Install" : "Sign & Install", systemImage: "square.and.arrow.down.fill")'),
    ('Label("Sign Only", systemImage: "signature")',
     'Label(_rbx9HasTweakChanges ? "Inject Only" : "Sign Only", systemImage: "signature")')
]
for before,after in labels:
    if s.count(before)!=1:raise RuntimeError("Main signing button label changed: "+before)
    s=s.replace(before,after,1)

# The Quick Tweak Editor calls _start from two different NavigationLinks.
before='''onApply: { shouldInstall in _start(installAfterSigning: shouldInstall) }'''
after='''onApply: { shouldInstall in
                        _rbx9InjectingTweaks = true
                        _start(installAfterSigning: shouldInstall)
                    }'''
if s.count(before)!=2:
    raise RuntimeError(f"Expected 2 Quick Tweak Editor apply callbacks, found {s.count(before)}")
s=s.replace(before,after,2)

# The swipe editor is a separate sheet; dismiss it before presenting progress.
before='''                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.30) {
                                _start(installAfterSigning: shouldInstall)
                            }'''
after='''                            _rbx9InjectingTweaks = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.30) {
                                _start(installAfterSigning: shouldInstall)
                            }'''
if s.count(before)!=1:raise RuntimeError("Swipe editor apply callback changed")
s=s.replace(before,after,1)

# Standard Sign & Install on an app with known tweak changes uses the same label.
before='''guard !_isSigning else { return }
        if installAfterSigning == nil {'''
after='''guard !_isSigning else { return }
        _rbx9InjectingTweaks = _rbx9InjectingTweaks || _rbx9HasTweakChanges
        if installAfterSigning == nil {'''
if s.count(before)!=1:raise RuntimeError("Signing start guard changed")
s=s.replace(before,after,1)

# Compact overlay while the signing operation is running. This says "injecting"
# without hiding the fact the IPA is re-signed prior to installation.
before='.disabled(_isSigning)'
after='''            .disabled(_isSigning)
            .overlay {
                if _isSigning && _rbx9InjectingTweaks {
                    VStack(spacing: 12) {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .tint(Color.accentColor)
                            .scaleEffect(1.1)
                        Text("Injecting Tweaks…")
                            .font(.headline)
                            .foregroundStyle(.primary)
                        Text("Preparing and re-signing the modified IPA")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(24)
                    .background(
                        .regularMaterial,
                        in: RoundedRectangle(cornerRadius: 20, style: .continuous)
                    )
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.black.opacity(0.24))
                }
            }
'''
if s.count(before)!=1:raise RuntimeError("Signing view animation anchor changed")
s=s.replace(before,after,1)
p.write_text(s)

print("RBx9 v1.3.6 injection-first UX ready; original signing and installation semantics retained.")
