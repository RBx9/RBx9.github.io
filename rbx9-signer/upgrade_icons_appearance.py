#!/usr/bin/env python3
# GPL-3.0 RBx9 v1.1 polish: optional icons; preserve user's selected original as default.
from pathlib import Path
import plistlib
import shutil

root = Path("feather")
app = root / "Feather"
original = Path("rbx9-source-icon.png")
if not original.is_file():
    raise RuntimeError("The original selected RB9 icon must remain present")

names = [
    ("RBx9Ocean", "Ocean Glow"),
    ("RBx9Midnight", "Midnight"),
    ("RBx9Aurora", "Aurora"),
    ("RBx9Frost", "Frost"),
    ("RBx9Mono", "Monochrome"),
    ("RBx9Electric", "Electric")
]

# Replace all six Feather alternate icons, without touching the original AppIcon.appiconset.
source = Path("rbx9-alt-icons")
icons = app / "Resources/Icons"
if icons.is_dir():
    shutil.rmtree(icons)
alt = icons / "RBx9"
alt.mkdir(parents=True, exist_ok=True)
for key, _ in names:
    for scale in (2, 3):
        file = f"{key}@{scale}x.png"
        candidate = source / file
        if not candidate.is_file():
            raise RuntimeError("Missing alternate: " + str(candidate))
        shutil.copy2(candidate, alt / file)

# Alternate icons are opt-in. nil is the iOS system's unmodified default app icon.
selector = app / "Views/Settings/App Icon/AppIconView.swift"
selector.write_text("""// RBx9 alternate icons. Based on Feather under GPL-3.0.
import SwiftUI
import NimbleViews

extension AppIconView {
    struct AltIcon: Identifiable {
        var displayName: String
        var author: String
        var key: String?
        var image: UIImage
        var id: String { key ?? displayName }

        init(displayName: String, author: String, key: String? = nil) {
            self.displayName = displayName
            self.author = author
            self.key = key
            self.image = altImage(key)
        }
    }

    static func altImage(_ name: String?) -> UIImage {
        let path = Bundle.main.bundleURL
            .appendingPathComponent((name ?? "AppIcon60x60") + "@2x.png")
        return UIImage(contentsOfFile: path.path) ?? UIImage()
    }
}

struct AppIconView: View {
    @Binding var currentIcon: String?

    private let options: [AltIcon] = [
        AltIcon(displayName: "Original RB9 (Default)", author: "RBx9", key: nil),
        AltIcon(displayName: "Ocean Glow", author: "RBx9", key: "RBx9Ocean"),
        AltIcon(displayName: "Midnight", author: "RBx9", key: "RBx9Midnight"),
        AltIcon(displayName: "Aurora", author: "RBx9", key: "RBx9Aurora"),
        AltIcon(displayName: "Frost", author: "RBx9", key: "RBx9Frost"),
        AltIcon(displayName: "Monochrome", author: "RBx9", key: "RBx9Mono"),
        AltIcon(displayName: "Electric", author: "RBx9", key: "RBx9Electric")
    ]

    var body: some View {
        NBList("App Icon") {
            NBSection("RBx9 Icons") {
                ForEach(options) { icon in
                    Button {
                        UIApplication.shared.setAlternateIconName(icon.key) { _ in
                            currentIcon = UIApplication.shared.alternateIconName
                        }
                    } label: {
                        HStack(spacing: 18) {
                            Image(uiImage: icon.image)
                                .appIconStyle()
                            NBTitleWithSubtitleView(
                                title: icon.displayName,
                                subtitle: icon.key == nil ? "Your original icon" : "Optional design",
                                linelimit: 0
                            )
                            Spacer(minLength: 0)
                            if currentIcon == icon.key {
                                Image(systemName: "checkmark")
                                    .bold()
                                    .foregroundStyle(Color.accentColor)
                            }
                        }
                    }
                }
            }
        }
        .onAppear {
            currentIcon = UIApplication.shared.alternateIconName
        }
    }
}
""")

plist_path = app / "Resources/Info.plist"
with plist_path.open("rb") as f:
    info = plistlib.load(f)
primary = info.setdefault("CFBundleIcons", {}).get("CFBundlePrimaryIcon")
if not primary:
    raise RuntimeError("Existing primary icon missing; refusing to change default")
info["CFBundleIcons"]["CFBundleAlternateIcons"] = {
    key: {"CFBundleIconFiles": [key], "UIPrerenderedIcon": False}
    for key, _ in names
}
with plist_path.open("wb") as f:
    plistlib.dump(info, f, sort_keys=False)

# Preserve saved appearance choices, but provide RBx9's dark + cyan defaults.
def change(rel, before, after):
    p = app / rel
    src = p.read_text()
    if src.count(before) != 1:
        raise RuntimeError(f"Expected appearance anchor: {rel} / {before}")
    p.write_text(src.replace(before, after, 1))
    print("Appearance:", rel)

change("Views/Settings/Appearance/AppearanceView.swift",
       "UIUserInterfaceStyle.unspecified.rawValue",
       "UIUserInterfaceStyle.dark.rawValue")
change("Views/Settings/Appearance/AppearanceView.swift",
       'private var _selectedColorHex: String = "#848ef9"',
       'private var _selectedColorHex: String = "#2DE2CF"')
change("Views/Settings/Appearance/AppearanceTintColorView.swift",
       'private var _selectedColorHex: String = "#848ef9"',
       'private var _selectedColorHex: String = "#2DE2CF"')
tint = app / "Views/Settings/Appearance/AppearanceTintColorView.swift"
s = tint.read_text()
begin = s.index('private let _tintOptions: [(name: String, hex: String)] = [')
end = s.index(chr(10) + chr(9) + ']', begin) + 3
s = s[:begin] + '''private let _tintOptions: [(name: String, hex: String)] = [
        ("RBx9 Cyan", "#2DE2CF"),
        ("Ice Blue", "#43D9FF"),
        ("Ocean", "#168EFF"),
        ("Aqua", "#17CBB3"),
        ("Royal", "#4478FF"),
        ("White Blue", "#C8F7FF")
    ]''' + s[end:]
tint.write_text(s)
print("RBx9 optional icon set ready; original primary icon is unchanged")
