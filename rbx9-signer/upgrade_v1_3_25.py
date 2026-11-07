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
