#!/usr/bin/env python3
# RBx9 v1.3.4 - Install-tab row opens Re-sign; only Install button opens installer.
# Feather-derived code remains GPL-3.0.
from pathlib import Path

root=Path("feather")
p=root/"Feather/Views/Library/LibraryCellView.swift"
s=p.read_text()
start=s.index('\t\t\t_appIcon(for: app)')
end=s.index('\n\t\t}\n\t\t.padding(isRegular ? 12 : 0)', start)
# The row itself must NOT own a tap handler: otherwise SwiftUI may dispatch
# both the trailing Install button AND the ancestor .onTapGesture.
# Two distinct borderless Buttons prevent nested tap propagation.
replacement='''            Button {
                if isEditing {
                    _toggleSelection()
                } else {
                    // Applies in both Sign and Install sections. A signed app
                    // should reopen signing options when its row is tapped.
                    selectedSigningAppPresenting = AnyApp(base: app)
                }
            } label: {
                HStack(spacing: 18) {
                    _appIcon(for: app)
                    NBTitleWithSubtitleView(
                        title: app.name ?? .localized("Unknown"),
                        subtitle: _desc,
                        linelimit: 0
                    )
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.borderless)
            .accessibilityLabel(app.isSigned ? "Re-sign " + (app.name ?? "app") : "Sign " + (app.name ?? "app"))

            if !isEditing {
                Button {
                    // Installation is *only* initiated from this explicit
                    // Install button; never from the rest of the cell.
                    if opensInstallerOnTap {
                        selectedInstallAppPresenting = AnyApp(base: app)
                    } else {
                        selectedSigningAppPresenting = AnyApp(base: app)
                    }
                } label: {
                    HStack(spacing: 5) {
                        Image(systemName: opensInstallerOnTap ? "square.and.arrow.down.fill" : "signature")
                        Text(opensInstallerOnTap ? "Install" : "Sign")
                    }
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(Color.black)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(
                        Color(red: 0.32, green: 0.88, blue: 0.81),
                        in: Capsule()
                    )
                }
                .buttonStyle(.borderless)
                .accessibilityLabel(opensInstallerOnTap ? "Install application" : "Sign application")
            }'''
if 'opensInstallerOnTap' not in s[start:end]:
    raise RuntimeError("Expected RBx9 install badge in LibraryCellView")
s=s[:start]+replacement+s[end:]
tapStart=s.index('\n\t\t.onTapGesture {',s.index('.padding(isRegular ? 12 : 0)'))
swipeStart=s.index('.swipeActions(edge: .leading',tapStart)
if 'selectedInstallAppPresenting' not in s[tapStart:swipeStart]:
    raise RuntimeError("Unexpected row tap section; refusing to patch")
s=s[:tapStart]+'\n        '+s[swipeStart:]
if '.onTapGesture {' in s[s.index('.padding(isRegular ? 12 : 0)'):s.index('.contextMenu {')]:
    raise RuntimeError("Ancestor row tap handler was not fully removed")
p.write_text(s)

config=root/"Feather.xcconfig"
version=config.read_text()
old="FEATHER_PROJECT_VERSION=1.3.3"
if version.count(old)!=1:raise RuntimeError("Expected v1.3.3")
config.write_text(version.replace(old,"FEATHER_PROJECT_VERSION=1.3.4",1))
print("RBx9 v1.3.4 - row: re-sign, explicit pill: install, gestures isolated.")
