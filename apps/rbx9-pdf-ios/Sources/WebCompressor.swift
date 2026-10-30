import WebKit

/// Runs the web app's compress.js (shared with rbx9.github.io/pdf) in a hidden
/// WKWebView. It rewrites the images inside a PDF, which PDFKit can't do.
/// Everything stays on the device; the page only loads bundled files.
@MainActor
final class WebCompressor: NSObject, WKNavigationDelegate {
    static let shared = WebCompressor()

    private var webView: WKWebView?
    private var loading: CheckedContinuation<Void, Error>?

    /// Returns the optimized PDF and how many large images were found.
    func shrinkImages(in pdf: Data, level: String) async throws -> (Data, Int) {
        let webView = try await loadedWebView()
        let result = try await webView.callAsyncJavaScript(
            "return await compressPDF(data, level)",
            arguments: ["data": pdf.base64EncodedString(), "level": level],
            contentWorld: .page)
        guard let dict = result as? [String: Any],
              let b64 = dict["data"] as? String,
              let data = Data(base64Encoded: b64) else {
            throw PDFToolError.message("Compression failed.")
        }
        return (data, (dict["found"] as? NSNumber)?.intValue ?? 0)
    }

    private func loadedWebView() async throws -> WKWebView {
        if let webView { return webView }
        guard let url = Bundle.main.url(forResource: "compressor", withExtension: "html") else {
            throw PDFToolError.message("The compressor is missing from the app.")
        }
        let view = WKWebView(frame: CGRect(x: 0, y: 0, width: 1, height: 1))
        view.navigationDelegate = self
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            loading = continuation
            view.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        }
        webView = view
        return view
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loading?.resume()
        loading = nil
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        loading?.resume(throwing: error)
        loading = nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        loading?.resume(throwing: error)
        loading = nil
    }
}
