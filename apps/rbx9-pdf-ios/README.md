# RBx9 PDF for iOS

A native SwiftUI PDF toolkit for iPhone and iPad (iOS 16+). Every tool runs on the device with PDFKit, Core Graphics and Vision, so files are never uploaded.

**Tools:** Merge · Split · Organize pages · Remove pages · Extract pages · Rotate · Compress · Scan to PDF · Images to PDF · PDF to images · Page numbers · Watermark · Protect (password) · Unlock · PDF to text (with OCR for scans)

A web version with the same core tools lives in [`/pdf`](../../pdf) and is published at https://rbx9.github.io/pdf/.

## Build

GitHub Actions builds it on every push ([workflow](../../.github/workflows/build-rbx9-pdf.yml)). Download the unsigned `RBx9PDF.ipa` from the run's artifacts and sign it with Feather, ESign or your own certificate.

To publish a release that appears in the RBx9 IPA source:

```sh
git tag rbx9-pdf-v1.0.0 && git push origin rbx9-pdf-v1.0.0
```

Or open **Actions → Build RBx9 PDF (iOS) → Run workflow** and enter the release tag. Bump `MARKETING_VERSION` in `project.yml` for each new version.

Build locally on a Mac:

```sh
brew install xcodegen
cd apps/rbx9-pdf-ios && xcodegen generate && open RBx9PDF.xcodeproj
```

## Layout

| File | Purpose |
| --- | --- |
| `project.yml` | XcodeGen project spec (bundle ID `com.rbx9.pdf`) |
| `Sources/Tool.swift` | Tool list, icons and options |
| `Sources/PDFEngine.swift` | All PDF processing and `ToolRunner` |
| `Sources/WebCompressor.swift` | Runs the web app's [`pdf/compress.js`](../../pdf/compress.js) in a hidden WKWebView to optimize the images inside PDFs |
| `Sources/ToolView.swift` | Shared tool screen, file import, results, document scanner |
| `Sources/RBx9PDFApp.swift` | App entry and home grid |
