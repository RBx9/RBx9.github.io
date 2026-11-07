#!/usr/bin/env python3
# RBx9 Signer 1.3.25: import errors after a download are shown, and every
# download step is written to the Injection Log (Settings > Features).
# Apply AFTER upgrade_v1_3_24.py. Set RBX9_TREE to use another tree.
import os
from pathlib import Path

tree = Path(os.environ.get("RBX9_TREE", "feather"))
p = tree / "Feather/Backend/Observable/DownloadManager.swift"
s = p.read_text()


def once(old, new, label):
    global s
    assert s.count(old) == 1, ("v1.3.25 " + label, s.count(old))
    s = s.replace(old, new, 1)


once(r'''			if err != nil {
				let generator = UINotificationFeedbackGenerator()
				generator.notificationOccurred(.error)
			}
''', r'''			if let err {
				let generator = UINotificationFeedbackGenerator()
				generator.notificationOccurred(.error)
				RBx9InjectLog.add("download: import FAILED for \(dl.fileName): \(err.localizedDescription)")
				DispatchQueue.main.async {
					UIAlertController.showAlertWithOk(
						title: "Import failed",
						message: "\(dl.fileName) was downloaded but could not be imported. \(err.localizedDescription)"
					)
				}
			} else {
				RBx9InjectLog.add("download: import OK for \(dl.fileName)")
			}
''', "import callback")

once(r'''			try handlePachageFile(url: destinationURL, dl: download)
''', r'''			let rbx9Size = (try? FileManager.default.attributesOfItem(atPath: destinationURL.path)[.size] as? Int64) ?? -1
			RBx9InjectLog.add("download: file received \(destinationURL.lastPathComponent) (\(rbx9Size) bytes), importing")
			try handlePachageFile(url: destinationURL, dl: download)
''', "file received")

once(r'''		let failedName = download.fileName
''', r'''		RBx9InjectLog.add("download: network error \((error as NSError).code) \(error.localizedDescription) for \(download.fileName)")
		let failedName = download.fileName
''', "network error log")

once(r'''		let task = _session.downloadTask(with: url)
		task.taskDescription = id
		download.task = task
		task.resume()

		downloads.append(download)
''', r'''		let task = _session.downloadTask(with: url)
		task.taskDescription = id
		download.task = task
		task.resume()
		RBx9InjectLog.add("download: started \(url.absoluteString)")

		downloads.append(download)
''', "started")

# --- Background session cannot create its temp file (NSURLErrorCannotCreateFile,
# -3000): fall back to a normal session and remember it for this device.
once(r'''	var rbx9RetryCount = 0
''', r'''	var rbx9RetryCount = 0
	var rbx9UsedForeground = false
''', "foreground flag")

once(r'''	private var _session: URLSession!
''', r'''	private var _session: URLSession!

	/// Used when iOS's background download service cannot create its temporary
	/// file on this device (NSURLErrorCannotCreateFile, -3000).
	private lazy var _rbx9FallbackSession: URLSession = {
		let configuration = URLSessionConfiguration.default
		configuration.waitsForConnectivity = true
		return URLSession(configuration: configuration, delegate: self, delegateQueue: nil)
	}()

	private static let _rbx9PreferForegroundKey = "rbx9.downloads.preferForeground"

	private func _rbx9Session(foreground: Bool) -> URLSession {
		if foreground { return _rbx9FallbackSession }
		return _session
	}
''', "fallback session")

once(r'''	fileprivate func _rbx9ForgetProvenance(id: String) {''', r'''	/// Task identifiers repeat across sessions, so match by object or by the
	/// download id stored in the task description.
	fileprivate static func _rbx9Matches(_ download: Download, _ task: URLSessionDownloadTask) -> Bool {
		guard let existing = download.task else { return false }
		if existing === task { return true }
		if let a = existing.taskDescription, let b = task.taskDescription { return a == b }
		return false
	}

	fileprivate func _rbx9ForgetProvenance(id: String) {''', "matcher")

once(r'''if let existing = downloads.first(where: { $0.task?.taskIdentifier == task.taskIdentifier }) {''',
     r'''if let existing = downloads.first(where: { Self._rbx9Matches($0, task) }) {''', "adopt match")
once(r'''return self.downloads.first(where: { $0.task?.taskIdentifier == task.taskIdentifier })''',
     r'''return self.downloads.first(where: { Self._rbx9Matches($0, task) })''', "resolve match")

once(r'''		let task = _session.downloadTask(with: url)
		task.taskDescription = id
		download.task = task
		task.resume()
		RBx9InjectLog.add("download: started''', r'''		let rbx9Foreground = UserDefaults.standard.bool(forKey: Self._rbx9PreferForegroundKey)
		download.rbx9UsedForeground = rbx9Foreground
		let task = _rbx9Session(foreground: rbx9Foreground).downloadTask(with: url)
		task.taskDescription = id
		download.task = task
		task.resume()
		RBx9InjectLog.add("download: started''', "start session")

once(r'''			let task = _session.downloadTask(withResumeData: resumeData)
''', r'''			let task = _rbx9Session(foreground: download.rbx9UsedForeground).downloadTask(withResumeData: resumeData)
''', "resume data session")
once(r'''		} else if let url = download.task?.originalRequest?.url {
			let task = _session.downloadTask(with: url)
''', r'''		} else if let url = download.task?.originalRequest?.url {
			let task = _rbx9Session(foreground: download.rbx9UsedForeground).downloadTask(with: url)
''', "resume url session")

once(r'''		let nsError = error as NSError
''', r'''		let nsError = error as NSError

		if nsError.code == NSURLErrorCannotCreateFile, !download.rbx9UsedForeground {
			RBx9InjectLog.add("download: background session cannot create its temp file (-3000); retrying with a normal session")
			UserDefaults.standard.set(true, forKey: Self._rbx9PreferForegroundKey)
			download.rbx9UsedForeground = true
			let retryURL = download.url
			DispatchQueue.main.async {
				download.resumeData = nil
				download.rbx9RetryCount = 0
				let task = self._rbx9FallbackSession.downloadTask(with: retryURL)
				task.taskDescription = download.id
				download.task = task
				task.resume()
			}
			return
		}
''', "fallback on -3000")

p.write_text(s)

# The import destination (Documents/Unsigned) is deleted by Reset > Delete
# Imported Apps and only recreated at the next launch. Recreate it before the
# move so imports never fail on a missing folder.
fh = tree / "Feather/Utilities/Handlers/AppFileHandler.swift"
t = fh.read_text()
old = "\t\ttry _fileManager.moveItem(at: payloadURL, to: destinationURL)\n"
assert t.count(old) == 1, ("v1.3.25 move", t.count(old))
t = t.replace(old, "\t\ttry _fileManager.createDirectoryIfNeeded(at: _fileManager.unsigned)\n" + old, 1)
fh.write_text(t)

cfg = tree / "Feather.xcconfig"
c = cfg.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.24") != 1:
    raise RuntimeError("v1.3.25: expected base 1.3.24")
cfg.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.24", "FEATHER_PROJECT_VERSION=1.3.25", 1))
print("RBx9 v1.3.25: import errors shown, download steps logged, Unsigned folder recreated")
