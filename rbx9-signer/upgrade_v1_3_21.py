#!/usr/bin/env python3
# RBx9 Signer 1.3.21 private:
#  - Sign & Install / Sign Only show a spinner and "Signing..." inside the button.
#  - The installer status label shows a spinner while packaging or handing off.
#  - Downloads use a background URLSession: they keep running when the app is
#    left, resume after a dropped connection, and are re-attached after relaunch.
# Apply AFTER upgrade_v1_3_20.py, to the upstream tree in ./feather.
from pathlib import Path
import re

root = Path("feather/Feather")
BL = lambda x: re.sub(r'(?m)^[ \t]+$', '', x)



p = root / "Backend/Observable/DownloadManager.swift"
s = BL(p.read_text())

def once(old, new, label):
    global s
    old = BL(old)
    assert s.count(old) == 1, (label, s.count(old))
    s = s.replace(old, new, 1)

once("import BackgroundTasks\n", "import BackgroundTasks\nimport UIKit\n", "import")

once("\tvar task: URLSessionDownloadTask?\n\tvar resumeData: Data?\n",
     "\tvar task: URLSessionDownloadTask?\n\tvar resumeData: Data?\n\tvar rbx9RetryCount = 0\n", "retry field")

once("""	override init() {
		super.init()
		let configuration = URLSessionConfiguration.default
		_session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
	}
""", """	/// Set by AppDelegate when iOS relaunches the app for finished background
	/// transfers. It must be called once the session has delivered its events.
	var rbx9BackgroundCompletionHandler: (() -> Void)?

	override init() {
		super.init()
		// A background session keeps downloading while the app is suspended or
		// closed, and iOS hands the finished file back on the next launch.
		let identifier = (Bundle.main.bundleIdentifier ?? "com.rbx9.signer") + ".downloads"
		let configuration = URLSessionConfiguration.background(withIdentifier: identifier)
		configuration.isDiscretionary = false
		configuration.sessionSendsLaunchEvents = true
		configuration.waitsForConnectivity = true
		configuration.allowsCellularAccess = true
		_session = URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
		_rbx9ReattachRunningDownloads()
	}

	// MARK: RBx9 background download support
	private static func _rbx9ProvenanceKey(_ id: String) -> String {
		"rbx9.download.provenance." + id
	}

	private func _rbx9SaveProvenance(_ provenance: SourceAppProvenance?, id: String) {
		let key = Self._rbx9ProvenanceKey(id)
		if let provenance, let data = try? JSONEncoder().encode(provenance) {
			UserDefaults.standard.set(data, forKey: key)
		} else {
			UserDefaults.standard.removeObject(forKey: key)
		}
	}

	private func _rbx9LoadProvenance(id: String) -> SourceAppProvenance? {
		guard let data = UserDefaults.standard.data(forKey: Self._rbx9ProvenanceKey(id)) else { return nil }
		return try? JSONDecoder().decode(SourceAppProvenance.self, from: data)
	}

	fileprivate func _rbx9ForgetProvenance(id: String) {
		UserDefaults.standard.removeObject(forKey: Self._rbx9ProvenanceKey(id))
	}

	/// Re-create Download entries for transfers iOS kept running while the app
	/// was suspended or relaunched, so progress and completion still work.
	private func _rbx9ReattachRunningDownloads() {
		_session.getAllTasks { [weak self] tasks in
			guard let self else { return }
			DispatchQueue.main.async {
				for case let task as URLSessionDownloadTask in tasks {
					_ = self._rbx9Adopt(task)
				}
			}
		}
	}

	/// Must run on the main thread. Returns the matching Download, creating one
	/// for a transfer that survived an app restart.
	@discardableResult
	private func _rbx9Adopt(_ task: URLSessionDownloadTask) -> Download? {
		if let existing = downloads.first(where: { $0.task?.taskIdentifier == task.taskIdentifier }) {
			return existing
		}
		guard task.state != .canceling, task.state != .completed,
			  let url = task.originalRequest?.url else { return nil }
		let id = task.taskDescription ?? UUID().uuidString
		let download = Download(id: id, url: url, sourceProvenance: _rbx9LoadProvenance(id: id))
		download.task = task
		downloads.append(download)
		return download
	}

	/// Look up (or adopt) the Download for a delegate callback from any thread.
	fileprivate func _rbx9Resolve(_ task: URLSessionDownloadTask, adopt: Bool = true) -> Download? {
		let find = { () -> Download? in
			if adopt { return self._rbx9Adopt(task) }
			return self.downloads.first(where: { $0.task?.taskIdentifier == task.taskIdentifier })
		}
		return Thread.isMainThread ? find() : DispatchQueue.main.sync(execute: find)
	}
""", "init")

once("""		let download = Download(id: id, url: url, sourceProvenance: sourceProvenance)

		let task = _session.downloadTask(with: url)
		download.task = task
		task.resume()
""", """		let download = Download(id: id, url: url, sourceProvenance: sourceProvenance)
		_rbx9SaveProvenance(sourceProvenance, id: id)

		let task = _session.downloadTask(with: url)
		task.taskDescription = id
		download.task = task
		task.resume()
""", "start")

once("""			let task = _session.downloadTask(withResumeData: resumeData)
			download.task = task
			task.resume()
""", """			let task = _session.downloadTask(withResumeData: resumeData)
			task.taskDescription = download.id
			download.task = task
			task.resume()
""", "resume data")

once("""			let task = _session.downloadTask(with: url)
			download.task = task
			task.resume()

			#if !targetEnvironment(macCatalyst)
			_updateBackgroundAudioState()
			#endif
		}
	}""", """			let task = _session.downloadTask(with: url)
			task.taskDescription = download.id
			download.task = task
			task.resume()

			#if !targetEnvironment(macCatalyst)
			_updateBackgroundAudioState()
			#endif
		}
	}""", "resume url")

once("""	func cancelDownload(_ download: Download) {
		download.task?.cancel()
""", """	func cancelDownload(_ download: Download) {
		_rbx9ForgetProvenance(id: download.id)
		download.task?.cancel()
""", "cancel")

once("""	func handlePachageFile(url: URL, dl: Download) throws {
		FR.handlePackageFile(url, download: dl) { err in
""", """	func handlePachageFile(url: URL, dl: Download) throws {
		// Importing a large IPA can outlast the short time iOS gives a woken app.
		var rbx9Background: UIBackgroundTaskIdentifier = .invalid
		let beginBackground = {
			rbx9Background = UIApplication.shared.beginBackgroundTask(withName: "RBx9 import download") {
				UIApplication.shared.endBackgroundTask(rbx9Background)
				rbx9Background = .invalid
			}
		}
		if Thread.isMainThread { beginBackground() } else { DispatchQueue.main.sync(execute: beginBackground) }
		FR.handlePackageFile(url, download: dl) { err in
			DispatchQueue.main.async {
				if rbx9Background != .invalid {
					UIApplication.shared.endBackgroundTask(rbx9Background)
					rbx9Background = .invalid
				}
			}
			self._rbx9ForgetProvenance(id: dl.id)
""", "handle")

once("""		guard let download = getDownloadTask(by: downloadTask) else { return }

		let tempDirectory""", """		guard let download = _rbx9Resolve(downloadTask) else { return }

		let tempDirectory""", "finish")

once("""		guard let download = getDownloadTask(by: downloadTask) else { return }

		DispatchQueue.main.async {
			download.progress""", """		guard let download = _rbx9Resolve(downloadTask) else { return }

		DispatchQueue.main.async {
			download.progress""", "write data")

marker = "\tfunc urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {"
assert s.count(marker) == 1
head = s[:s.index(marker)]
tail = """	func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
		guard
			let error,
			let downloadTask = task as? URLSessionDownloadTask,
			let download = _rbx9Resolve(downloadTask, adopt: false)
		else {
			return
		}

		// A dropped connection leaves resume data. Continue from where it stopped
		// (a few times) instead of throwing the whole download away.
		let nsError = error as NSError
		if nsError.code != NSURLErrorCancelled, download.rbx9RetryCount < 5 {
			download.rbx9RetryCount += 1
			let resumeData = nsError.userInfo[NSURLSessionDownloadTaskResumeData] as? Data
			DispatchQueue.main.async {
				download.resumeData = resumeData
				self.resumeDownload(download)
			}
			return
		}

		DispatchQueue.main.async {
			self._rbx9ForgetProvenance(id: download.id)
			if let index = self.getDownloadIndex(by: download.id) {
				self.downloads.remove(at: index)
			}
		}
	}

	/// iOS has delivered every event queued while the app was not running.
	func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
		DispatchQueue.main.async {
			let handler = self.rbx9BackgroundCompletionHandler
			self.rbx9BackgroundCompletionHandler = nil
			handler?()
		}
	}
}
"""
s = head + tail
p.write_text(s)

q = root / "Backend/Storage/Storage+SourceMetadata.swift"
t = q.read_text()
assert t.count("struct SourceAppProvenance: Equatable {") == 1
q.write_text(t.replace("struct SourceAppProvenance: Equatable {", "struct SourceAppProvenance: Equatable, Codable {", 1))

a = root / "FeatherApp.swift"
u = a.read_text()
old = """		_addDefaultCertificates()
		return true
	}
"""
assert u.count(old) == 1
u = u.replace(old, old + """
	/// iOS relaunches the app when a background download finishes. Hand the
	/// completion handler to the download manager so it can import the file.
	func application(
		_ application: UIApplication,
		handleEventsForBackgroundURLSession identifier: String,
		completionHandler: @escaping () -> Void
	) {
		DownloadManager.shared.rbx9BackgroundCompletionHandler = completionHandler
	}
""", 1)
a.write_text(u)
print("downloads patched")



def patch(path, edits):
    p = root / path
    s = p.read_text()
    for old, new, label in edits:
        assert s.count(old) == 1, (path, label, s.count(old))
        s = s.replace(old, new, 1)
    p.write_text(s)

patch("Views/Signing/SigningView.swift", [
    ("    @State private var _rbx9InjectingTweaks = false\n",
     "    @State private var _rbx9InjectingTweaks = false\n"
     "    /// 0 = idle, 1 = Sign & Install pressed, 2 = Sign Only pressed.\n"
     "    @State private var _rbx9SigningMode = 0\n", "state"),
    ('Label(_rbx9HasTweakChanges ? "Inject & Install" : "Sign & Install", systemImage: "square.and.arrow.down.fill")',
     'HStack(spacing: 9) {\n'
     '                            if _isSigning && _rbx9SigningMode == 1 {\n'
     '                                ProgressView()\n'
     '                                    .progressViewStyle(.circular)\n'
     '                                    .tint(Color.black)\n'
     '                                Text("Signing…")\n'
     '                            } else {\n'
     '                                Image(systemName: "square.and.arrow.down.fill")\n'
     '                                Text(_rbx9HasTweakChanges ? "Inject & Install" : "Sign & Install")\n'
     '                            }\n'
     '                        }', "install button"),
    ('Label(_rbx9HasTweakChanges ? "Inject Only" : "Sign Only", systemImage: "signature")',
     'HStack(spacing: 7) {\n'
     '                            if _isSigning && _rbx9SigningMode == 2 {\n'
     '                                ProgressView()\n'
     '                                    .progressViewStyle(.circular)\n'
     '                                    .tint(Color.accentColor)\n'
     '                                Text("Signing…")\n'
     '                            } else {\n'
     '                                Image(systemName: "signature")\n'
     '                                Text(_rbx9HasTweakChanges ? "Inject Only" : "Sign Only")\n'
     '                            }\n'
     '                        }', "only button"),
    ("\t\t_isSigning = true\n",
     "\t\t_rbx9SigningMode = (installAfterSigning == false) ? 2 : 1\n\t\t_isSigning = true\n", "mode"),
])

patch("Views/Library/Install/InstallPreviewView.swift", [
    ("            Label(viewModel.statusLabel, systemImage: viewModel.statusImage)\n",
     "            Label {\n"
     "                Text(viewModel.statusLabel)\n"
     "            } icon: {\n"
     "                // Large IPAs spend a while packaging; show that work is happening.\n"
     "                if rbx9IsWorking {\n"
     "                    ProgressView()\n"
     "                        .controlSize(.small)\n"
     "                } else {\n"
     "                    Image(systemName: viewModel.statusImage)\n"
     "                }\n"
     "            }\n", "status label"),
    ("    @ViewBuilder\n    private func rbx9RecoveryCard() -> some View {",
     "    private var rbx9IsWorking: Bool {\n"
     "        switch viewModel.status {\n"
     "        case .none, .sendingManifest, .sendingPayload:\n"
     "            return true\n"
     "        default:\n"
     "            return false\n"
     "        }\n"
     "    }\n\n"
     "    @ViewBuilder\n    private func rbx9RecoveryCard() -> some View {", "working flag"),
])
print("loading patched")

# --- Closed-connection errors while iOS fetches the IPA are not fatal -------
_srv = root / "Backend/Server/ServerInstaller.swift"
_t = _srv.read_text()
_old = """					case .failure(let error):
						self._updateStatus(.broken(error))
"""
_new = """					case .failure(let error):
						if Self._rbx9IsClientDisconnect(error) {
							// iOS often closes and reopens the connection while it
							// fetches a large IPA. Wait for a retry before failing.
							self._rbx9StartDisconnectWatchdog(error)
						} else {
							self._updateStatus(.broken(error))
						}
"""
assert _t.count(_old) == 1, "payload failure case"
_t = _t.replace(_old, _new, 1)
_old2 = "	private func _updateStatus(_ newStatus: InstallerStatusViewModel.InstallerStatus) {"
assert _t.count(_old2) == 1, "update status"
_helpers = """	/// NIOCore.ChannelError code 5 (ioOnClosedChannel): the other side closed the
	/// connection mid-transfer. That is expected when iOS retries a request.
	private static func _rbx9IsClientDisconnect(_ error: Error) -> Bool {
		let nsError = error as NSError
		if nsError.domain == "NIOCore.ChannelError" && nsError.code == 5 { return true }
		return String(describing: error).contains("ioOnClosedChannel")
	}

	/// If iOS never comes back after a dropped connection, report the failure
	/// instead of leaving the installer waiting forever.
	private func _rbx9StartDisconnectWatchdog(_ error: Error) {
		DispatchQueue.main.asyncAfter(deadline: .now() + 25) { [weak self] in
			guard let self else { return }
			if case .sendingPayload = self.viewModel.status {
				self.viewModel.status = .broken(error)
			}
		}
	}

"""
_t = _t.replace(_old2, _helpers + _old2, 1)
_srv.write_text(_t)

# --- One-time automatic web-installer fallback (only when direct handoff stalls)
_ip = root / "Views/Library/Install/InstallPreviewView.swift"
_s = _ip.read_text()

def _once(old, new, label):
    global _s
    assert _s.count(old) == 1, ("fallback " + label, _s.count(old))
    _s = _s.replace(old, new, 1)

_once('    @State private var rbx9ServerCheck = ""\n',
      '    @State private var rbx9ServerCheck = ""\n'
      '    @State private var rbx9DidWebFallback = false\n'
      '    @State private var rbx9WebFallbackTask: Task<Void, Never>?\n', "state")

_once('                    rbx9RecoveryTask?.cancel()\n                    rbx9RecoveryTask = Task { @MainActor in\n',
      '                    // The user chose to skip the web page, so it only appears if\n'
      '                    // iOS has not started the install shortly after the handoff.\n'
      '                    rbx9WebFallbackTask?.cancel()\n'
      '                    if _serverMethod == 1 && _skipSafariInstallPage && !rbx9DidWebFallback {\n'
      '                        rbx9WebFallbackTask = Task { @MainActor in\n'
      '                            try? await Task.sleep(nanoseconds: 5_000_000_000)\n'
      '                            guard !Task.isCancelled, !rbx9DidWebFallback, !_isWebviewPresenting else { return }\n'
      '                            if case .ready = viewModel.status {\n'
      '                                rbx9DidWebFallback = true\n'
      '                                _isWebviewPresenting = true\n'
      '                            }\n'
      '                        }\n'
      '                    }\n'
      '                    rbx9RecoveryTask?.cancel()\n                    rbx9RecoveryTask = Task { @MainActor in\n', "ready branch")

_once('                    rbx9ServerCheck = ""\n                    rbx9InstallHint = ""\n',
      '                    rbx9ServerCheck = ""\n                    rbx9InstallHint = ""\n'
      '                    rbx9WebFallbackTask?.cancel()\n'
      '                    rbx9WebFallbackTask = nil\n', "leave ready")

_ip.write_text(_s)

cfg = Path("feather/Feather.xcconfig")
c = cfg.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.20") != 1:
    raise RuntimeError("v1.3.21: expected base 1.3.20")
cfg.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.20", "FEATHER_PROJECT_VERSION=1.3.21", 1))
print("RBx9 v1.3.21 private: button loading state, background downloads")
