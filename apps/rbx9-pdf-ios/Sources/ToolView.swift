import PhotosUI
import QuickLook
import SwiftUI
import UniformTypeIdentifiers
import VisionKit

struct ToolView: View {
    let tool: Tool

    @State private var files: [InputFile] = []
    @State private var options = ToolOptions()
    @State private var pages: [PageItem] = []
    @State private var outputs: [OutputFile] = []
    @State private var showImporter = false
    @State private var showScanner = false
    @State private var photoItems: [PhotosPickerItem] = []
    @State private var working = false
    @State private var status: String?
    @State private var errorText: String?
    @State private var preview: URL?

    var body: some View {
        Form {
            Section {
                inputButtons
            } footer: {
                Text(tool.subtitle)
            }

            if !files.isEmpty {
                Section(tool.allowsMultiple ? "Files (drag to reorder)" : "File") {
                    ForEach(files) { file in
                        HStack {
                            Image(systemName: tool.input == .pdf ? "doc.richtext" : "photo")
                                .foregroundStyle(tool.color)
                            Text(file.name).lineLimit(1)
                            Spacer()
                            Text(formatSize(file.data.count)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    .onMove { files.move(fromOffsets: $0, toOffset: $1) }
                    .onDelete { files.remove(atOffsets: $0); pages = []; outputs = [] }
                }
            }

            if tool == .organize && !pages.isEmpty {
                organizeSection
            }

            optionsSection

            Section {
                Button(action: run) {
                    HStack {
                        Spacer()
                        if working { ProgressView().padding(.trailing, 6) }
                        Text(working ? (status ?? "Working…") : tool.title).bold()
                        Spacer()
                    }
                }
                .disabled(working || files.count < tool.minimumFiles)
            } footer: {
                if let errorText {
                    Text(errorText).foregroundStyle(.red)
                }
            }

            if !outputs.isEmpty {
                resultsSection
            }
        }
        .navigationTitle(tool.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if tool.allowsMultiple || tool == .organize { EditButton() }
        }
        .fileImporter(isPresented: $showImporter,
                      allowedContentTypes: tool.input == .pdf ? [.pdf] : [.image],
                      allowsMultipleSelection: tool.allowsMultiple,
                      onCompletion: importFiles)
        .onChange(of: photoItems) { items in loadPhotos(items) }
        .sheet(isPresented: $showScanner) {
            ScannerView { images in
                let added = images.enumerated().compactMap { i, image in
                    image.jpegData(compressionQuality: 0.85).map {
                        InputFile(name: "Scan page \(files.count + i + 1).jpg", data: $0)
                    }
                }
                files.append(contentsOf: added)
            }
            .ignoresSafeArea()
        }
        .quickLookPreview($preview)
    }

    // MARK: Sections

    @ViewBuilder private var inputButtons: some View {
        switch tool.input {
        case .pdf:
            Button { showImporter = true } label: {
                Label(tool.allowsMultiple ? "Add PDFs" : (files.isEmpty ? "Choose PDF" : "Choose a different PDF"), systemImage: "folder")
            }
        case .images:
            PhotosPicker(selection: $photoItems, matching: .images) {
                Label("Add from Photos", systemImage: "photo.on.rectangle")
            }
            Button { showImporter = true } label: { Label("Add from Files", systemImage: "folder") }
        case .scan:
            Button { showScanner = true } label: { Label(files.isEmpty ? "Scan document" : "Scan more pages", systemImage: "doc.viewfinder") }
                .disabled(!VNDocumentCameraViewController.isSupported)
            if !VNDocumentCameraViewController.isSupported {
                Text("This device can’t scan documents.").foregroundStyle(.secondary)
            }
        }
    }

    private var organizeSection: some View {
        Section("Pages (tap Edit to reorder)") {
            ForEach($pages) { $page in
                HStack(spacing: 14) {
                    Image(uiImage: page.thumbnail)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 54, height: 70)
                        .rotationEffect(.degrees(Double(page.rotation)))
                        .shadow(radius: 1)
                    Text("Page \(page.index + 1)")
                    Spacer()
                    Button { page.rotation = (page.rotation + 90) % 360 } label: {
                        Image(systemName: "rotate.right")
                    }
                    .buttonStyle(.borderless)
                }
            }
            .onMove { pages.move(fromOffsets: $0, toOffset: $1) }
            .onDelete { pages.remove(atOffsets: $0) }
        }
    }

    @ViewBuilder private var optionsSection: some View {
        switch tool {
        case .split:
            Section("Options") {
                Picker("Split by", selection: $options.splitMode) {
                    ForEach(SplitMode.allCases) { Text($0.rawValue).tag($0) }
                }
                if options.splitMode == .ranges {
                    rangeField("Ranges", text: $options.splitRanges, hint: "Each range becomes a file, e.g. 1-3, 4, 5-")
                } else if options.splitMode == .chunks {
                    Stepper("Pages per file: \(options.chunkSize)", value: $options.chunkSize, in: 1...500)
                }
            }
        case .remove:
            Section("Options") { rangeField("Pages to remove", text: $options.removeRanges, hint: "e.g. 2, 5-7") }
        case .extract:
            Section("Options") { rangeField("Pages to extract", text: $options.extractRanges, hint: "e.g. 1, 4-6, 9-") }
        case .rotate:
            Section("Options") {
                Picker("Rotation", selection: $options.rotateAngle) {
                    Text("90° right").tag(90)
                    Text("180°").tag(180)
                    Text("90° left").tag(270)
                }
                rangeField("Pages", text: $options.rotateRanges, hint: "Leave empty to rotate every page")
            }
        case .compress:
            Section {
                Picker("Compression", selection: $options.compression) {
                    ForEach(CompressionLevel.allCases) { Text($0.rawValue).tag($0) }
                }
            } footer: {
                Text("Less, Recommended and Extreme redraw each page as an image, so text can no longer be selected. Lossless keeps everything as-is.")
            }
        case .scan, .imagesToPDF:
            Section("Options") {
                Picker("Page size", selection: $options.pageSize) {
                    ForEach(PageSizeOption.allCases) { Text($0.rawValue).tag($0) }
                }
                Picker("Margin", selection: $options.margin) {
                    ForEach(MarginOption.allCases) { Text($0.rawValue).tag($0) }
                }
            }
        case .pdfToImages:
            Section("Options") {
                Picker("Format", selection: $options.imageFormat) {
                    ForEach(ImageFormat.allCases) { Text($0.rawValue).tag($0) }
                }
                Picker("Resolution", selection: $options.dpi) {
                    Text("Screen (72 dpi)").tag(72)
                    Text("Standard (150 dpi)").tag(150)
                    Text("Print (300 dpi)").tag(300)
                }
            }
        case .pageNumbers:
            Section("Options") {
                Picker("Position", selection: $options.numberPosition) {
                    ForEach(NumberPosition.allCases) { Text($0.rawValue).tag($0) }
                }
                Picker("Format", selection: $options.numberFormat) {
                    ForEach(NumberFormat.allCases) { Text($0.rawValue).tag($0) }
                }
                Stepper("First number: \(options.firstNumber)", value: $options.firstNumber, in: 0...9999)
                Stepper("Font size: \(Int(options.numberFontSize))", value: $options.numberFontSize, in: 6...48)
            }
        case .watermark:
            Section("Options") {
                TextField("Watermark text", text: $options.watermarkText)
                Stepper("Font size: \(Int(options.watermarkSize))", value: $options.watermarkSize, in: 8...200, step: 4)
                VStack(alignment: .leading) {
                    Text("Opacity: \(Int(options.watermarkOpacity * 100))%")
                    Slider(value: $options.watermarkOpacity, in: 0.05...1)
                }
                Toggle("Diagonal", isOn: $options.watermarkDiagonal)
            }
        case .protect:
            Section {
                SecureField("Password", text: $options.password)
                SecureField("Confirm password", text: $options.confirmPassword)
            } header: {
                Text("Password")
            } footer: {
                Text("Anyone opening the PDF will need this password. It can’t be recovered if you forget it.")
            }
        case .unlock:
            Section("Password") { SecureField("Current password", text: $options.password) }
        default:
            EmptyView()
        }
    }

    private var resultsSection: some View {
        Section {
            ForEach(outputs) { output in
                HStack {
                    Button { preview = output.url } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(output.name).lineLimit(1)
                            Text(output.note ?? formatSize(output.size)).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    ShareLink(item: output.url) { Image(systemName: "square.and.arrow.up") }
                        .buttonStyle(.borderless)
                }
            }
            if outputs.count > 1 {
                ShareLink(items: outputs.map(\.url)) { Label("Share all \(outputs.count) files", systemImage: "square.and.arrow.up.on.square") }
            }
        } header: {
            Text("Done")
        } footer: {
            Text("Tap a file to preview it, or share it to save it to Files.")
        }
    }

    private func rangeField(_ title: String, text: Binding<String>, hint: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            TextField(title, text: text)
                .keyboardType(.numbersAndPunctuation)
                .autocorrectionDisabled()
            Text(hint).font(.caption).foregroundStyle(.secondary)
        }
    }

    // MARK: Actions

    private func importFiles(_ result: Result<[URL], Error>) {
        switch result {
        case .failure(let error):
            errorText = error.localizedDescription
        case .success(let urls):
            let loaded: [InputFile] = urls.compactMap { url in
                let scoped = url.startAccessingSecurityScopedResource()
                defer { if scoped { url.stopAccessingSecurityScopedResource() } }
                guard let data = try? Data(contentsOf: url) else { return nil }
                return InputFile(name: url.lastPathComponent, data: data)
            }
            if loaded.count < urls.count { errorText = "Some files could not be read." } else { errorText = nil }
            files = tool.allowsMultiple ? files + loaded : Array(loaded.prefix(1))
            outputs = []
            if tool == .organize { loadThumbnails() }
        }
    }

    private func loadPhotos(_ items: [PhotosPickerItem]) {
        guard !items.isEmpty else { return }
        Task {
            for item in items {
                if let data = try? await item.loadTransferable(type: Data.self) {
                    files.append(InputFile(name: "Photo \(files.count + 1).jpg", data: data))
                }
            }
            photoItems = []
        }
    }

    private func loadThumbnails() {
        guard let file = files.first else { return }
        pages = []
        Task {
            do {
                let items = try await Task.detached(priority: .userInitiated) { () throws -> [PageItem] in
                    let doc = try PDFEngine.cgDocument(file)
                    return (1...doc.numberOfPages).compactMap { n -> PageItem? in
                        guard let page = doc.page(at: n) else { return nil }
                        let scale = 140 / max(PDFEngine.visibleSize(page).width, 1)
                        return PageItem(index: n - 1, thumbnail: PDFEngine.image(of: page, scale: scale))
                    }
                }.value
                pages = items
            } catch {
                errorText = error.localizedDescription
            }
        }
    }

    private func run() {
        working = true
        errorText = nil
        outputs = []
        let tool = tool, files = files, options = options, pages = pages
        Task {
            do {
                let result = try await Task.detached(priority: .userInitiated) {
                    try ToolRunner.run(tool, files: files, options: options, pages: pages) { message in
                        Task { @MainActor in status = message }
                    }
                }.value
                outputs = result
                if result.count == 1 { preview = result[0].url }
            } catch {
                errorText = error.localizedDescription
            }
            working = false
            status = nil
        }
    }
}

/// Wraps VisionKit's document camera.
struct ScannerView: UIViewControllerRepresentable {
    let onScan: ([UIImage]) -> Void
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let controller = VNDocumentCameraViewController()
        controller.delegate = context.coordinator
        return controller
    }

    func updateUIViewController(_ controller: VNDocumentCameraViewController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        let parent: ScannerView

        init(_ parent: ScannerView) { self.parent = parent }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            parent.onScan((0..<scan.pageCount).map { scan.imageOfPage(at: $0) })
            parent.dismiss()
        }

        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) {
            parent.dismiss()
        }

        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) {
            parent.dismiss()
        }
    }
}
