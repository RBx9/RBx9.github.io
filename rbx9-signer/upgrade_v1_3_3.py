#!/usr/bin/env python3
# RBx9 v1.3.3 - remove duplicate Advanced dylib items and
# modernize the remaining useful advanced navigation rows.
# GPL-3.0 Feather derivative.
from pathlib import Path

root = Path("feather")
p = root/"Feather/Views/Signing/SigningView.swift"
s = p.read_text()

anchor = 'NBSection(.localized("Advanced")) {'
if s.count(anchor) != 1:
    raise RuntimeError("Could not find the Advanced section")
a = s.rfind('\n', 0, s.index(anchor)) + 1
if 'DisclosureGroup(.localized("Modify")) {' not in s[a:a+150]:
    raise RuntimeError("Could not find Advanced/Modify group")
properties = 'NavigationLink(.localized("Properties")) {'
b = s.rfind('\n', 0, s.index(properties, a)) + 1
new = '''        NBSection("Advanced Tools") {
            NavigationLink {
                SigningFrameworksView(
                    app: app,
                    options: $_temporaryOptions.optional()
                )
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "shippingbox.fill")
                        .foregroundStyle(Color.accentColor)
                        .frame(width: 26)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Frameworks & PlugIns")
                            .font(.subheadline.weight(.semibold))
                        Text("Manage bundled frameworks and extensions")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 5)
            }

            NavigationLink {
                SigningEntitlementsView(
                    bindingValue: $_temporaryOptions.appEntitlementsFile
                )
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "checkmark.shield.fill")
                        .foregroundStyle(Color.accentColor)
                        .frame(width: 26)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Entitlements")
                            .font(.subheadline.weight(.semibold))
                        Text("Inspect and configure app permissions")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 5)
            }
'''
s = s[:a] + new + s[b:]
old = '''\t\t\tNavigationLink(.localized("Properties")) {
\t\t\t\tForm { SigningOptionsView(
\t\t\t\t\toptions: $_temporaryOptions,
\t\t\t\t\ttemporaryOptions: _optionsManager.options
\t\t\t\t)}
\t\t\t\t.navigationTitle(.localized("Properties"))
\t\t\t}'''
new = '''            NavigationLink {
                Form {
                    SigningOptionsView(
                        options: $_temporaryOptions,
                        temporaryOptions: _optionsManager.options
                    )
                }
                .navigationTitle("App Properties")
            } label: {
                HStack(spacing: 12) {
                    Image(systemName: "slider.horizontal.3")
                        .foregroundStyle(Color.accentColor)
                        .frame(width: 26)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("App Properties")
                            .font(.subheadline.weight(.semibold))
                        Text("Advanced signing configuration")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 5)
            }'''
if s.count(old) != 1:
    raise RuntimeError("Could not find old Advanced Properties link")
s = s.replace(old, new, 1)
p.write_text(s)

cfg = root/"Feather.xcconfig"
v = cfg.read_text()
if v.count("FEATHER_PROJECT_VERSION=1.3.2") != 1:
    raise RuntimeError("Unexpected version before v1.3.3")
cfg.write_text(v.replace("FEATHER_PROJECT_VERSION=1.3.2",
                         "FEATHER_PROJECT_VERSION=1.3.3", 1))
print("RBx9 Advanced Tools now has only Frameworks, Entitlements, Properties")
