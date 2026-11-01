#!/usr/bin/env python3
# RBx9 v1.3.7: native SwiftUI transmission startup with accessibility support.
# GPL-3.0-only Feather derivative; do not alter signing behavior.
import json
import shutil
from pathlib import Path

root = Path("feather")
app = root / "Feather"
entry = app / "FeatherApp.swift"
src = entry.read_text()

def unique(old, new, label):
    global src
    count = src.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    src = src.replace(old, new, 1)

unique(
    "struct FeatherApp: App {\n",
    """struct FeatherApp: App {
    @Environment(\\.accessibilityReduceMotion) private var rbx9ReduceMotion
    @State private var rbx9ShowingStartup = true
""",
    "app launch state",
)

unique(
    "\t\t\t.onAppear {\n",
    """            .overlay {
                if rbx9ShowingStartup {
                    RBx9TransmissionStartup()
                        .transition(.opacity)
                        .zIndex(100)
                }
            }
            .task {
                // Only play on a fresh scene creation, not every background resume.
                // Reduce Motion users see a short static branded screen.
                do {
                    try await Task.sleep(
                        nanoseconds: rbx9ReduceMotion ? 450_000_000 : 2_350_000_000
                    )
                } catch {
                    return
                }
                withAnimation(.easeOut(duration: rbx9ReduceMotion ? 0.12 : 0.42)) {
                    rbx9ShowingStartup = false
                }
            }
            .onAppear {
""",
    "startup scene overlay",
)

# Keep this view in FeatherApp.swift, which already belongs to the Xcode target.
# App icons are normally compiled into a private AppIcon asset; mirror the selected
# icon into a normal image set so SwiftUI can display the genuine branded icon.
src += r"""

// MARK: - RBx9 startup transmission (iOS 16+)
private struct RBx9TransmissionStartup: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var booted = false
    @State private var scanPassed = false
    @State private var connected = false

    private let cyan = Color(red: 0.18, green: 0.89, blue: 0.84)
    private let midnight = Color(red: 0.022, green: 0.045, blue: 0.085)

    var body: some View {
        GeometryReader { geo in
            ZStack {
                midnight

                RadialGradient(
                    colors: [cyan.opacity(booted ? 0.20 : 0.06), .clear],
                    center: .center,
                    startRadius: 10,
                    endRadius: 360
                )
                .blur(radius: 24)
                .scaleEffect(booted ? 1.1 : 0.6)

                // A subtle circuit-like coordinate grid, drawn without extra assets.
                Path { path in
                    for x in stride(from: CGFloat(0), through: geo.size.width, by: 37) {
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: geo.size.height))
                    }
                    for y in stride(from: CGFloat(0), through: geo.size.height, by: 37) {
                        path.move(to: CGPoint(x: 0, y: y))
                        path.addLine(to: CGPoint(x: geo.size.width, y: y))
                    }
                }
                .stroke(cyan.opacity(0.045), lineWidth: 0.65)

                VStack(spacing: 22) {
                    Spacer(minLength: 0)

                    ZStack {
                        Circle()
                            .stroke(cyan.opacity(0.12), lineWidth: 1)
                            .frame(width: 242, height: 242)
                            .scaleEffect(booted ? 1 : 0.72)

                        Circle()
                            .trim(from: 0.04, to: 0.76)
                            .stroke(
                                cyan.opacity(0.8),
                                style: StrokeStyle(lineWidth: 2, lineCap: .round)
                            )
                            .frame(width: 224, height: 224)
                            .rotationEffect(.degrees(scanPassed ? 262 : -80))
                            .shadow(color: cyan.opacity(0.8), radius: 11)

                        Circle()
                            .trim(from: 0.13, to: 0.49)
                            .stroke(cyan.opacity(0.35), lineWidth: 1.2)
                            .frame(width: 192, height: 192)
                            .rotationEffect(.degrees(scanPassed ? -140 : 80))

                        RoundedRectangle(cornerRadius: 33, style: .continuous)
                            .fill(midnight.opacity(0.9))
                            .frame(width: 152, height: 152)
                            .overlay {
                                Image("RBx9LaunchIcon")
                                    .resizable()
                                    .scaledToFill()
                                    .frame(width: 144, height: 144)
                                    .clipShape(
                                        RoundedRectangle(cornerRadius: 29, style: .continuous)
                                    )
                            }
                            .overlay {
                                RoundedRectangle(cornerRadius: 33, style: .continuous)
                                    .stroke(cyan.opacity(0.50), lineWidth: 1.2)
                            }
                            .overlay {
                                // Single visible transmission beam, clipped to icon.
                                Rectangle()
                                    .fill(
                                        LinearGradient(
                                            colors: [.clear, cyan.opacity(0.06),
                                                     cyan.opacity(0.78), .clear],
                                            startPoint: .top,
                                            endPoint: .bottom
                                        )
                                    )
                                    .frame(height: 32)
                                    .offset(y: scanPassed ? 118 : -118)
                                    .opacity(reduceMotion ? 0 : 1)
                                    .clipShape(
                                        RoundedRectangle(cornerRadius: 33, style: .continuous)
                                    )
                            }
                            .shadow(color: cyan.opacity(booted ? 0.40 : 0.08), radius: 28)
                            .scaleEffect(booted ? 1 : 0.83)
                    }
                    .frame(width: 260, height: 260)
                    .opacity(booted ? 1 : 0.25)

                    VStack(spacing: 9) {
                        (
                            Text("RB").foregroundColor(.white)
                            + Text("x").foregroundColor(cyan)
                            + Text("9").foregroundColor(.white)
                        )
                        .font(.system(size: 52, weight: .black, design: .rounded))
                        .tracking(1.5)
                        .shadow(color: cyan.opacity(0.28), radius: 16)

                        Text("SIGNING STUDIO")
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                            .tracking(4)
                            .foregroundStyle(cyan.opacity(0.9))
                    }
                    .opacity(booted ? 1 : 0)
                    .offset(y: booted ? 0 : 16)

                    HStack(spacing: 8) {
                        ForEach(0..<5, id: \.self) { index in
                            Capsule()
                                .fill(cyan.opacity(connected || index < 2 ? 0.88 : 0.2))
                                .frame(width: index == 2 ? 25 : 13, height: 3)
                        }
                    }
                    .padding(.top, 4)
                    .opacity(booted ? 1 : 0)

                    Spacer(minLength: 0)

                    Text(connected ? "TRANSMISSION ESTABLISHED" : "INITIALIZING SECURE WORKSPACE")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .tracking(2)
                        .foregroundStyle(cyan.opacity(connected ? 0.88 : 0.42))
                        .contentTransition(.opacity)
                        .padding(.bottom, 40)
                }
                .padding(.horizontal, 24)
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .clipped()
        }
        .ignoresSafeArea()
        .task {
            guard !reduceMotion else {
                booted = true
                scanPassed = true
                connected = true
                return
            }
            withAnimation(.spring(response: 0.72, dampingFraction: 0.82)) {
                booted = true
            }
            try? await Task.sleep(nanoseconds: 300_000_000)
            withAnimation(.easeInOut(duration: 1.18)) {
                scanPassed = true
            }
            try? await Task.sleep(nanoseconds: 1_100_000_000)
            withAnimation(.easeOut(duration: 0.33)) {
                connected = true
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("RBx9 Signer starting")
    }
}
"""
entry.write_text(src)

icons = app / "Resources/Assets.xcassets/RBx9LaunchIcon.imageset"
icons.mkdir(parents=True, exist_ok=True)
shutil.copy2("rbx9-source-icon.png", icons / "rbx9-launch.png")
(icons / "Contents.json").write_text(json.dumps({
    "images": [{"filename": "rbx9-launch.png", "idiom": "universal"}],
    "info": {"author": "xcode", "version": 1}
}, indent=2) + "\n")

cfg = root / "Feather.xcconfig"
text = cfg.read_text()
old = "FEATHER_PROJECT_VERSION=1.3.6"
if text.count(old) != 1:
    raise RuntimeError("Expected v1.3.6 before transmission startup upgrade")
cfg.write_text(text.replace(old, "FEATHER_PROJECT_VERSION=1.3.7", 1))

assert src.count("RBx9TransmissionStartup()") == 1
assert src.count('Image("RBx9LaunchIcon")') == 1
print("RBx9 v1.3.7: native cyan transmission splash, logo, and Reduce Motion support")
