import PDFKit
import UIKit
import Vision

struct InputFile: Identifiable {
    let id = UUID()
    let name: String
    let data: Data

    var baseName: String { (name as NSString).deletingPathExtension }
}

struct OutputFile: Identifiable {
    let id = UUID()
    let url: URL
    var note: String?

    var name: String { url.lastPathComponent }
    var size: Int { (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0 }
}

enum PDFToolError: LocalizedError {
    case unreadable(String)
    case locked(String)
    case message(String)

    var errorDescription: String? {
        switch self {
        case .unreadable(let name): return "\(name) could not be opened as a PDF."
        case .locked(let name): return "\(name) is password-protected. Unlock it first."
        case .message(let text): return text
        }
    }
}

func formatSize(_ bytes: Int) -> String {
    ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
}

/// All PDF work happens here, synchronously, on whatever thread calls it.
/// Nothing leaves the device.
enum PDFEngine {

    // MARK: Loading

    static func document(_ file: InputFile) throws -> PDFDocument {
        guard let doc = PDFDocument(data: file.data) else { throw PDFToolError.unreadable(file.name) }
        if doc.isLocked { throw PDFToolError.locked(file.name) }
        return doc
    }

    static func cgDocument(_ file: InputFile, password: String = "") throws -> CGPDFDocument {
        guard let provider = CGDataProvider(data: file.data as CFData), let doc = CGPDFDocument(provider) else {
            throw PDFToolError.unreadable(file.name)
        }
        if doc.isEncrypted && !doc.isUnlocked && !doc.unlockWithPassword(password) {
            throw password.isEmpty ? PDFToolError.locked(file.name) : PDFToolError.message("That password is incorrect.")
        }
        if doc.numberOfPages == 0 { throw PDFToolError.unreadable(file.name) }
        return doc
    }

    /// "1-3, 5, 8-" -> [[0,1,2],[4],[7...]] (zero-based, one array per range).
    static func parseRanges(_ text: String, pageCount: Int) throws -> [[Int]] {
        var groups: [[Int]] = []
        for raw in text.split(separator: ",") {
            let part = raw.trimmingCharacters(in: .whitespaces)
            if part.isEmpty { continue }
            let pieces = part.split(separator: "-", omittingEmptySubsequences: false).map { $0.trimmingCharacters(in: .whitespaces) }
            guard pieces.count <= 2 else { throw PDFToolError.message("“\(part)” is not a valid page range.") }
            let start = pieces[0].isEmpty ? 1 : Int(pieces[0])
            let end = pieces.count == 1 ? start : (pieces[1].isEmpty ? pageCount : Int(pieces[1]))
            guard let s = start, let e = end, !(pieces.count == 2 && pieces[0].isEmpty && pieces[1].isEmpty) else {
                throw PDFToolError.message("“\(part)” is not a valid page range.")
            }
            guard s >= 1, e <= pageCount, s <= e else {
                throw PDFToolError.message("Range “\(part)” is outside 1–\(pageCount).")
            }
            groups.append(Array((s - 1)...(e - 1)))
        }
        if groups.isEmpty { throw PDFToolError.message("Enter at least one page or range.") }
        return groups
    }

    // MARK: Page assembly (vector, lossless)

    /// Builds a new document from (page index, extra rotation) pairs.
    static func assemble(_ doc: PDFDocument, pages: [(Int, Int)]) -> PDFDocument {
        let out = PDFDocument()
        for (index, rotation) in pages {
            guard let page = doc.page(at: index)?.copy() as? PDFPage else { continue }
            page.rotation = (page.rotation + rotation) % 360
            out.insert(page, at: out.pageCount)
        }
        return out
    }

    static func merge(_ files: [InputFile]) throws -> PDFDocument {
        let out = PDFDocument()
        for file in files {
            let doc = try document(file)
            for i in 0..<doc.pageCount {
                if let page = doc.page(at: i)?.copy() as? PDFPage { out.insert(page, at: out.pageCount) }
            }
        }
        return out
    }

    // MARK: Rendering

    /// Page size as it appears on screen, i.e. after its /Rotate is applied.
    static func visibleSize(_ page: CGPDFPage) -> CGSize {
        let box = page.getBoxRect(.cropBox)
        return page.rotationAngle % 180 == 0 ? box.size : CGSize(width: box.height, height: box.width)
    }

    /// Draws `page` filling `rect` in a top-left-origin (UIKit) context.
    static func draw(_ page: CGPDFPage, in rect: CGRect, context cg: CGContext) {
        cg.saveGState()
        cg.translateBy(x: rect.minX, y: rect.maxY)
        cg.scaleBy(x: rect.width / visibleSize(page).width, y: -rect.height / visibleSize(page).height)
        cg.concatenate(page.getDrawingTransform(.cropBox, rect: CGRect(origin: .zero, size: visibleSize(page)), rotate: 0, preserveAspectRatio: true))
        cg.drawPDFPage(page)
        cg.restoreGState()
    }

    static func image(of page: CGPDFPage, scale: CGFloat) -> UIImage {
        let size = visibleSize(page)
        let target = CGSize(width: (size.width * scale).rounded(), height: (size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        return UIGraphicsImageRenderer(size: target, format: format).image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(origin: .zero, size: target))
            draw(page, in: CGRect(origin: .zero, size: target), context: ctx.cgContext)
        }
    }

    /// Re-draws every page into a new PDF (keeping vector content), letting
    /// `overlay` paint on top in UIKit coordinates.
    static func redraw(_ doc: CGPDFDocument, overlay: ((Int, CGRect, CGContext) -> Void)? = nil) -> Data {
        UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: 612, height: 792)).pdfData { ctx in
            for n in 1...max(doc.numberOfPages, 1) {
                guard let page = doc.page(at: n) else { continue }
                let rect = CGRect(origin: .zero, size: visibleSize(page))
                ctx.beginPage(withBounds: rect, pageInfo: [:])
                draw(page, in: rect, context: ctx.cgContext)
                overlay?(n - 1, rect, ctx.cgContext)
            }
        }
    }

    // MARK: Tools

    static func compress(_ file: InputFile, level: CompressionLevel, progress: (String) -> Void) throws -> (Data, String) {
        let doc = try document(file)
        var best = doc.dataRepresentation() ?? file.data
        if let raster = level.raster {
            let cg = try cgDocument(file)
            let data = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: 612, height: 792)).pdfData { ctx in
                for n in 1...cg.numberOfPages {
                    progress("Compressing page \(n) of \(cg.numberOfPages)…")
                    autoreleasepool {
                        guard let page = cg.page(at: n) else { return }
                        let rect = CGRect(origin: .zero, size: visibleSize(page))
                        ctx.beginPage(withBounds: rect, pageInfo: [:])
                        // Drawing a JPEG-backed image lets Core Graphics embed the JPEG bytes as-is.
                        if let jpeg = image(of: page, scale: raster.scale).jpegData(compressionQuality: raster.quality),
                           let img = UIImage(data: jpeg) {
                            img.draw(in: rect)
                        }
                    }
                }
            }
            if data.count < best.count { best = data }
        }
        let before = file.data.count
        guard best.count < before else { return (file.data, "Already well compressed") }
        let percent = Int((Double(before - best.count) / Double(before) * 100).rounded())
        return (best, "\(formatSize(before)) → \(formatSize(best.count)) (−\(percent)%)")
    }

    static func imagesToPDF(_ images: [UIImage], size option: PageSizeOption, margin: CGFloat) -> Data {
        UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: 612, height: 792)).pdfData { ctx in
            for original in images {
                autoreleasepool {
                    // Re-encode as JPEG so the PDF stores compressed images, not raw bitmaps.
                    let image = original.jpegData(compressionQuality: 0.85).flatMap(UIImage.init(data:)) ?? original
                    var page: CGSize
                    switch option {
                    case .fit: page = CGSize(width: image.size.width + margin * 2, height: image.size.height + margin * 2)
                    case .a4: page = CGSize(width: 595.28, height: 841.89)
                    case .letter: page = CGSize(width: 612, height: 792)
                    }
                    if option != .fit && image.size.width > image.size.height { page = CGSize(width: page.height, height: page.width) }
                    let scale = min((page.width - margin * 2) / image.size.width, (page.height - margin * 2) / image.size.height)
                    let w = image.size.width * scale, h = image.size.height * scale
                    ctx.beginPage(withBounds: CGRect(origin: .zero, size: page), pageInfo: [:])
                    image.draw(in: CGRect(x: (page.width - w) / 2, y: (page.height - h) / 2, width: w, height: h))
                }
            }
        }
    }

    static func addPageNumbers(_ file: InputFile, options o: ToolOptions) throws -> Data {
        let doc = try cgDocument(file)
        let total = doc.numberOfPages + o.firstNumber - 1
        let attrs: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: o.numberFontSize),
            .foregroundColor: UIColor.darkGray,
        ]
        return redraw(doc) { i, rect, _ in
            let text = o.numberFormat.text(i + o.firstNumber, of: total) as NSString
            let size = text.size(withAttributes: attrs)
            let pad: CGFloat = 28
            let x: CGFloat
            switch o.numberPosition {
            case .bottomLeft, .topLeft: x = pad
            case .bottomRight, .topRight: x = rect.width - pad - size.width
            case .bottomCenter, .topCenter: x = (rect.width - size.width) / 2
            }
            let top = [NumberPosition.topLeft, .topCenter, .topRight].contains(o.numberPosition)
            let y = top ? pad - size.height / 2 : rect.height - pad - size.height / 2
            text.draw(at: CGPoint(x: x, y: y), withAttributes: attrs)
        }
    }

    static func watermark(_ file: InputFile, options o: ToolOptions) throws -> Data {
        guard !o.watermarkText.trimmingCharacters(in: .whitespaces).isEmpty else {
            throw PDFToolError.message("Enter watermark text.")
        }
        let doc = try cgDocument(file)
        let attrs: [NSAttributedString.Key: Any] = [
            .font: UIFont.boldSystemFont(ofSize: o.watermarkSize),
            .foregroundColor: UIColor.systemRed.withAlphaComponent(o.watermarkOpacity),
        ]
        let text = o.watermarkText as NSString
        let size = text.size(withAttributes: attrs)
        return redraw(doc) { _, rect, cg in
            cg.saveGState()
            cg.translateBy(x: rect.midX, y: rect.midY)
            if o.watermarkDiagonal { cg.rotate(by: -.pi / 4) }
            text.draw(at: CGPoint(x: -size.width / 2, y: -size.height / 2), withAttributes: attrs)
            cg.restoreGState()
        }
    }

    static func protect(_ file: InputFile, password: String, to url: URL) throws {
        guard !password.isEmpty else { throw PDFToolError.message("Enter a password.") }
        let doc = try document(file)
        let ok = doc.write(to: url, withOptions: [.userPasswordOption: password, .ownerPasswordOption: password])
        if !ok { throw PDFToolError.message("The protected PDF could not be written.") }
    }

    static func unlock(_ file: InputFile, password: String) throws -> Data {
        redraw(try cgDocument(file, password: password))
    }

    static func extractText(_ file: InputFile, progress: (String) -> Void) throws -> String {
        let pdf = try document(file)
        let cg = try cgDocument(file)
        var pages: [String] = []
        for i in 0..<pdf.pageCount {
            var text = pdf.page(at: i)?.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            // No text layer usually means a scan, so fall back to on-device OCR.
            if text.isEmpty, let page = cg.page(at: i + 1), let cgImage = image(of: page, scale: 2).cgImage {
                progress("Reading page \(i + 1) of \(pdf.pageCount)…")
                let request = VNRecognizeTextRequest()
                request.recognitionLevel = .accurate
                request.usesLanguageCorrection = true
                try VNImageRequestHandler(cgImage: cgImage).perform([request])
                text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
            }
            pages.append("— Page \(i + 1) —\n\(text)")
        }
        return pages.joined(separator: "\n\n")
    }
}

// MARK: - Running a tool

enum ToolRunner {

    static func run(_ tool: Tool, files: [InputFile], options o: ToolOptions, pages: [PageItem],
                    progress: @escaping (String) -> Void) throws -> [OutputFile] {
        let folder = FileManager.default.temporaryDirectory
            .appendingPathComponent("Output", isDirectory: true)
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

        func save(_ data: Data, _ name: String, note: String? = nil) throws -> OutputFile {
            let url = folder.appendingPathComponent(name)
            try data.write(to: url)
            return OutputFile(url: url, note: note)
        }
        func savePDF(_ doc: PDFDocument, _ name: String) throws -> OutputFile {
            guard let data = doc.dataRepresentation() else { throw PDFToolError.message("The PDF could not be saved.") }
            return try save(data, name)
        }

        guard let first = files.first else { throw PDFToolError.message("Choose a file first.") }

        switch tool {
        case .merge:
            return [try savePDF(try PDFEngine.merge(files), "Merged.pdf")]

        case .split:
            let doc = try PDFEngine.document(first)
            let all = Array(0..<doc.pageCount)
            let groups: [[Int]]
            switch o.splitMode {
            case .ranges: groups = try PDFEngine.parseRanges(o.splitRanges, pageCount: doc.pageCount)
            case .every: groups = all.map { [$0] }
            case .chunks:
                let n = max(1, o.chunkSize)
                groups = stride(from: 0, to: all.count, by: n).map { Array(all[$0..<min($0 + n, all.count)]) }
            }
            return try groups.map { g -> OutputFile in
                let label = g.count == 1 ? "\(g[0] + 1)" : "\(g[0] + 1)-\(g[g.count - 1] + 1)"
                return try savePDF(PDFEngine.assemble(doc, pages: g.map { ($0, 0) }), "\(first.baseName)_pages_\(label).pdf")
            }

        case .organize:
            guard !pages.isEmpty else { throw PDFToolError.message("Every page has been deleted.") }
            let doc = try PDFEngine.document(first)
            return [try savePDF(PDFEngine.assemble(doc, pages: pages.map { ($0.index, $0.rotation) }), "\(first.baseName)_organized.pdf")]

        case .remove:
            let doc = try PDFEngine.document(first)
            let drop = Set(try PDFEngine.parseRanges(o.removeRanges, pageCount: doc.pageCount).joined())
            let keep = (0..<doc.pageCount).filter { !drop.contains($0) }
            if keep.isEmpty { throw PDFToolError.message("That would remove every page.") }
            return [try savePDF(PDFEngine.assemble(doc, pages: keep.map { ($0, 0) }), "\(first.baseName)_edited.pdf")]

        case .extract:
            let doc = try PDFEngine.document(first)
            let pick = try PDFEngine.parseRanges(o.extractRanges, pageCount: doc.pageCount).joined()
            return [try savePDF(PDFEngine.assemble(doc, pages: pick.map { ($0, 0) }), "\(first.baseName)_extracted.pdf")]

        case .rotate:
            let doc = try PDFEngine.document(first)
            let targets = o.rotateRanges.trimmingCharacters(in: .whitespaces).isEmpty
                ? Set(0..<doc.pageCount)
                : Set(try PDFEngine.parseRanges(o.rotateRanges, pageCount: doc.pageCount).joined())
            let plan = (0..<doc.pageCount).map { ($0, targets.contains($0) ? o.rotateAngle : 0) }
            return [try savePDF(PDFEngine.assemble(doc, pages: plan), "\(first.baseName)_rotated.pdf")]

        case .compress:
            let (data, note) = try PDFEngine.compress(first, level: o.compression, progress: progress)
            return [try save(data, "\(first.baseName)_compressed.pdf", note: note)]

        case .scan, .imagesToPDF:
            let images = files.compactMap { UIImage(data: $0.data) }
            if images.isEmpty { throw PDFToolError.message("None of the images could be read.") }
            let name = tool == .scan ? "Scan.pdf" : (files.count == 1 ? "\(first.baseName).pdf" : "Images.pdf")
            return [try save(PDFEngine.imagesToPDF(images, size: o.pageSize, margin: o.margin.points), name)]

        case .pdfToImages:
            let doc = try PDFEngine.cgDocument(first)
            return try (1...doc.numberOfPages).compactMap { n -> OutputFile? in
                try autoreleasepool { () throws -> OutputFile? in
                    progress("Rendering page \(n) of \(doc.numberOfPages)…")
                    guard let page = doc.page(at: n) else { return nil }
                    let image = PDFEngine.image(of: page, scale: CGFloat(o.dpi) / 72)
                    let data = o.imageFormat == .png ? image.pngData() : image.jpegData(compressionQuality: 0.9)
                    guard let data else { return nil }
                    return try save(data, "\(first.baseName)_page_\(n).\(o.imageFormat == .png ? "png" : "jpg")")
                }
            }

        case .pageNumbers:
            return [try save(PDFEngine.addPageNumbers(first, options: o), "\(first.baseName)_numbered.pdf")]

        case .watermark:
            return [try save(PDFEngine.watermark(first, options: o), "\(first.baseName)_watermarked.pdf")]

        case .protect:
            guard o.password == o.confirmPassword else { throw PDFToolError.message("The passwords don’t match.") }
            let url = folder.appendingPathComponent("\(first.baseName)_protected.pdf")
            try PDFEngine.protect(first, password: o.password, to: url)
            return [OutputFile(url: url)]

        case .unlock:
            return [try save(PDFEngine.unlock(first, password: o.password), "\(first.baseName)_unlocked.pdf")]

        case .extractText:
            let text = try PDFEngine.extractText(first, progress: progress)
            return [try save(Data(text.utf8), "\(first.baseName).txt")]
        }
    }
}
