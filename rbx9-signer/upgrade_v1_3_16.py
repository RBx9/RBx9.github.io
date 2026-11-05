#!/usr/bin/env python3
# RBx9 Signer 1.3.16: polished vault deletion sheet, compact searchable source
# rows with downloaded status; improved download diagnostics.
# GPL-3.0-only Feather derivative. Keep signing behavior unchanged.
from pathlib import Path

root=Path("feather")
swift=root/"Feather/Views/Signing/SigningTweaksView.swift"
src=swift.read_text()

def once(old,new,reason):
    global src
    n=src.count(old)
    if n!=1:
        raise RuntimeError(f"{reason}: wanted 1 anchor, got {n}")
    src=src.replace(old,new,1)

old_dialog=r'''        .confirmationDialog(
            "Delete stored file?",
            isPresented: Binding(
                get: { pendingDelete != nil },
                set: { if !$0 { pendingDelete = nil } }
            ),
            titleVisibility: .visible
        ) {
            Button("Delete from Storage", role: .destructive) {
                guard let file = pendingDelete else { return }
                pendingDelete = nil
                do { try vault.delete(file) }
                catch {
                    notice = error.localizedDescription
                    showNotice = true
                }
            }
            Button("Cancel", role: .cancel) { pendingDelete = nil }
        } message: {
            Text("This deletes the saved copy. Previously signed apps and original files outside RBx9 are unchanged.")
        }'''
new_sheet=r'''        .sheet(item: $pendingDelete) { file in
            RBx9DeleteTweakSheet(file: file) {
                pendingDelete = nil
                do { try vault.delete(file) }
                catch {
                    notice = error.localizedDescription
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                        showNotice = true
                    }
                }
            }
            .presentationDetents([.height(328)])
            .presentationDragIndicator(.visible)
        }'''
once(old_dialog,new_sheet,"replace system deletion popover")

# A dedicated SwiftUI sheet avoids iOS 26's floating context-menu popover.
# The destructive action must still be confirmed before deleting the file.
src += r"""

// MARK: - RBx9 styled confirmation for deleting stored files
private struct RBx9DeleteTweakSheet: View {
    @Environment(\.dismiss) private var dismiss
    let file: RBx9StoredTweak
    let onDelete: () -> Void

    var body: some View {
        VStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 18)
                    .fill(Color.red.opacity(0.11))
                    .frame(width: 58, height: 58)
                Image(systemName: "trash")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(.red)
            }
            .padding(.top, 10)

            VStack(spacing: 7) {
                Text("Remove from Dylib Storage?")
                    .font(.headline)
                    .multilineTextAlignment(.center)
                Text(file.name)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .foregroundStyle(.cyan)
                Text("Only the saved copy is deleted. Your installed apps and files outside RBx9 stay unchanged.")
                    .font(.footnote)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            Button(role: .destructive) {
                dismiss()
                onDelete()
            } label: {
                Label("Delete File", systemImage: "trash")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.red)
            .background(Color.red.opacity(0.12),
                        in: RoundedRectangle(cornerRadius: 15))

            Button {
                dismiss()
            } label: {
                Text("Keep File")
                    .font(.subheadline.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.black)
            .background(Color.cyan, in: RoundedRectangle(cornerRadius: 15))
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 16)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(UIColor.secondarySystemBackground))
    }
}
"""

# Only suppress success popups: the Downloaded badge confirms success.
once(
    '''                notice = "Downloaded \(item.name) into Dylib Storage."
                showNotice = true
                return stored''',
    '''                return stored''',
    "remove redundant post-download confirmation"
)
once(
    '''                notice = "Already in Dylib Storage. Reusing the existing copy."
                showNotice = true
                return stored''',
    '''                return stored''',
    "remove redundant duplicate confirmation"
)

# Real HTTP codes help distinguish an old release URL, missing asset or
# transport error. Avoid generic "GitHub download failed" messages.
once(
    '''            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw NSError(domain: "RBx9 Dylib Source", code: 5,
                              userInfo: [NSLocalizedDescriptionKey: "The GitHub download failed."])
            }''',
    '''            guard let http = response as? HTTPURLResponse else {
                throw NSError(domain: "RBx9 Dylib Source", code: 5,
                              userInfo: [NSLocalizedDescriptionKey: "The download returned an unexpected response."])
            }
            guard http.statusCode == 200 else {
                let help = http.statusCode == 404
                    ? "The Release asset is missing or its URL is outdated. Refresh your source."
                    : "Please retry or check the GitHub Release link."
                throw NSError(domain: "RBx9 Dylib Source", code: http.statusCode,
                    userInfo: [NSLocalizedDescriptionKey: "GitHub download HTTP \(http.statusCode). \(help)"])
            }''',
    "show real GitHub response code"
)

# Replace only the final online library SwiftUI view, not its source model,
# quick editor API or the local vault. The view lives at this file's end
# before this patch appends a separate delete sheet.
start=src.index("struct RBx9RemoteDylibLibraryView: View {")
end=src.index("// MARK: - RBx9 styled confirmation for deleting stored files",start)
new_library=r'''struct RBx9RemoteDylibLibraryView: View {
    @Environment(\.dismiss) private var dismiss
    @StateObject private var source = RBx9DylibSourceModel()
    @StateObject private var vault = RBx9DylibStorage.shared
    @State private var searchText = ""
    // In Quick Editor, a saved file can be added instantly without re-downloading.
    var onAdded: ((URL) -> Void)? = nil

    private var visibleEntries: [RBx9SourceDylib] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return source.entries }
        return source.entries.filter { item in
            item.name.localizedCaseInsensitiveContains(query) ||
            item.fileName.localizedCaseInsensitiveContains(query) ||
            item.description.localizedCaseInsensitiveContains(query) ||
            (item.compatibility ?? "").localizedCaseInsensitiveContains(query)
        }
    }

    private func localFile(for item: RBx9SourceDylib) -> URL? {
        vault.items.first {
            $0.hash.caseInsensitiveCompare(item.sha256) == .orderedSame
        }?.url
    }

    @ViewBuilder
    private func downloadControl(for item: RBx9SourceDylib) -> some View {
        if source.downloading.contains(item.id) {
            VStack(spacing: 4) {
                ProgressView()
                    .controlSize(.small)
                Text("Downloading")
                    .font(.caption2)
            }
            .foregroundStyle(.cyan)
            .frame(width: 98)
        } else if let stored = localFile(for: item) {
            if let onAdded {
                Button {
                    onAdded(stored)
                } label: {
                    VStack(spacing: 3) {
                        Label("Add to IPA", systemImage: "plus.circle.fill")
                            .font(.caption2.weight(.semibold))
                        Text("Downloaded")
                            .font(.system(size: 10))
                    }
                    .frame(width: 98)
                }
                .buttonStyle(.bordered)
                .tint(.cyan)
                .accessibilityLabel("Add downloaded \(item.name) to IPA")
            } else {
                Label("Downloaded", systemImage: "checkmark.circle.fill")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.green)
                    .frame(width: 101)
                    .accessibilityLabel(item.name + " downloaded")
            }
        } else {
            Button {
                Task {
                    if let url = await source.download(item) {
                        vault.refresh()
                        onAdded?(url)
                    }
                }
            } label: {
                Label("Download", systemImage: "arrow.down.to.line")
                    .font(.caption2.weight(.semibold))
                    .frame(width: 96)
            }
            .buttonStyle(.borderedProminent)
            .tint(.cyan)
            .foregroundStyle(.black)
            .accessibilityLabel("Download " + item.name)
        }
    }

    @ViewBuilder
    private func sourceRow(_ item: RBx9SourceDylib) -> some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 5) {
                Text(item.name)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                    .truncationMode(.middle)
                HStack(spacing: 5) {
                    Text("v" + item.version)
                    Text("·")
                    Text(ByteCountFormatter.string(fromByteCount: item.size,
                                                   countStyle: .file))
                }
                .font(.caption2)
                .foregroundStyle(.cyan)
                if !item.description.isEmpty {
                    Text(item.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                if let compatibility = item.compatibility,
                   !compatibility.isEmpty {
                    Text(compatibility)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            downloadControl(for: item)
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.vertical, 7)
        .contentShape(Rectangle())
    }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 12) {
                        Image(systemName: "shippingbox.fill")
                            .font(.system(size: 22, weight: .semibold))
                            .foregroundStyle(.cyan)
                            .frame(width: 43, height: 43)
                            .background(Color.cyan.opacity(0.13),
                                        in: RoundedRectangle(cornerRadius: 13))
                        VStack(alignment: .leading, spacing: 4) {
                            Text("RBx9 Dylib Source")
                                .font(.headline)
                            Text("\(source.entries.count) available  ·  \(vault.items.count) saved")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 4)
                } footer: {
                    Text(onAdded == nil
                         ? "Download tweaks to your local storage. They remain available for later IPA signing."
                         : "Select Download to save and add a tweak. Already saved files can be added directly.")
                }

                Section {
                    if source.refreshing && source.entries.isEmpty {
                        HStack(spacing: 10) {
                            ProgressView()
                            Text("Loading dylibs…")
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 12)
                    } else if source.entries.isEmpty {
                        Text("No published dylibs yet. Add one in RBx9 Source Manager.")
                            .foregroundStyle(.secondary)
                    } else if visibleEntries.isEmpty {
                        Text("No dylibs match your search.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(visibleEntries) { item in
                            sourceRow(item)
                        }
                    }
                } header: {
                    Text("Available Dylibs")
                } footer: {
                    Text("Downloads are verified using SHA-256. Saving a dylib never signs or installs an app automatically.")
                }
            }
            .navigationTitle("Source Dylibs")
            .searchable(text: $searchText, prompt: "Search dylibs")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if onAdded != nil {
                        Button("Done") { dismiss() }
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await source.refresh() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(source.refreshing)
                }
            }
            .refreshable {
                vault.refresh()
                await source.refresh()
            }
            .task {
                vault.refresh()
                await source.refresh()
            }
            .alert("RBx9 Dylib Source", isPresented: $source.showNotice) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(source.notice)
            }
        }
    }
}

'''
src=src[:start]+new_library+src[end:]

for marker in [
    '.sheet(item: $pendingDelete)',
    'RBx9DeleteTweakSheet(file: file)',
    'private struct RBx9DeleteTweakSheet: View',
    'func downloadControl(for item: RBx9SourceDylib)',
    'Label("Downloaded", systemImage: "checkmark.circle.fill")',
    '.searchable(text: $searchText, prompt: "Search dylibs")',
    'GitHub download HTTP',
]:
    if marker not in src:
        raise RuntimeError("Missing 1.3.16 marker: "+marker)
if '"Delete stored file?"' in src:
    raise RuntimeError("Old system delete confirmation remains")

swift.write_text(src)
cfg=root/"Feather.xcconfig"
content=cfg.read_text()
if content.count("FEATHER_PROJECT_VERSION=1.3.15")!=1:
    raise RuntimeError("Expected RBx9 Signer v1.3.15")
cfg.write_text(content.replace("FEATHER_PROJECT_VERSION=1.3.15",
                                "FEATHER_PROJECT_VERSION=1.3.16",1))
print("RBx9 v1.3.16: dark delete sheet, searchable compact dylib list, Downloaded status, actionable diagnostics")
