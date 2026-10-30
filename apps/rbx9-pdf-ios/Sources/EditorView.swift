import SwiftUI
import UniformTypeIdentifiers
import WebKit

/// Edit PDF: runs the web app's editor (pdf/edit.html, bundled with the app so
/// it works offline) in a WKWebView. The app hands it the PDF, and Save opens
/// the share sheet to save the edited file to Files or send it. Apple Pencil
/// works through the editor's pointer events (pressure, Pencil-only drawing).

struct EditorScreen: View {
    @EnvironmentObject private var inbox: Inbox
    @Environment(\.dismiss) private var dismiss
    @State private var file: InputFile?
    @State private var showPicker = false
    @State private var errorText: String?

    var body: some View {
        Group {
            if let file {
                EditorWebView(file: file, onClose: { dismiss() })
                    .ignoresSafeArea(edges: .bottom)
                    .toolbar(.hidden, for: .navigationBar)
            } else {
                chooser
            }
        }
        .sheet(isPresented: $showPicker) {
            DocumentPicker(types: [.pdf], allowsMultiple: false) { urls in
                showPicker = false
                open(urls.first)
            } onCancel: {
                showPicker = false
            }
            .ignoresSafeArea()
        }
        .onAppear {
            if file == nil, let handed = inbox.take(for: .editPDF) { file = handed }
        }
    }

    private var chooser: some View {
        VStack(spacing: 18) {
            Spacer()
            ToolIcon(tool: .editPDF, size: 76)
            Text("Edit PDF").font(.system(.largeTitle, design: .rounded).weight(.bold))
            Text("Change existing text, add text, images, signatures, drawings, highlights and shapes.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)
            Button { showPicker = true } label: { Text("Choose PDF") }
                .buttonStyle(GradientButtonStyle(tool: .editPDF))
                .padding(.top, 6)
            if let errorText {
                Label(errorText, systemImage: "exclamationmark.triangle.fill").foregroundStyle(.red).font(.subheadline)
            }
            Spacer()
            Spacer()
        }
        .frame(maxWidth: .infinity)
        .background(BrandBackground())
        .navigationTitle("Edit PDF")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func open(_ url: URL?) {
        guard let url else { return }
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else {
            errorText = "That file could not be read."
            return
        }
        errorText = nil
        file = InputFile(name: url.lastPathComponent, data: data)
    }
}

struct EditorWebView: UIViewRepresentable {
    let file: InputFile
    let onClose: () -> Void

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(BundleSchemeHandler(), forURLScheme: BundleSchemeHandler.scheme)
        // A weak proxy, so the content controller doesn't keep the coordinator alive.
        config.userContentController.add(WeakMessageHandler(context.coordinator), name: "rbx9")
        let view = WKWebView(frame: .zero, configuration: config)
        view.uiDelegate = context.coordinator
        view.isOpaque = false
        view.backgroundColor = .systemBackground
        view.scrollView.contentInsetAdjustmentBehavior = .never
        view.load(URLRequest(url: URL(string: "\(BundleSchemeHandler.scheme)://app/edit.html")!))
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {}

    static func dismantleUIView(_ view: WKWebView, coordinator: Coordinator) {
        view.configuration.userContentController.removeScriptMessageHandler(forName: "rbx9")
    }

    final class Coordinator: NSObject, WKScriptMessageHandler, WKUIDelegate {
        let parent: EditorWebView

        init(_ parent: EditorWebView) { self.parent = parent }

        func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
            guard let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
            switch action {
            case "ready":
                guard let webView = message.webView else { return }
                let file = parent.file
                Task { @MainActor in
                    _ = try? await webView.callAsyncJavaScript(
                        "await RBx9Editor.open(data, name)",
                        arguments: ["data": file.data.base64EncodedString(), "name": file.name],
                        contentWorld: .page)
                }
            case "save":
                guard let name = body["name"] as? String, let b64 = body["data"] as? String,
                      let data = Data(base64Encoded: b64) else { return }
                let folder = FileManager.default.temporaryDirectory.appendingPathComponent("Edited", isDirectory: true)
                try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
                let url = folder.appendingPathComponent(name)
                do {
                    try data.write(to: url, options: .atomic)
                    share(url, from: message.webView)
                } catch {
                    present(UIAlertController(title: "Saving failed", message: error.localizedDescription, preferredStyle: .alert), from: message.webView)
                }
            case "close":
                parent.onClose()
            default:
                break
            }
        }

        // The editor uses alert() and confirm(), which WKWebView only shows through its UI delegate.
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default) { _ in completionHandler() })
            present(alert, from: webView, fallback: completionHandler)
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let alert = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Cancel", style: .cancel) { _ in completionHandler(false) })
            alert.addAction(UIAlertAction(title: "OK", style: .destructive) { _ in completionHandler(true) })
            present(alert, from: webView) { completionHandler(false) }
        }

        /// On iPad the share sheet must be a popover; it points at the Save button (top right).
        private func share(_ url: URL, from view: WKWebView?) {
            let sheet = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            if let popover = sheet.popoverPresentationController, let view {
                popover.sourceView = view
                popover.sourceRect = CGRect(x: view.bounds.maxX - 70, y: 12, width: 50, height: 40)
                popover.permittedArrowDirections = [.up]
            }
            present(sheet, from: view)
        }

        private func present(_ controller: UIViewController, from view: UIView?, fallback: (() -> Void)? = nil) {
            if let alert = controller as? UIAlertController, alert.actions.isEmpty {
                alert.addAction(UIAlertAction(title: "OK", style: .default))
            }
            var top = view?.window?.rootViewController
            while let next = top?.presentedViewController { top = next }
            guard let top else { fallback?(); return }
            top.present(controller, animated: true)
        }
    }
}

private final class WeakMessageHandler: NSObject, WKScriptMessageHandler {
    weak var target: WKScriptMessageHandler?

    init(_ target: WKScriptMessageHandler) { self.target = target }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        target?.userContentController(controller, didReceive: message)
    }
}

/// Serves the bundled web app (the "pdf" folder) at rbx9://app/…, so the
/// editor's JavaScript modules load as they do on the website.
final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    static let scheme = "rbx9"

    private let root = Bundle.main.resourceURL!.appendingPathComponent("pdf", isDirectory: true).standardizedFileURL

    private static let types = [
        "html": "text/html", "js": "text/javascript", "mjs": "text/javascript", "css": "text/css",
        "svg": "image/svg+xml", "png": "image/png", "json": "application/json", "webmanifest": "application/manifest+json",
    ]

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return }
        let path = url.path.isEmpty || url.path == "/" ? "edit.html" : String(url.path.dropFirst())
        let file = root.appendingPathComponent(path).standardizedFileURL
        guard file.path.hasPrefix(root.path), let data = try? Data(contentsOf: file) else {
            task.didFailWithError(URLError(.fileDoesNotExist))
            return
        }
        let type = Self.types[file.pathExtension.lowercased()] ?? "application/octet-stream"
        let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                       headerFields: ["Content-Type": type, "Content-Length": "\(data.count)"])!
        task.didReceive(response)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}
}
