import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }

    /// Indigo → violet → pink, the RBx9 PDF brand gradient.
    static let brand = [Color(hex: 0x6366F1), Color(hex: 0xA855F7), Color(hex: 0xEC4899)]
}

extension LinearGradient {
    static let brand = LinearGradient(colors: Color.brand, startPoint: .topLeading, endPoint: .bottomTrailing)

    init(_ tool: Tool) {
        self.init(colors: tool.colors, startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

enum InputKind {
    case pdf, images, scan
}

enum Tool: String, CaseIterable, Identifiable {
    case merge, split, organize, remove, extract, rotate, compress
    case scan, imagesToPDF, pdfToImages
    case pageNumbers, watermark, protect, unlock, extractText

    var id: String { rawValue }

    var title: String {
        switch self {
        case .merge: return "Merge PDF"
        case .split: return "Split PDF"
        case .organize: return "Organize Pages"
        case .remove: return "Remove Pages"
        case .extract: return "Extract Pages"
        case .rotate: return "Rotate PDF"
        case .compress: return "Compress PDF"
        case .scan: return "Scan to PDF"
        case .imagesToPDF: return "Images to PDF"
        case .pdfToImages: return "PDF to Images"
        case .pageNumbers: return "Page Numbers"
        case .watermark: return "Watermark"
        case .protect: return "Protect PDF"
        case .unlock: return "Unlock PDF"
        case .extractText: return "PDF to Text (OCR)"
        }
    }

    var subtitle: String {
        switch self {
        case .merge: return "Combine PDFs in the order you want."
        case .split: return "Turn ranges or every page into separate PDFs."
        case .organize: return "Reorder, rotate and delete pages."
        case .remove: return "Delete pages you don’t need."
        case .extract: return "Pull selected pages into a new PDF."
        case .rotate: return "Rotate all pages or just some."
        case .compress: return "Make the file smaller."
        case .scan: return "Use the camera to scan paper documents."
        case .imagesToPDF: return "Convert photos and images into a PDF."
        case .pdfToImages: return "Save every page as a JPG or PNG."
        case .pageNumbers: return "Stamp page numbers on every page."
        case .watermark: return "Stamp text across every page."
        case .protect: return "Add a password to a PDF."
        case .unlock: return "Remove a PDF password you know."
        case .extractText: return "Get the text out, even from scans."
        }
    }

    var symbol: String {
        switch self {
        case .merge: return "doc.on.doc"
        case .split: return "scissors"
        case .organize: return "square.grid.2x2"
        case .remove: return "trash"
        case .extract: return "arrow.up.doc"
        case .rotate: return "rotate.right"
        case .compress: return "arrow.down.right.and.arrow.up.left"
        case .scan: return "doc.viewfinder"
        case .imagesToPDF: return "photo.on.rectangle"
        case .pdfToImages: return "photo"
        case .pageNumbers: return "number"
        case .watermark: return "drop"
        case .protect: return "lock"
        case .unlock: return "lock.open"
        case .extractText: return "text.viewfinder"
        }
    }

    /// Two-stop gradient for the tool's icon (matches the web app).
    var colors: [Color] {
        let hex: (UInt32, UInt32)
        switch self {
        case .merge: hex = (0xF43F5E, 0xFB923C)
        case .split: hex = (0xF97316, 0xFACC15)
        case .organize: hex = (0x8B5CF6, 0xD946EF)
        case .remove: hex = (0xEC4899, 0xF43F5E)
        case .extract: hex = (0x3B82F6, 0x06B6D4)
        case .rotate: hex = (0x14B8A6, 0x22C55E)
        case .compress: hex = (0x22C55E, 0x84CC16)
        case .scan: hex = (0x6366F1, 0x0EA5E9)
        case .imagesToPDF: hex = (0xF59E0B, 0xEF4444)
        case .pdfToImages: hex = (0x06B6D4, 0x6366F1)
        case .pageNumbers: hex = (0x6366F1, 0x8B5CF6)
        case .watermark: hex = (0x0EA5E9, 0x6366F1)
        case .protect: hex = (0x475569, 0x1E293B)
        case .unlock: hex = (0xA855F7, 0x6366F1)
        case .extractText: hex = (0x10B981, 0x0EA5E9)
        }
        return [Color(hex: hex.0), Color(hex: hex.1)]
    }

    var color: Color { colors[0] }

    var input: InputKind {
        switch self {
        case .scan: return .scan
        case .imagesToPDF: return .images
        default: return .pdf
        }
    }

    /// Whether a file opened from another app can go straight into this tool.
    func accepts(_ file: InputFile) -> Bool {
        let isPDF = file.name.lowercased().hasSuffix(".pdf")
        switch input {
        case .pdf: return isPDF
        case .images: return !isPDF
        case .scan: return false
        }
    }

    var allowsMultiple: Bool { self == .merge || self == .imagesToPDF || self == .scan }
    var minimumFiles: Int { self == .merge ? 2 : 1 }
}

// MARK: - Options

enum SplitMode: String, CaseIterable, Identifiable {
    case ranges = "Custom ranges", every = "Every page", chunks = "Fixed size"
    var id: String { rawValue }
}

enum CompressionLevel: String, CaseIterable, Identifiable {
    case less = "Less", recommended = "Recommended", extreme = "Extreme"
    var id: String { rawValue }

    /// Level name understood by compress.js.
    var key: String { rawValue.lowercased() }

    /// Extreme also tries redrawing whole pages as JPEGs (scale, quality).
    var raster: (scale: CGFloat, quality: CGFloat)? { self == .extreme ? (1, 0.45) : nil }
}

enum PageSizeOption: String, CaseIterable, Identifiable {
    case fit = "Same as image", a4 = "A4", letter = "US Letter"
    var id: String { rawValue }
}

enum MarginOption: String, CaseIterable, Identifiable {
    case none = "None", small = "Small", large = "Large"
    var id: String { rawValue }
    var points: CGFloat { self == .none ? 0 : self == .small ? 18 : 36 }
}

enum ImageFormat: String, CaseIterable, Identifiable {
    case jpeg = "JPG", png = "PNG"
    var id: String { rawValue }
}

enum NumberPosition: String, CaseIterable, Identifiable {
    case bottomCenter = "Bottom center", bottomRight = "Bottom right", bottomLeft = "Bottom left"
    case topCenter = "Top center", topRight = "Top right", topLeft = "Top left"
    var id: String { rawValue }
}

enum NumberFormat: String, CaseIterable, Identifiable {
    case plain = "1", page = "Page 1", slash = "1 / 10", pageOf = "Page 1 of 10"

    var id: String { rawValue }

    func text(_ n: Int, of total: Int) -> String {
        switch self {
        case .plain: return "\(n)"
        case .page: return "Page \(n)"
        case .slash: return "\(n) / \(total)"
        case .pageOf: return "Page \(n) of \(total)"
        }
    }
}

struct ToolOptions {
    var splitMode = SplitMode.ranges
    var splitRanges = "1-2, 3-"
    var chunkSize = 2
    var removeRanges = "1"
    var extractRanges = "1-3"
    var rotateAngle = 90
    var rotateRanges = ""
    var compression = CompressionLevel.recommended
    var pageSize = PageSizeOption.fit
    var margin = MarginOption.none
    var imageFormat = ImageFormat.jpeg
    var dpi = 150
    var numberPosition = NumberPosition.bottomCenter
    var numberFormat = NumberFormat.plain
    var firstNumber = 1
    var numberFontSize: Double = 11
    var watermarkText = "CONFIDENTIAL"
    var watermarkSize: Double = 60
    var watermarkOpacity: Double = 0.2
    var watermarkDiagonal = true
    var password = ""
    var confirmPassword = ""
}

/// One page in the Organize tool's editable list.
struct PageItem: Identifiable {
    let id = UUID()
    let index: Int
    var rotation = 0
    let thumbnail: UIImage
}
