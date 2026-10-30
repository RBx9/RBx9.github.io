import SwiftUI

@main
struct RBx9PDFApp: App {
    var body: some Scene {
        WindowGroup {
            HomeView()
        }
    }
}

struct HomeView: View {
    private let columns = [GridItem(.adaptive(minimum: 155), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Label("Everything runs on your iPhone. Files are never uploaded.", systemImage: "lock.shield")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(Tool.allCases) { tool in
                            NavigationLink(value: tool) { ToolTile(tool: tool) }
                                .buttonStyle(.plain)
                        }
                    }
                }
                .padding()
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("RBx9 PDF")
            .navigationDestination(for: Tool.self) { ToolView(tool: $0) }
        }
    }
}

struct ToolTile: View {
    let tool: Tool

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Image(systemName: tool.symbol)
                .font(.title2)
                .foregroundStyle(.white)
                .frame(width: 44, height: 44)
                .background(tool.color.gradient, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            Text(tool.title)
                .font(.headline)
                .foregroundStyle(.primary)
            Text(tool.subtitle)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .padding(14)
        .background(Color(.secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}
