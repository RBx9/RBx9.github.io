// RBx9 v1.1 optional alternate icon renderer.
// The user's selected original RB9 image is read as input and is NEVER modified.
import AppKit
import CoreImage
import Foundation

guard CommandLine.arguments.count == 3 else {
    fatalError("Usage: swift make_alternates.swift original.png output-directory")
}
let sourceURL = URL(fileURLWithPath: CommandLine.arguments[1])
let destination = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
guard let original = CIImage(contentsOf: sourceURL) else { fatalError("Missing original icon") }
let context = CIContext(options: [.useSoftwareRenderer: false])

func filter(_ name: String, input: CIImage, params: [String: Any] = [:]) -> CIImage {
    guard let effect = CIFilter(name: name) else { fatalError("Missing Core Image filter: \(name)") }
    effect.setValue(input, forKey: kCIInputImageKey)
    params.forEach { effect.setValue($0.value, forKey: $0.key) }
    guard let output = effect.outputImage else { fatalError("No output for \(name)") }
    return output.cropped(to: original.extent)
}
func controls(_ input: CIImage, brightness: Double = 0, contrast: Double = 1, saturation: Double = 1) -> CIImage {
    filter("CIColorControls", input: input, params: [
        kCIInputBrightnessKey: brightness,
        kCIInputContrastKey: contrast,
        kCIInputSaturationKey: saturation
    ])
}
func tint(_ input: CIImage, radians: Double) -> CIImage {
    filter("CIHueAdjust", input: input, params: [kCIInputAngleKey: radians])
}
func write(_ image: CIImage, name: String) throws {
    guard let master = context.createCGImage(image, from: original.extent) else {
        fatalError("Could not render \(name)")
    }
    for (suffix, size) in [("@2x", 120), ("@3x", 180)] {
        guard let bitmap = CGContext(
            data: nil, width: size, height: size,
            bitsPerComponent: 8, bytesPerRow: 0,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { fatalError("Bitmap context failed") }
        bitmap.interpolationQuality = .high
        bitmap.draw(master, in: CGRect(x: 0, y: 0, width: size, height: size))
        guard let icon = bitmap.makeImage(),
              let png = NSBitmapImageRep(cgImage: icon).representation(using: .png, properties: [:])
        else { fatalError("PNG encode failed") }
        let output = destination.appendingPathComponent("\(name)\(suffix).png")
        try png.write(to: output, options: .atomic)
        print("Wrote \(output.path) (\(png.count) bytes)")
    }
}
let candidates: [(String, CIImage)] = [
    ("RBx9Ocean", controls(original, brightness: 0.035, contrast: 1.14, saturation: 1.65)),
    ("RBx9Midnight", controls(original, brightness: -0.16, contrast: 1.48, saturation: 0.95)),
    ("RBx9Aurora", controls(tint(original, radians: 0.75), brightness: 0.02, contrast: 1.11, saturation: 1.30)),
    ("RBx9Frost", controls(filter("CIColorInvert", input: original), brightness: 0.005, contrast: 1.04, saturation: 0.75)),
    ("RBx9Mono", controls(filter("CIPhotoEffectMono", input: original), contrast: 1.20)),
    ("RBx9Electric", controls(tint(original, radians: -0.63), brightness: 0.03, contrast: 1.23, saturation: 1.72))
]
for (name, image) in candidates {
    try write(image, name: name)
}
