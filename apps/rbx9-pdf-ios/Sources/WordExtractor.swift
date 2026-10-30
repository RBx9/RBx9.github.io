import PDFKit
import UIKit
import Vision

/// Pulls positioned text and images out of each page in the format docx.js
/// expects (see pdf/docx.js). Scanned pages go through on-device OCR.
enum WordExtractor {
    struct Item: Encodable {
        let t: String
        let x, y, w, s: Double
        let b, i: Bool
        let f: String
    }

    struct Picture: Encodable {
        let x, y, w, h: Double
        let data: String
        let mime: String
    }

    struct Page: Encodable {
        let width, height: Double
        let items: [Item]
        let images: [Picture]
    }

    static func extract(_ file: InputFile, progress: (String) -> Void) throws -> (json: String, textChars: Int, ocrPages: Int) {
        let pdf = try PDFEngine.document(file)
        let cg = try PDFEngine.cgDocument(file)
        var pages: [Page] = []
        var chars = 0
        var ocrPages = 0
        for i in 0..<pdf.pageCount {
            progress("Reading page \(i + 1) of \(pdf.pageCount)…")
            guard let page = pdf.page(at: i), let cgPage = cg.page(at: i + 1) else { continue }
            let box = page.bounds(for: .cropBox)
            try autoreleasepool {
                var items = textItems(page, box: box)
                var images = ImageScanner(page: cgPage, box: box).scan()
                if items.isEmpty {
                    progress("Recognizing text on page \(i + 1)…")
                    items = try ocrItems(cgPage)
                    if !items.isEmpty {
                        ocrPages += 1
                        // The page-sized scan picture isn't needed once its text is recognized.
                        images = images.filter { $0.w < box.width * 0.85 || $0.h < box.height * 0.85 }
                    }
                }
                chars += items.reduce(0) { $0 + $1.t.count }
                pages.append(Page(width: box.width, height: box.height, items: items, images: images))
            }
        }
        let data = try JSONEncoder().encode(pages)
        return (String(decoding: data, as: UTF8.self), chars, ocrPages)
    }

    private static let boldPattern = "bold|black|heavy|semibold|demi"
    private static let italicPattern = "italic|oblique"

    /// One item per font run on each text line.
    static func textItems(_ page: PDFPage, box: CGRect) -> [Item] {
        guard let selection = page.selection(for: box) else { return [] }
        var items: [Item] = []
        for line in selection.selectionsByLine() {
            guard let attributed = line.attributedString, attributed.length > 0 else { continue }
            let bounds = line.bounds(for: page)
            let length = Double(attributed.length)
            let string = attributed.string as NSString
            attributed.enumerateAttribute(.font, in: NSRange(location: 0, length: attributed.length)) { value, range, _ in
                let text = string.substring(with: range).replacingOccurrences(of: "\n", with: " ")
                guard !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
                let font = value as? UIFont
                var size = Double(font?.pointSize ?? 0)
                if size <= 1 || size > Double(bounds.height) * 3 { size = Double(bounds.height) * 0.8 }
                let name = font?.fontName ?? ""
                let traits = font?.fontDescriptor.symbolicTraits ?? []
                let start = Double(range.location) / length
                let share = Double(range.length) / length
                items.append(Item(
                    t: text,
                    x: Double(bounds.minX - box.minX) + Double(bounds.width) * start,
                    // Baseline sits about a fifth of the line height above the bottom.
                    y: Double(box.maxY - bounds.minY) - Double(bounds.height) * 0.2,
                    w: Double(bounds.width) * share,
                    s: size,
                    b: traits.contains(.traitBold) || name.range(of: boldPattern, options: [.regularExpression, .caseInsensitive]) != nil,
                    i: traits.contains(.traitItalic) || name.range(of: italicPattern, options: [.regularExpression, .caseInsensitive]) != nil,
                    f: name))
            }
        }
        return items
    }

    static func ocrItems(_ page: CGPDFPage) throws -> [Item] {
        guard let image = PDFEngine.image(of: page, scale: 2).cgImage else { return [] }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        try VNImageRequestHandler(cgImage: image).perform([request])
        let size = PDFEngine.visibleSize(page)
        return (request.results ?? []).compactMap { observation in
            guard let text = observation.topCandidates(1).first?.string else { return nil }
            let r = observation.boundingBox // normalized, bottom-left origin
            let height = Double(r.height * size.height)
            return Item(t: text,
                        x: Double(r.minX * size.width),
                        y: Double((1 - r.minY) * size.height) - height * 0.2,
                        w: Double(r.width * size.width),
                        s: height * 0.8,
                        b: false, i: false, f: "")
        }
    }
}

/// Finds the images drawn on a page by walking its content stream and tracking
/// the current transform, so each picture's position and size are known.
final class ImageScanner {
    private let page: CGPDFPage
    private let box: CGRect
    private var xObjects: CGPDFDictionaryRef?
    fileprivate var ctm = CGAffineTransform.identity
    fileprivate var stack: [CGAffineTransform] = []
    private var found: [WordExtractor.Picture] = []

    init(page: CGPDFPage, box: CGRect) {
        self.page = page
        self.box = box
        var resources: CGPDFDictionaryRef?
        var objects: CGPDFDictionaryRef?
        if let dict = page.dictionary,
           CGPDFDictionaryGetDictionary(dict, "Resources", &resources), let resources,
           CGPDFDictionaryGetDictionary(resources, "XObject", &objects) {
            xObjects = objects
        }
    }

    fileprivate static func from(_ info: UnsafeMutableRawPointer?) -> ImageScanner {
        Unmanaged<ImageScanner>.fromOpaque(info!).takeUnretainedValue()
    }

    func scan() -> [WordExtractor.Picture] {
        guard xObjects != nil, let table = CGPDFOperatorTableCreate() else { return [] }
        defer { CGPDFOperatorTableRelease(table) }
        CGPDFOperatorTableSetCallback(table, "q") { _, info in
            let me = ImageScanner.from(info)
            me.stack.append(me.ctm)
        }
        CGPDFOperatorTableSetCallback(table, "Q") { _, info in
            let me = ImageScanner.from(info)
            me.ctm = me.stack.popLast() ?? .identity
        }
        CGPDFOperatorTableSetCallback(table, "cm") { scanner, info in
            var v = [CGPDFReal](repeating: 0, count: 6)
            for k in (0..<6).reversed() {
                guard CGPDFScannerPopNumber(scanner, &v[k]) else { return }
            }
            let me = ImageScanner.from(info)
            me.ctm = CGAffineTransform(a: v[0], b: v[1], c: v[2], d: v[3], tx: v[4], ty: v[5]).concatenating(me.ctm)
        }
        CGPDFOperatorTableSetCallback(table, "Do") { scanner, info in
            var name: UnsafePointer<CChar>?
            guard CGPDFScannerPopName(scanner, &name), let name else { return }
            ImageScanner.from(info).draw(name)
        }
        let content = CGPDFContentStreamCreateWithPage(page)
        defer { CGPDFContentStreamRelease(content) }
        let scanner = CGPDFScannerCreate(content, table, Unmanaged.passUnretained(self).toOpaque())
        defer { CGPDFScannerRelease(scanner) }
        CGPDFScannerScan(scanner)
        return found
    }

    private func draw(_ name: UnsafePointer<CChar>) {
        guard let xObjects else { return }
        var stream: CGPDFStreamRef?
        var subtype: UnsafePointer<CChar>?
        guard CGPDFDictionaryGetStream(xObjects, name, &stream), let stream,
              let dict = CGPDFStreamGetDictionary(stream),
              CGPDFDictionaryGetName(dict, "Subtype", &subtype), let subtype,
              String(cString: subtype) == "Image" else { return }
        // Images are drawn into the unit square, so the transform gives their placement.
        let rect = CGRect(x: 0, y: 0, width: 1, height: 1).applying(ctm)
        guard rect.width >= 24, rect.height >= 24, let jpeg = Self.jpegData(stream, dict) else { return }
        found.append(.init(x: Double(rect.minX - box.minX), y: Double(box.maxY - rect.maxY),
                           w: Double(rect.width), h: Double(rect.height),
                           data: jpeg.base64EncodedString(), mime: "image/jpeg"))
    }

    private static func jpegData(_ stream: CGPDFStreamRef, _ dict: CGPDFDictionaryRef) -> Data? {
        var format = CGPDFDataFormat.raw
        guard let cfData = CGPDFStreamCopyData(stream, &format) else { return nil }
        let data = cfData as Data
        if format == .jpegEncoded || format == .JPEG2000 {
            return UIImage(data: data).flatMap(flattened)
        }
        var width: CGPDFInteger = 0, height: CGPDFInteger = 0, bits: CGPDFInteger = 0
        guard CGPDFDictionaryGetInteger(dict, "Width", &width),
              CGPDFDictionaryGetInteger(dict, "Height", &height),
              CGPDFDictionaryGetInteger(dict, "BitsPerComponent", &bits), bits == 8 else { return nil }
        let components = componentCount(dict)
        guard components == 1 || components == 3, data.count >= width * height * components,
              let provider = CGDataProvider(data: data as CFData),
              let image = CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 8 * components,
                                  bytesPerRow: width * components,
                                  space: components == 3 ? CGColorSpaceCreateDeviceRGB() : CGColorSpaceCreateDeviceGray(),
                                  bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                                  provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent)
        else { return nil }
        return flattened(UIImage(cgImage: image))
    }

    private static func componentCount(_ dict: CGPDFDictionaryRef) -> Int {
        var name: UnsafePointer<CChar>?
        if CGPDFDictionaryGetName(dict, "ColorSpace", &name), let name {
            switch String(cString: name) {
            case "DeviceRGB": return 3
            case "DeviceGray": return 1
            default: return 0
            }
        }
        var array: CGPDFArrayRef?
        var first: UnsafePointer<CChar>?
        var icc: CGPDFStreamRef?
        var n: CGPDFInteger = 0
        if CGPDFDictionaryGetArray(dict, "ColorSpace", &array), let array,
           CGPDFArrayGetName(array, 0, &first), let first, String(cString: first) == "ICCBased",
           CGPDFArrayGetStream(array, 1, &icc), let icc,
           let iccDict = CGPDFStreamGetDictionary(icc),
           CGPDFDictionaryGetInteger(iccDict, "N", &n) {
            return n
        }
        return 0
    }

    /// JPEG on a white background, at most 2000 px on the long side.
    private static func flattened(_ image: UIImage) -> Data? {
        let scale = min(1, 2000 / max(image.size.width, image.size.height, 1))
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            image.draw(in: CGRect(origin: .zero, size: size))
        }.jpegData(compressionQuality: 0.88)
    }
}
