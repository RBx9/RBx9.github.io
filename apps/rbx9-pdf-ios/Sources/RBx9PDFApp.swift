import SwiftUI
import UniformTypeIdentifiers

@main
struct RBx9PDFApp: App {
    @StateObject private var inbox = Inbox()

    var body: some Scene {
        WindowGroup {
            HomeView()
                .environmentObject(inbox)
                .tint(Color(hex: 0x7C3AED))
                .onOpenURL { inbox.receive($0) }
        }
    }
}

/// Files shared to the app ("Open in RBx9 PDF") wait here until a tool takes them.
@MainActor
final class Inbox: ObservableObject {
    @Published var incoming: InputFile?
    private var handoff: (tool: Tool, file: InputFile)?

    func receive(_ url: URL) {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        guard let data = try? Data(contentsOf: url) else { return }
        incoming = InputFile(name: url.lastPathComponent, data: data)
    }

    func send(_ file: InputFile, to tool: Tool) {
        handoff = (tool, file)
        incoming = nil
    }

    func take(for tool: Tool) -> InputFile? {
        guard let handoff, handoff.tool == tool else { return nil }
        self.handoff = nil
        return handoff.file
    }
}

// MARK: - Home

struct HomeView: View {
    @EnvironmentObject private var inbox: Inbox
    @AppStorage("toolOrder") private var storedOrder = ""
    @State private var order: [Tool] = []
    @State private var path: [Tool] = []
    @State private var query = ""
    @State private var editing = false
    @State private var dragging: Tool?

    private let columns = [GridItem(.adaptive(minimum: 155), spacing: 14)]

    private var visibleTools: [Tool] {
        guard !query.isEmpty else { return order }
        return order.filter { "\($0.title) \($0.subtitle)".localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    if !editing && query.isEmpty { HeroCard() }
                    if editing {
                        Label("Drag tiles to rearrange them. Your order is saved.", systemImage: "hand.draw")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    LazyVGrid(columns: columns, spacing: 14) {
                        ForEach(visibleTools) { tool in
                            tile(for: tool)
                        }
                    }
                    if visibleTools.isEmpty {
                        Text("No tools match “\(query)”.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    }
                    Text("Developed by RBx9")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 8)
                }
                .padding(.horizontal)
                .padding(.bottom, 24)
                .animation(.spring(response: 0.35, dampingFraction: 0.8), value: order)
                .animation(.easeInOut(duration: 0.2), value: editing)
            }
            .background(BrandBackground())
            .navigationTitle("RBx9 PDF")
            .searchable(text: $query, prompt: "Search tools")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if editing {
                        Button("Done") { editing = false }.bold()
                    } else {
                        Menu {
                            Button { editing = true } label: { Label("Rearrange Tools", systemImage: "square.grid.3x3.square") }
                            Button(role: .destructive) { order = Tool.allCases } label: { Label("Reset Order", systemImage: "arrow.counterclockwise") }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                        }
                    }
                }
            }
            .navigationDestination(for: Tool.self) { ToolView(tool: $0) }
        }
        .onAppear(perform: loadOrder)
        .onChange(of: order) { tools in storedOrder = tools.map(\.rawValue).joined(separator: ",") }
        .sheet(item: $inbox.incoming) { file in
            OpenWithSheet(file: file) { tool in
                inbox.send(file, to: tool)
                path = [tool]
            }
            .presentationDetents([.medium, .large])
        }
    }

    @ViewBuilder private func tile(for tool: Tool) -> some View {
        let card = ToolTile(tool: tool, editing: editing)
            .opacity(dragging == tool ? 0.4 : 1)
            .contextMenu {
                Button { move(tool, to: 0) } label: { Label("Move to Top", systemImage: "arrow.up.to.line") }
                Button { move(tool, by: -1) } label: { Label("Move Earlier", systemImage: "arrow.left") }
                Button { move(tool, by: 1) } label: { Label("Move Later", systemImage: "arrow.right") }
                Button { editing = true } label: { Label("Rearrange Tools", systemImage: "square.grid.3x3.square") }
            }
        if editing {
            card
                .onDrag {
                    dragging = tool
                    return NSItemProvider(object: tool.rawValue as NSString)
                }
                .onDrop(of: [.text], delegate: TileDropDelegate(target: tool, order: $order, dragging: $dragging))
        } else {
            NavigationLink(value: tool) { card }
                .buttonStyle(PressableStyle())
        }
    }

    private func loadOrder() {
        guard order.isEmpty else { return }
        let saved = storedOrder.split(separator: ",").compactMap { Tool(rawValue: String($0)) }
        // Keep the saved order, then append any tools added in newer versions.
        order = saved + Tool.allCases.filter { !saved.contains($0) }
    }

    private func move(_ tool: Tool, to index: Int) {
        guard let from = order.firstIndex(of: tool) else { return }
        order.remove(at: from)
        order.insert(tool, at: min(max(index, 0), order.count))
    }

    private func move(_ tool: Tool, by offset: Int) {
        guard let from = order.firstIndex(of: tool) else { return }
        move(tool, to: from + offset)
    }
}

/// Live reordering while a tile is dragged over others.
struct TileDropDelegate: DropDelegate {
    let target: Tool
    @Binding var order: [Tool]
    @Binding var dragging: Tool?

    func dropEntered(info: DropInfo) {
        guard let dragging, dragging != target,
              let from = order.firstIndex(of: dragging),
              let to = order.firstIndex(of: target) else { return }
        order.move(fromOffsets: IndexSet(integer: from), toOffset: to > from ? to + 1 : to)
    }

    func dropUpdated(info: DropInfo) -> DropProposal? { DropProposal(operation: .move) }

    func performDrop(info: DropInfo) -> Bool {
        dragging = nil
        return true
    }
}

struct HeroCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "lock.shield.fill")
                Text("100% ON-DEVICE").font(.caption.weight(.bold)).kerning(1)
            }
            .foregroundStyle(.white.opacity(0.9))
            Text("Every PDF tool,\nprivate by design.")
                .font(.system(.title, design: .rounded).weight(.heavy))
                .foregroundStyle(.white)
            Text("Files are processed on your iPhone and never uploaded.")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.85))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(22)
        .background {
            ZStack {
                LinearGradient.brand
                Circle().fill(.white.opacity(0.18)).frame(width: 220).blur(radius: 40).offset(x: -120, y: -80)
                Image(systemName: "doc.richtext.fill")
                    .font(.system(size: 120))
                    .foregroundStyle(.white.opacity(0.12))
                    .rotationEffect(.degrees(-12))
                    .offset(x: 120, y: 30)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .shadow(color: Color(hex: 0x7C3AED).opacity(0.35), radius: 18, y: 10)
    }
}

struct ToolTile: View {
    let tool: Tool
    var editing = false
    @State private var wiggle = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top) {
                ToolIcon(tool: tool, size: 46)
                Spacer()
                if editing {
                    Image(systemName: "line.3.horizontal")
                        .font(.headline)
                        .foregroundStyle(.tertiary)
                }
            }
            Text(tool.title)
                .font(.system(.headline, design: .rounded))
                .foregroundStyle(.primary)
                .padding(.top, 4)
            Text(tool.subtitle)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, minHeight: 156, alignment: .topLeading)
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Color.primary.opacity(0.06)))
        .shadow(color: .black.opacity(0.06), radius: 10, y: 4)
        .rotationEffect(.degrees(editing && wiggle ? 1.2 : editing ? -1.2 : 0))
        .animation(editing ? .easeInOut(duration: 0.14).repeatForever(autoreverses: true) : .default, value: wiggle)
        .onAppear { wiggle = true }
        .onChange(of: editing) { _ in wiggle.toggle() }
    }
}

struct ToolIcon: View {
    let tool: Tool
    var size: CGFloat = 46

    var body: some View {
        Image(systemName: tool.symbol)
            .font(.system(size: size * 0.45, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: size, height: size)
            .background(LinearGradient(tool), in: RoundedRectangle(cornerRadius: size * 0.3, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: size * 0.3, style: .continuous).strokeBorder(.white.opacity(0.25), lineWidth: 0.5))
            .shadow(color: tool.color.opacity(0.4), radius: 8, y: 4)
    }
}

/// Soft brand-coloured glow behind the grouped background.
struct BrandBackground: View {
    var body: some View {
        ZStack(alignment: .top) {
            Color(.systemGroupedBackground)
            LinearGradient(colors: Color.brand.map { $0.opacity(0.16) } + [.clear], startPoint: .topLeading, endPoint: .bottom)
                .frame(height: 420)
        }
        .ignoresSafeArea()
    }
}

struct PressableStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .animation(.spring(response: 0.25, dampingFraction: 0.7), value: configuration.isPressed)
    }
}

/// Shown when a PDF or image is shared to the app from Files, Mail, Safari…
struct OpenWithSheet: View {
    let file: InputFile
    let choose: (Tool) -> Void

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label(file.name, systemImage: "doc.fill").lineLimit(1)
                }
                Section("Open with") {
                    ForEach(Tool.allCases.filter { $0.accepts(file) }) { tool in
                        Button { choose(tool) } label: {
                            HStack(spacing: 14) {
                                ToolIcon(tool: tool, size: 34)
                                VStack(alignment: .leading) {
                                    Text(tool.title).foregroundStyle(.primary)
                                    Text(tool.subtitle).font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Choose a Tool")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
